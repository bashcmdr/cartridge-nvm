#!/usr/bin/env python3
"""Owned-fixture hook tests. sudo is always an inert failure, including red runs."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
SOURCE = pathlib.Path(os.environ.get('NVM_TEST_SOURCE', REPO / 'main.bashcmdr'))
BASH = os.environ.get('NVM_HOOK_TEST_BASH', shutil.which('bash'))
README = pathlib.Path(os.environ.get('NVM_TEST_README', REPO / 'README.md'))
PREFIX = r'''
set -u
source "$TEST_MAIN"
nvm() {
    case "${1-}" in
        use) return "${FAIL_USE:-0}" ;;
        current)
            if [[ ${FAIL_CURRENT:-0} != 0 ]]; then return "$FAIL_CURRENT"; fi
            printf '%s\n' "${CURRENT_VERSION:-v2.0.0}" ;;
        --version) printf 'fixture-nvm\n' ;;
        list) printf 'fixture-list\n' ;;
        *) return "${PASSTHRU_STATUS:-0}" ;;
    esac
}
sudo() { printf 'sudo\n' >> "$TRACE"; return 99; }
find() {
    printf 'find\n' >> "$TRACE"
    [[ ${FORBID_FIND:-0} == 0 ]] || return 98
    [[ $1 == "$HOME/.nvm/"* ]] || return 97
    command find "$@"
}
ln() {
    printf 'ln\n' >> "$TRACE"
    [[ ${FAIL_LN:-0} == 0 ]] || return 13
    command ln "$@"
}
rm() {
    printf 'rm\n' >> "$TRACE"
    [[ ${FAIL_RM:-0} == 0 ]] || return 14
    command rm "$@"
}
mkdir() {
    [[ ${FAIL_MKDIR:-0} == 0 ]] || return 15
    command mkdir "$@"
}
node() { printf 'fixture-node\n'; }
npm() { printf 'fixture-npm\n'; }
'''


class HookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bcm-nvm-hook-')
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.home = self.root / 'home with spaces'
        self.home.mkdir()
        self.nvm = self.home / '.nvm'
        self.nvm.mkdir()
        (self.nvm / 'nvm.sh').write_text(': # fixture only\n')
        self.links = self.home / '.local/bin'
        self.trace = self.root / 'operations.log'
        self.trace.write_text('')
        framework = self.root / 'console'
        library = framework / 'lib'
        library.mkdir(parents=True)
        (library / 'core.bashcmdr').write_text('''
__bashcmdr_info() { :; }
__bashcmdr_success() { :; }
__bashcmdr_error() { printf '%s\\n' "$*" >&2; }
''')
        (library / 'guards.bashcmdr').write_text('bashcmdr_guard_validate() { return 0; }\n')
        cartridge = framework / 'cartridges/nvm-loader'
        cartridge.mkdir(parents=True)
        shutil.copyfile(SOURCE, cartridge / 'main.bashcmdr')
        (cartridge / 'manifest.json').write_text('{}\n')
        self.main = cartridge / 'main.bashcmdr'
        for version in ['v1.0.0', 'v2.0.0']:
            for name in ['node', 'npm']:
                self.executable(version, name)

    def executable(self, version, name):
        path = self.nvm / 'versions/node' / version / 'bin' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\nexit 0\n')
        path.chmod(0o755)
        return path

    def managed(self, name='node', version='v1.0.0'):
        self.links.mkdir(parents=True, exist_ok=True)
        path = self.links / name
        path.symlink_to(self.nvm / 'versions/node' / version / 'bin' / name)
        return path

    def run_hook(self, command='nvmh use v2.0.0', **extra):
        env = {'HOME': str(self.home), 'NVM_DIR': str(self.nvm),
               'PATH': '/usr/bin:/bin', 'TERM': 'dumb', 'LC_ALL': 'C',
               'TEST_MAIN': str(self.main), 'TRACE': str(self.trace)}
        env.update({key: str(value) for key, value in extra.items()})
        return subprocess.run([BASH, '--noprofile', '--norc', '-c',
                               PREFIX + '\n' + command], env=env,
                              capture_output=True, text=True, timeout=5)

    def assert_no_success(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('SUCCESS:', result.stdout)

    def test_default_user_links_without_privilege_or_find(self):
        result = self.run_hook(FORBID_FIND=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.links / 'node').is_symlink())
        self.assertEqual(os.readlink(self.links / 'node'), str(self.nvm / 'versions/node/v2.0.0/bin/node'))
        self.assertNotIn('sudo', self.trace.read_text())
        self.assertNotIn('find', self.trace.read_text())

    def test_configurable_owned_directory(self):
        custom = self.home / 'custom bin'
        result = self.run_hook(BASHCMDR_NVM_LINK_DIR=custom)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((custom / 'node').is_symlink())
        self.assertFalse(self.links.exists())

    def test_switch_with_no_sudo_command_in_path(self):
        tools = self.root / 'minimal tools'
        tools.mkdir()
        for name in ['dirname', 'ln', 'rm', 'mkdir', 'rmdir', 'readlink']:
            executable = shutil.which(name)
            self.assertIsNotNone(executable, name)
            (tools / name).symlink_to(executable)
        self.managed('node')
        self.managed('npm')
        result = self.run_hook(
            'unset -f sudo; hash -r; '
            'if command -v sudo >/dev/null 2>&1; then exit 91; fi; '
            'nvmh use v2.0.0', PATH=tools, FORBID_FIND=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.links / 'node'),
                         str(self.nvm / 'versions/node/v2.0.0/bin/node'))
        self.assertFalse((self.links / '.bashcmdr-nvm.lock').exists())
        self.assertNotIn('sudo', self.trace.read_text())
        self.assertNotIn('find', self.trace.read_text())

    def test_switch_updates_managed_and_removes_only_managed_stale_links(self):
        self.managed()
        old_source = self.executable('v1.0.0', 'old-helper')
        stale = self.managed('old-helper')
        foreign = self.links / 'foreign-helper'
        foreign.symlink_to(self.home / 'unrelated')
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(stale.is_symlink())
        self.assertTrue(old_source.exists())
        self.assertEqual(os.readlink(foreign), str(self.home / 'unrelated'))
        self.assertEqual(os.readlink(self.links / 'node'), str(self.nvm / 'versions/node/v2.0.0/bin/node'))

    def test_foreign_regular_file_is_preserved_and_preflight_aborts(self):
        prior = self.managed('npm')
        node = self.links / 'node'
        node.write_text('foreign-file')
        result = self.run_hook()
        self.assert_no_success(result)
        self.assertEqual(node.read_text(), 'foreign-file')
        self.assertIn('v1.0.0', os.readlink(prior))
        self.assertNotIn('rm', self.trace.read_text())

    def test_foreign_symlink_is_preserved(self):
        self.links.mkdir(parents=True)
        target = self.home / 'other-node'
        target.write_text('foreign-target')
        (self.links / 'node').symlink_to(target)
        result = self.run_hook()
        self.assert_no_success(result)
        self.assertEqual(os.readlink(self.links / 'node'), str(target))
        self.assertEqual(target.read_text(), 'foreign-target')

    def test_broken_foreign_symlink_is_preserved(self):
        self.links.mkdir(parents=True)
        target = self.home / 'missing-node'
        (self.links / 'node').symlink_to(target)
        self.assert_no_success(self.run_hook())
        self.assertEqual(os.readlink(self.links / 'node'), str(target))

    def test_lookalike_escaping_target_is_foreign(self):
        self.links.mkdir(parents=True)
        target = str(self.nvm / 'versions/node/v1.0.0/bin/../../../../outside/node')
        (self.links / 'node').symlink_to(target)
        self.assert_no_success(self.run_hook())
        self.assertEqual(os.readlink(self.links / 'node'), target)

    def test_same_version_is_idempotent(self):
        first = self.run_hook()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue((self.links / 'node').is_symlink())
        inode = (self.links / 'node').lstat().st_ino
        operations = self.trace.read_text()
        second = self.run_hook()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((self.links / 'node').lstat().st_ino, inode)
        self.assertEqual(self.trace.read_text(), operations)

    def test_missing_version_directory_preserves_existing_links(self):
        old = self.managed()
        self.assert_no_success(self.run_hook(CURRENT_VERSION='v9.9.9'))
        self.assertIn('v1.0.0', os.readlink(old))

    def test_no_executables_preserves_existing_links(self):
        old = self.managed()
        for path in (self.nvm / 'versions/node/v2.0.0/bin').iterdir():
            path.unlink()
        result = self.run_hook()
        self.assertEqual(result.returncode, 127, result.stderr)
        self.assertIn('v1.0.0', os.readlink(old))

    def test_failed_nvm_use_does_not_run_hook(self):
        result = self.run_hook(FAIL_USE=17)
        self.assertEqual(result.returncode, 17)
        self.assertEqual(self.trace.read_text(), '')
        self.assertFalse(self.links.exists())

    def test_failed_current_query_is_propagated(self):
        result = self.run_hook(FAIL_CURRENT=23)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertFalse(self.links.exists())

    def test_link_failure_is_nonzero_without_success(self):
        self.assert_no_success(self.run_hook(FAIL_LN=1))

    def test_remove_failure_is_nonzero_and_preserves_link(self):
        old = self.managed()
        self.assert_no_success(self.run_hook(FAIL_RM=1))
        self.assertIn('v1.0.0', os.readlink(old))

    def test_missing_nvm_function_is_an_error(self):
        self.assert_no_success(self.run_hook('unset -f nvm; _nvm_post_use_hook'))

    def test_no_active_managed_version_is_an_error(self):
        for version in ['none', 'system', '../outside']:
            with self.subTest(version=version):
                self.assert_no_success(self.run_hook(CURRENT_VERSION=version))
                self.assertFalse(self.links.exists())

    def test_system_directory_is_rejected_before_operations(self):
        self.assert_no_success(self.run_hook(BASHCMDR_NVM_LINK_DIR='/usr/local/bin'))
        self.assertEqual(self.trace.read_text(), '')

    def test_symlink_link_directory_is_rejected(self):
        foreign = self.home / 'foreign-directory'
        foreign.mkdir()
        self.links.parent.mkdir(parents=True)
        self.links.symlink_to(foreign, target_is_directory=True)
        self.assert_no_success(self.run_hook())
        self.assertEqual(list(foreign.iterdir()), [])

    def test_existing_lock_is_not_removed(self):
        lock = self.links / '.bashcmdr-nvm.lock'
        lock.mkdir(parents=True)
        (lock / 'owner').write_text('other-hook')
        self.assert_no_success(self.run_hook())
        self.assertEqual((lock / 'owner').read_text(), 'other-hook')

    def test_diagnose_does_not_probe_sudo(self):
        result = self.run_hook('nvm_diagnose')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('sudo', self.trace.read_text())

    def test_passthrough_and_no_arguments_preserve_nvm_status(self):
        result = self.run_hook('nvmh list')
        self.assertEqual(result.stdout.strip(), 'fixture-list')
        self.assertEqual(self.trace.read_text(), '')
        self.assertEqual(self.run_hook('nvmh', PASSTHRU_STATUS=4).returncode, 4)

    def test_missing_nvm_script_is_an_error(self):
        (self.nvm / 'nvm.sh').unlink()
        self.assert_no_success(self.run_hook())

    def test_hidden_executable_is_linked(self):
        self.executable('v2.0.0', '.hidden-helper')
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.links / '.hidden-helper').is_symlink())

    def test_mkdir_failure_is_nonzero(self):
        self.assert_no_success(self.run_hook(FAIL_MKDIR=1))

    def test_readme_has_no_broad_privilege_recipe(self):
        text = README.read_text()
        self.assertNotIn('NOPASSWD', text)
        self.assertNotIn('sudo chmod', text)
        self.assertNotIn('sudo tee', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
