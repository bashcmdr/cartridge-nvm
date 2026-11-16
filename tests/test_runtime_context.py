#!/usr/bin/env python3
"""NVM cartridge lifecycle protocol tests; no real NVM/Node or installer runs."""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(os.environ.get('NVM_RUNTIME_TEST_REPO', pathlib.Path(__file__).resolve().parent.parent))
BASH = os.environ.get('NVM_RUNTIME_TEST_BASH', shutil.which('bash'))
EVIDENCE = os.environ.get('NVM_RUNTIME_TEST_EVIDENCE_DIR')
NVM = r'''printf 'source:%s:%s\n' "$NVM_DIR" "$*" >> "$TRACE"
NVM_FIXTURE_ROOT=$NVM_DIR
nvm_aux_fixture() { :; }
nvm() {
    printf 'nvm:%s\n' "$*" >> "$TRACE"
    case ${1-} in
        --version)
            [[ ${EMPTY_VERSION:-0} == 0 ]] && printf 'fixture-0.40.0\n'
            return "${VERSION_STATUS:-0}" ;;
        list) printf 'fixture installed version\n'; return "${LIST_STATUS:-0}" ;;
        current) printf 'v2.0.0\n' ;;
        use)
            NVM_BIN="$NVM_FIXTURE_ROOT/versions/node/v2.0.0/bin"
            NVM_INC="$NVM_FIXTURE_ROOT/versions/node/v2.0.0/include/node"
            case :$PATH: in *:"$NVM_BIN":*) ;; *) PATH="$NVM_BIN:$PATH";; esac
            export PATH NVM_BIN NVM_INC ;;
        deactivate)
            [[ ${DEACTIVATE_STATUS:-0} == 0 ]] || return "$DEACTIVATE_STATUS"
            if [[ ${NVM_BIN:-} && $PATH == "$NVM_BIN":* ]]; then PATH=${PATH#"$NVM_BIN":}; fi
            unset NVM_BIN NVM_INC ;;
        *) return "${PASSTHRU_STATUS:-0}" ;;
    esac
}
if [[ ${SOURCE_PARTIAL:-0} == 1 ]]; then NVM_PARTIAL_EFFECT=retained; fi
if [[ ${SOURCE_STATUS:-0} != 0 ]]; then return "$SOURCE_STATUS"; fi
nvm use fixture >/dev/null
'''


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='bcm-nvm-runtime-owned-')
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.home = self.root / 'home space'; self.home.mkdir()
        self.project = self.root / 'project space'; self.project.mkdir()
        self.nvm = self.home / '.nvm'; self.install(self.nvm)
        self.custom = self.home / 'custom nvm space'; self.install(self.custom)
        self.tools = self.root / 'sinks'; self.tools.mkdir()
        self.trace = self.root / 'calls.log'; self.trace.write_text('')
        self.forbidden = self.root / 'forbidden.log'; self.forbidden.write_text('')
        for name in ['sudo','curl','wget','service','systemctl','git','node','npm']:
            path = self.tools / name
            path.write_text('#!/bin/sh\nprintf "%s\\n" "$0 $*" >> "$FORBIDDEN"\nexit 99\n')
            path.chmod(0o755)
        library = self.root / 'console/lib'; library.mkdir(parents=True)
        (library / 'core.bashcmdr').write_text('__bashcmdr_info() { printf "%s\\n" "$*"; }\n__bashcmdr_success() { printf "%s\\n" "$*"; }\n__bashcmdr_error() { printf "%s\\n" "$*" >&2; }\n')
        (library / 'guards.bashcmdr').write_text('bashcmdr_guard_validate() { printf "guard\\n" >> "$TRACE"; return "${GUARD_STATUS:-0}"; }\n')
        module = self.root / 'console/cartridges/nvm-loader'; module.mkdir(parents=True)
        self.main = module / 'main.bashcmdr'; shutil.copyfile(REPO / 'main.bashcmdr',self.main)
        shutil.copyfile(REPO / 'manifest.json',module / 'manifest.json')
        bare = self.root / 'bare'; bare.mkdir(); self.bare = bare / 'main.bashcmdr'; shutil.copyfile(self.main,self.bare)
        self.protected = [self.home / '.bashrc',self.home / '.npmrc',self.project / '.nvmrc',self.project / 'package.json']
        for path in self.protected: path.write_text('protected fixture: ' + path.name)
        self.before = {str(p):p.read_text() for p in self.protected}
        self.calls = []

    def install(self, root):
        root.mkdir()
        (root / 'nvm.sh').write_text(NVM)
        bin_dir = root / 'versions/node/v2.0.0/bin'; bin_dir.mkdir(parents=True)
        for name in ['node','npm']:
            p=bin_dir/name;p.write_text('#!/bin/sh\nprintf "unexpected node/npm\\n" >> "$FORBIDDEN"\nexit 99\n');p.chmod(0o755)

    def tearDown(self):
        after = {str(p):p.read_text() for p in self.protected}
        if EVIDENCE:
            target=pathlib.Path(EVIDENCE)/self._testMethodName;target.mkdir(parents=True,exist_ok=True)
            (target/'calls.json').write_text(json.dumps(self.calls,indent=2)+'\n')
            (target/'nvm-protocol.log').write_text(self.trace.read_text())
            (target/'forbidden.log').write_text(self.forbidden.read_text())
            (target/'protected-after.json').write_text(json.dumps(after,indent=2)+'\n')
        # Preserve diagnostics even when an archived version fails safety checks.
        self.assertEqual(after,self.before)
        self.assertEqual(self.forbidden.read_text(),'')

    def run_shell(self, body, **extra):
        env={'HOME':str(self.home),'PATH':str(self.tools)+':/usr/bin:/bin','LC_ALL':'C','TERM':'dumb',
             'TRACE':str(self.trace),'FORBIDDEN':str(self.forbidden),'MAIN':str(self.main),'BARE':str(self.bare),
             'CUSTOM':str(self.custom),'BASH_BIN':str(BASH),'BASH_ENV':os.devnull,'ENV':os.devnull}
        env.update({k:str(v) for k,v in extra.items()})
        result=subprocess.run([BASH,'--noprofile','--norc','-c',body],env=env,cwd=self.project,text=True,capture_output=True,timeout=5)
        self.calls.append({'script':body,'environment_overrides':{k:str(v) for k,v in extra.items()},'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        return result

    def ok(self,body,**extra):
        r=self.run_shell(body,**extra);self.assertEqual(r.returncode,0,r.stdout+r.stderr);return r

    def test_custom_root_with_spaces_is_used_for_script_and_completion(self):
        (self.custom/'bash_completion').write_text('printf "completion:%s\\n" "$NVM_DIR" >> "$TRACE"\n')
        self.ok('set -eu; export NVM_DIR="$CUSTOM"; source "$MAIN"; nvm_activate; [[ $BASHCMDR_NVM_LOADED == 1 && $NVM_DIR == "$CUSTOM" && $NVM_BIN == "$CUSTOM/versions/node/v2.0.0/bin" ]]')
        trace=self.trace.read_text();self.assertIn('source:'+str(self.custom)+':',trace);self.assertIn('completion:'+str(self.custom),trace);self.assertNotIn('source:'+str(self.nvm)+':',trace)

    def test_default_root_is_selected_only_when_no_nonempty_configuration(self):
        for value in [None,'']:
            args={} if value is None else {'NVM_DIR':value}
            self.ok('set -eu; source "$MAIN"; nvm_activate; [[ $NVM_DIR == "$HOME/.nvm" && $BASHCMDR_NVM_LOADED == 1 ]]',**args)

    def test_configuration_changed_after_source_is_honored(self):
        self.ok('set -eu; source "$MAIN"; export NVM_DIR="$CUSTOM"; nvm_activate; [[ ${NVM_CONFIG[dir]} == "$CUSTOM" ]]')
        self.assertIn('source:'+str(self.custom),self.trace.read_text())

    def test_missing_installation_is_dormant_and_clears_inherited_marker(self):
        r=self.ok('set -eu; source "$MAIN"; nvm_activate; [[ -z ${BASHCMDR_NVM_LOADED+x} && $NVM_DIR == "$CUSTOM/missing" ]]',NVM_DIR=str(self.custom/'missing'),BASHCMDR_NVM_LOADED='1')
        self.assertIn('skipping',r.stdout);self.assertNotIn('source:',self.trace.read_text())

    def test_existing_empty_missing_or_directory_script_is_failure(self):
        script=self.custom/'nvm.sh'
        for mode in ['empty','missing','directory']:
            if script.is_file():script.unlink()
            if mode=='empty':script.write_text('')
            if mode=='directory':script.mkdir()
            self.ok('set -eu; source "$MAIN"; if nvm_activate; then exit 81; fi; [[ -z ${BASHCMDR_NVM_LOADED+x} ]]',NVM_DIR=self.custom,BASHCMDR_NVM_LOADED=1)
        self.assertNotIn('source:',self.trace.read_text())

    def test_source_failure_preserves_status_and_never_publishes_success(self):
        self.ok('set -eu; source "$MAIN"; rc=0; nvm_activate || rc=$?; [[ $rc == 23 && -z ${BASHCMDR_NVM_LOADED+x} && $NVM_PARTIAL_EFFECT == retained ]]',SOURCE_STATUS=23,SOURCE_PARTIAL=1)

    def test_script_without_nvm_function_is_not_success(self):
        (self.nvm/'nvm.sh').write_text(': # no nvm function\n')
        self.ok('set -eu; source "$MAIN"; if nvm_activate; then exit 81; fi; [[ -z ${BASHCMDR_NVM_LOADED+x} ]]')

    def test_failed_empty_or_partial_version_probe_is_not_loaded(self):
        for extra in [{'VERSION_STATUS':17},{'EMPTY_VERSION':1},{'VERSION_STATUS':19,'EMPTY_VERSION':0}]:
            self.ok('set -eu; source "$MAIN"; if nvm_activate; then exit 81; fi; [[ -z ${BASHCMDR_NVM_LOADED+x} ]]',**extra)

    def test_optional_completion_failure_has_no_loaded_success(self):
        (self.nvm/'bash_completion').write_text('return 29\n')
        self.ok('set -eu; source "$MAIN"; rc=0; nvm_activate || rc=$?; [[ $rc == 29 && -z ${BASHCMDR_NVM_LOADED+x} ]]')

    def test_repeated_source_and_activation_are_validated_without_duplicate_bin(self):
        self.ok('set -eu; source "$MAIN"; nvm_activate; first=$PATH; source "$MAIN"; nvm_activate; [[ $PATH == "$first" && $BASHCMDR_NVM_LOADED == 1 ]]')
        self.assertEqual(sum(line.startswith('source:') for line in self.trace.read_text().splitlines()),2)

    def test_exported_marker_child_with_reset_path_reestablishes_function_and_bin(self):
        self.ok(r'''set -eu; source "$MAIN"; nvm_activate
"$BASH_BIN" --noprofile --norc -c 'set -eu; PATH=/usr/bin:/bin; unset -f nvm 2>/dev/null || :; source "$MAIN"; nvm_activate; declare -F nvm >/dev/null; [[ $BASHCMDR_NVM_LOADED == 1 && $PATH == "$NVM_DIR/versions/node/v2.0.0/bin:"* ]]'
''')

    def test_deactivation_delegates_and_retains_configuration_functions_and_foreign_path(self):
        self.ok('set -eu; export NVM_DIR="$CUSTOM"; source "$MAIN"; original=$PATH; nvm_activate; nvm_deactivate; [[ $PATH == "$original" && $NVM_DIR == "$CUSTOM" && -z ${NVM_BIN+x} && -z ${NVM_INC+x} && -z ${BASHCMDR_NVM_LOADED+x} ]]; declare -F nvm nvmh nvm_aux_fixture >/dev/null; nvm_activate; [[ $BASHCMDR_NVM_LOADED == 1 ]]')
        self.assertIn('nvm:deactivate --silent',self.trace.read_text());self.assertNotIn('nvm:unload',self.trace.read_text())

    def test_failed_upstream_deactivation_is_propagated_without_false_success(self):
        self.ok('set -eu; source "$MAIN"; nvm_activate; before=$PATH; rc=0; nvm_deactivate || rc=$?; [[ $rc == 31 && $PATH == "$before" && $BASHCMDR_NVM_LOADED == 1 ]]',DEACTIVATE_STATUS=31)

    def test_deactivation_retains_shared_and_foreign_links(self):
        links=self.home/'.local/bin';links.mkdir(parents=True);(links/'node').symlink_to(self.nvm/'versions/node/v2.0.0/bin/node');(links/'foreign').write_text('foreign')
        self.ok('set -eu; source "$MAIN"; nvm_activate; nvm_deactivate')
        self.assertTrue((links/'node').is_symlink());self.assertEqual((links/'foreign').read_text(),'foreign')

    def test_nounset_noargument_wrapper_and_unset_root_hook_remain_guarded(self):
        self.ok('set -eu; source "$MAIN"; nvm() { [[ $# == 0 ]]; }; nvmh; unset NVM_DIR; rc=0; _nvm_post_use_hook || rc=$?; [[ $rc == 1 ]]')

    def test_direct_errexit_missing_diagnosis_reaches_summary_and_fails(self):
        r=self.run_shell('set -eu; source "$MAIN"; nvm_diagnose; echo UNREACHABLE',NVM_DIR=str(self.home/'absent'))
        self.assertEqual(r.returncode,1,r.stdout+r.stderr);self.assertIn('Diagnostic Summary',r.stdout);self.assertIn('Found 2 issues',r.stdout);self.assertNotIn('loadable',r.stdout);self.assertNotIn('UNREACHABLE',r.stdout)

    def test_script_presence_diagnosis_never_claims_loadability_or_sources_it(self):
        r=self.ok('set -eu; source "$MAIN"; nvm_diagnose')
        self.assertIn('activation unverified',r.stdout);self.assertNotIn('loadable',r.stdout);self.assertEqual(self.trace.read_text(),'')

    def test_diagnosis_checks_producer_status_and_does_not_run_node_npm(self):
        for extra in [{'VERSION_STATUS':5},{'EMPTY_VERSION':1},{'LIST_STATUS':7}]:
            r=self.run_shell('set -eu; source "$MAIN"; source "$NVM_DIR/nvm.sh"; nvm_diagnose; echo UNREACHABLE',NVM_DIR=self.custom,**extra)
            self.assertEqual(r.returncode,1,r.stdout+r.stderr);self.assertIn('Diagnostic Summary',r.stdout);self.assertNotIn('UNREACHABLE',r.stdout)

    def test_bare_checkout_help_diagnose_and_explicit_guard_failure(self):
        r=self.ok('set -eu; source "$BARE"; nvm_help; nvm_setup; nvm_diagnose; if nvm_activate; then exit 81; fi')
        self.assertIn('console guard',r.stderr);self.assertNotIn('No such file',r.stderr);self.assertNotIn('command not found',r.stderr)
        direct=self.ok('set -eu; "$BASH_BIN" --noprofile --norc "$BARE" help')
        self.assertIn('https://github.com/nvm-sh/nvm#installing-and-updating',direct.stdout);self.assertNotIn('v0.39.0',direct.stdout)

    def test_configuration_admission_guard_status_and_shell_state_are_preserved(self):
        self.ok('set -eu; source "$MAIN"; here=$PWD; flags=$-; trap "true" USR1; original_trap=$(trap -p USR1); nvm_activate; nvm_deactivate; [[ $PWD == "$here" && $- == "$flags" && $(trap -p USR1) == "$original_trap" ]]')
        for binding in ['readonly NVM_DIR="$CUSTOM"','readonly PATH','declare -a NVM_DIR=("$CUSTOM")','declare -i BASHCMDR_NVM_LOADED=1']:
            self.ok('set -eu; source "$MAIN"; '+binding+'; before=$PATH; if nvm_activate; then exit 81; fi; [[ $PATH == "$before" ]]')
        self.ok('set -eu; source "$MAIN"; rc=0; nvm_activate || rc=$?; [[ $rc == 37 ]]',GUARD_STATUS=37)
        for root in ['relative/path','C:\\native\\path']:
            self.ok('set -eu; source "$MAIN"; if nvm_activate; then exit 81; fi',NVM_DIR=root)


if __name__ == '__main__':
    unittest.main(verbosity=2)
