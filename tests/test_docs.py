#!/usr/bin/env python3
"""Execute README examples against a required console in owned local fixtures."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(os.environ.get('NVM_DOCS_TEST_REPO', pathlib.Path(__file__).resolve().parent.parent))
CONSOLE = None
BASH = os.environ.get('NVM_DOCS_TEST_BASH') or shutil.which('bash')
URLS = {'console': 'https://github.com/bashcmdr/console.git',
        'nvm': 'https://github.com/bashcmdr/cartridge-nvm.git'}


class ReadmeExamples(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bcm-nvm-readme-owned-')
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.home = self.root / 'home space'
        self.tools = self.root / 'tools'
        self.home.mkdir(); self.tools.mkdir()
        self.calls = []
        self.gitlog = self.root / 'git-calls.jsonl'; self.gitlog.write_text('')
        self.trace = self.root / 'forbidden.log'; self.trace.write_text('')
        self.nvmtrace = self.root / 'nvm-calls.log'; self.nvmtrace.write_text('')
        self.env = {'HOME': str(self.home), 'PATH': str(self.tools) + os.pathsep + os.defpath,
                    'TMPDIR': str(self.root), 'LC_ALL': 'C', 'TERM': 'dumb',
                    'BASH_ENV': os.devnull, 'ENV': os.devnull, 'BASHCMDR_QUIET_BOOT': '1',
                    'BASHCMDR_VERBOSITY': '1', 'FORBIDDEN': str(self.trace), 'NVM_CALLS': str(self.nvmtrace),
                    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                    'GIT_ALLOW_PROTOCOL': 'file', 'GIT_TERMINAL_PROMPT': '0'}
        (self.tools / 'bash').symlink_to(BASH)
        for name in ['curl', 'wget', 'sudo', 'service', 'systemctl', 'node', 'npm']:
            path = self.tools / name
            path.write_text('#!' + BASH + '\nprintf "%s\\n" ' + name + ' >> "$FORBIDDEN"\nexit 99\n')
            path.chmod(0o755)
        self.nvmdir = self.home / '.nvm'; self.nvmdir.mkdir()
        self.nodebin = self.nvmdir / 'versions/node/v22.0.0/bin'; self.nodebin.mkdir(parents=True)
        node = self.nodebin / 'node'
        node.write_text('#!' + BASH + '\nprintf "fixture-node\\n"\n'); node.chmod(0o755)
        (self.nvmdir / 'nvm.sh').write_text(r'''
printf 'source\n' >> "$NVM_CALLS"
nvm() {
    printf '%s\n' "$*" >> "$NVM_CALLS"
    case "${1-}" in
        --version) printf 'fixture-nvm\n';;
        list|current) printf 'v22.0.0\n';;
        use) export PATH="$NVM_DIR/versions/node/v22.0.0/bin:$PATH";;
        deactivate) return 0;;
        *) return 2;;
    esac
}
''')
        (self.nvmdir / 'bash_completion').write_text(': # owned completion\n')
        self.protected = [self.home / x for x in ['.bashrc', '.bash_profile', '.profile']]
        for path in self.protected: path.write_text('owned profile sentinel\n')
        self.before = self.snapshot()
        self.sources = {name: self.root / 'sources' / ('source ' + name) for name in URLS}
        for path in self.sources.values(): path.mkdir(parents=True)
        for name in ['bin', 'lib', 'boot']: shutil.copytree(CONSOLE / name, self.sources['console'] / name)
        shutil.copyfile(CONSOLE / 'VERSION', self.sources['console'] / 'VERSION')
        for name in ['main.bashcmdr', 'manifest.json', 'README.md']: shutil.copyfile(REPO / name, self.sources['nvm'] / name)
        templates = self.root / 'empty templates'; templates.mkdir()
        self.env['GIT_TEMPLATE_DIR'] = str(templates)
        real_git = shutil.which('git')
        self.revisions = {}
        for name, path in self.sources.items():
            for args in [('init', '--quiet', str(path)), ('-C', str(path), 'add', '--all'),
                         ('-C', str(path), '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                          'commit', '--quiet', '-m', 'Owned exact source subset')]:
                subprocess.run([real_git, *args], env=self.env, check=True, capture_output=True, timeout=10)
            self.revisions[name] = subprocess.check_output([real_git, '-C', str(path), 'rev-parse', 'HEAD'], env=self.env, text=True).strip()
        wrapper = self.tools / 'git'
        wrapper.write_text('#!' + sys.executable + '\n' +
            'REAL=' + repr(real_git) + '\nROOT=' + repr(str(self.root)) + '\nLOG=' + repr(str(self.gitlog)) +
            '\nSOURCES=' + repr({URLS[n]: str(p) for n, p in self.sources.items()}) + '\n' + r'''
import json, pathlib, subprocess, sys
args = sys.argv[1:]
with open(LOG, 'a') as stream: stream.write(json.dumps(args) + '\n')
if args[:1] == ['clone']:
    assert args[-2] in SOURCES and pathlib.Path(args[-1]).resolve().is_relative_to(ROOT)
    assert args[:-2] in [['clone'], ['clone', '--quiet', '--']]
    args[-2] = SOURCES[args[-2]]
elif len(args) == 5 and args[0] == '-C' and args[2:] == ['rev-parse', '--verify', 'HEAD^{commit}']:
    assert pathlib.Path(args[1]).resolve().is_relative_to(ROOT)
else:
    sys.exit(96)
sys.exit(subprocess.run([REAL, *args]).returncode)
''')
        wrapper.chmod(0o755)

    def snapshot(self):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.protected}

    def blocks(self, title):
        text = (REPO / 'README.md').read_text()
        match = re.search(r'^## ' + re.escape(title) + r'\n(.*?)(?=^## |\Z)', text, re.M | re.S)
        self.assertIsNotNone(match, 'README section missing: ' + title)
        return re.findall(r'^```bash\n(.*?)^```', match.group(1), re.M | re.S)

    def run_example(self, text, cwd=None):
        p = subprocess.run([BASH, '--noprofile', '--norc', '-e', '-o', 'pipefail', '-c', text],
                           cwd=cwd or self.root, env=self.env, text=True, capture_output=True, timeout=15)
        self.calls.append({'script': text, 'cwd': str(cwd or self.root), 'exit': p.returncode,
                           'stdout': p.stdout, 'stderr': p.stderr})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.trace.read_text(), '')
        self.assertEqual(self.snapshot(), self.before)
        return p

    def install_and_boot(self):
        blocks = self.blocks('Install and enable')
        self.assertEqual(len(blocks), 2)
        return '\n'.join(blocks)

    def test_fresh_install_and_current_shell_initialization(self):
        install, boot = self.blocks('Install and enable')
        self.run_example(install + '\nif declare -F nvm >/dev/null; then exit 91; fi\n')
        p = self.run_example(boot + '\n[[ $BASHCMDR_NVM_LOADED == 1 ]]\n')
        self.assertIn('Bash Commander boot status: 0', p.stdout)
        self.assertIn('fixture-nvm', p.stdout)
        metadata = json.loads((self.home / '.bashcmdr/registry/installed/nvm-loader.json').read_text())
        self.assertEqual(metadata['source']['commit'], self.revisions['nvm'])

    def test_version_switch_and_current_shell_deactivation(self):
        text = self.install_and_boot() + '\n' + self.blocks('Use installed Node versions')[0]
        text += '\n[[ $(readlink "$HOME/.local/bin/node") == "$NVM_DIR/versions/node/v22.0.0/bin/node" ]]\n'
        text += self.blocks('Deactivate')[0]
        text += '\n[[ -z ${BASHCMDR_NVM_LOADED-} && -L "$HOME/.local/bin/node" ]]\ndeclare -F nvm >/dev/null\n'
        p = self.run_example(text)
        self.assertIn('fixture-node', p.stdout)

    def test_help_diagnostics_and_selected_console_log(self):
        text = self.install_and_boot() + '\n' + self.blocks('Diagnose and get help')[0]
        p = self.run_example(text)
        self.assertIn('NVM function not loaded; activation unverified', p.stdout)
        self.assertIn('NVM function available; version: fixture-nvm', p.stdout)
        self.assertIn('Console Log', p.stdout)

    def test_bare_inspection_and_sourced_action_limitation(self):
        blocks = self.blocks('Diagnose and get help')
        self.run_example(blocks[1], cwd=self.sources['nvm'])
        self.run_example('source main.bashcmdr activate\n[[ -z ${BASHCMDR_NVM_LOADED-} ]]\ndeclare -F nvm_activate >/dev/null\n', cwd=self.sources['nvm'])
        self.assertEqual(self.nvmtrace.read_text(), '')

    def test_missing_console_input_is_error(self):
        p = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve())],
                           env={'PATH': os.defpath}, text=True, capture_output=True, timeout=10)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('--console-root', p.stderr)
        self.assertNotIn('skipped=', p.stderr)

    def tearDown(self):
        directory = os.environ.get('NVM_DOCS_TEST_EVIDENCE_DIR')
        if directory:
            target = pathlib.Path(directory) / self.id().split('.')[-1]
            target.mkdir(parents=True, exist_ok=True)
            data = {'calls': self.calls, 'source_files': {'README.md': hashlib.sha256((REPO / 'README.md').read_bytes()).hexdigest(),
                    'main.bashcmdr': hashlib.sha256((REPO / 'main.bashcmdr').read_bytes()).hexdigest()},
                    'owned_fixture_commits': self.revisions, 'intercepted_git': self.gitlog.read_text(),
                    'forbidden': self.trace.read_text(), 'nvm_calls': self.nvmtrace.read_text(),
                    'protected_before': self.before, 'protected_after': self.snapshot(), 'bash': BASH}
            (target / 'records.json').write_text(json.dumps(data, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--console-root')
    options, remaining = parser.parse_known_args()
    if not options.console_root: parser.error('--console-root is required; missing console inputs must not become a skipped pass')
    CONSOLE = pathlib.Path(options.console_root).resolve()
    if not all((CONSOLE / p).is_file() for p in ['VERSION', 'bin/bashcmdr', 'boot/shell-init.bashcmdr', 'lib/core.bashcmdr']):
        parser.error('--console-root must name a complete selected console source')
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
