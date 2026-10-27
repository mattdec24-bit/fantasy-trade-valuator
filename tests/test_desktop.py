"""Offline desktop boundary tests; no real Keychain item or ESPN credentials."""
from io import BytesIO, StringIO
from contextlib import redirect_stdout, redirect_stderr
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from app import App, create_server
from desktop import Desktop, Settings, isolate_environment
from evaluator import ocr
from evaluator.sources import demo


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(Path(self.temp.name).resolve() / 'Trade Room')
        self.desktop = Desktop(self.settings)
        self.state = App(demo())
        self.credentials = {'year':'2026', 'league_id':'123456', 's2':'synthetic-only', 'swid':'{synthetic}'}

    def test_save_status_welcome_and_demo_never_read_keychain_or_connect(self):
        with patch.object(self.settings, 'keychain') as keychain, patch('desktop.load_espn') as network:
            self.assertFalse(self.desktop.status()['configured'])
            self.desktop.action({'action':'save', 'espn':self.credentials, 'storage':'file'}, self.state)
            self.desktop.action({'action':'welcome'}, self.state)
            self.desktop.action({'action':'demo'}, self.state)
            status = self.desktop.status()
            self.assertTrue(status['configured'])
            self.assertTrue(status['welcomed'])
            self.assertFalse(any(self.credentials[k] in json.dumps(status) for k in ('league_id', 's2', 'swid')))
            network.assert_not_called(); keychain.assert_not_called()
        self.assertEqual(stat.S_IMODE(self.settings.directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.settings.path.stat().st_mode), 0o600)
        self.assertEqual(self.settings.credentials(), self.credentials)

    def test_only_explicit_load_can_read_espn_and_failure_keeps_snapshot(self):
        self.settings.save(self.credentials, 'file')
        def load():
            self.assertEqual(os.environ['ESPN_S2'], 'synthetic-only')
            return demo()
        with patch('desktop.load_espn', side_effect=load) as network:
            self.desktop.action({'action':'espn'}, self.state)
            network.assert_called_once()
        self.assertFalse(any(k.startswith('ESPN_') for k in os.environ))
        league = self.state.league
        with patch('desktop.load_espn', side_effect=ValueError('PRIVATE-ERROR')):
            with self.assertRaisesRegex(ValueError, 'ESPN could not load') as caught:
                self.desktop.action({'action':'espn'}, self.state)
            self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertIs(self.state.league, league)
        self.desktop.action({'action':'forget'}, self.state)
        self.assertFalse(self.settings.status()['configured'])
        self.assertNotIn('synthetic-only', self.settings.path.read_text())

    def test_keychain_default_has_no_secret_file_and_read_is_explicit(self):
        with patch.object(self.settings, 'keychain', return_value=self.credentials) as keychain:
            self.settings.save(self.credentials, 'keychain')
            self.assertEqual(keychain.call_args.args, ('save', self.credentials))
            keychain.reset_mock()
            self.settings.status(); keychain.assert_not_called()
            self.assertNotIn('synthetic-only', self.settings.path.read_text())
            self.assertEqual(self.settings.credentials(), self.credentials)
            keychain.assert_called_once_with('read', account=self.settings.read()['keychain_account'])
            self.settings.forget()
            self.assertEqual(keychain.call_args.args, ('delete',))

    def test_config_rejects_links_invalid_values_and_atomic_failure(self):
        self.settings.save(self.credentials, 'file')
        pristine = self.settings.path.read_bytes()
        with patch('desktop.os.replace', side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError): self.settings.welcome()
        self.assertEqual(self.settings.path.read_bytes(), pristine)
        self.assertEqual(list(self.settings.directory.iterdir()), [self.settings.path])
        for edits in ({'year':'wrong'}, {'s2':'secret\r\nHeader'}, {'s2':'cookie; injection'}, {'swid':''}):
            with self.assertRaises(ValueError): self.settings.save(self.credentials | edits, 'file')
            self.assertEqual(self.settings.path.read_bytes(), pristine)
        self.settings.path.unlink()
        target = Path(self.temp.name) / 'target'; target.write_text('unchanged')
        self.settings.path.symlink_to(target)
        with self.assertRaises(ValueError): self.settings.status()
        self.assertEqual(target.read_text(), 'unchanged')

    def test_inherited_provider_credentials_and_proxies_are_cleared(self):
        with patch.dict(os.environ, {'ESPN_S2':'inherited', 'LLM_ENABLED':'true',
                        'LLM_API_KEY':'inherited', 'APP_PUBLIC_ORIGIN':'https://invalid.test',
                        'HTTPS_PROXY':'http://invalid.test', 'DYLD_LIBRARY_PATH':'/invalid',
                        'PYTHONPATH':'/invalid'}, clear=True):
            isolate_environment()
            self.assertEqual(os.environ['LLM_ENABLED'], 'false')
            self.assertEqual(os.environ['PATH'], '/usr/bin:/bin:/usr/sbin:/sbin')
            self.assertFalse(any(k.startswith(('ESPN_', 'APP_', 'DYLD_')) for k in os.environ))
            self.assertNotIn('HTTPS_PROXY', os.environ)
            self.assertNotIn('PYTHONPATH', os.environ)

    def test_native_ocr_receives_only_sanitized_png_over_pipes(self):
        from PIL import Image
        image = BytesIO(); Image.new('RGB', (180, 70), 'white').save(image, 'PNG')
        with patch('evaluator.ocr._native_helper', '/bundled/NativeHelper'), patch('evaluator.ocr.subprocess.run') as run:
            run.return_value.stdout = b'Bennett Vale'
            self.assertTrue(ocr.available())
            self.assertEqual(ocr.extract(image.getvalue()), 'Bennett Vale')
            self.assertEqual(run.call_args.args[0], ['/bundled/NativeHelper', 'ocr'])
            with Image.open(BytesIO(run.call_args.kwargs['input'])) as clean:
                self.assertEqual(clean.info, {})
            self.assertEqual(run.call_args.kwargs['timeout'], 15)

    def test_desktop_http_auth_origin_save_and_no_logging(self):
        server = create_server(port=0, token='synthetic-desktop-token', public_origin='')
        server.RequestHandlerClass.desktop = self.desktop
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        self.addCleanup(thread.join); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        def request(data=None, headers=None):
            body = json.dumps(data).encode() if data is not None else None
            with urlopen(Request(base + '/api/desktop', data=body, headers=headers or {})) as response:
                return json.load(response)
        headers = {'Authorization':'Bearer synthetic-desktop-token', 'Content-Type':'application/json'}
        with self.assertRaises(HTTPError) as error: request()
        self.assertEqual(error.exception.code, 401); error.exception.close()
        with self.assertRaises(HTTPError) as error: request({'action':'demo'}, headers | {'Origin':'https://invalid.test'})
        self.assertEqual(error.exception.code, 403); error.exception.close()
        out = StringIO()
        with redirect_stdout(out), redirect_stderr(out), patch('desktop.load_espn') as network:
            result = request({'action':'save','espn':self.credentials,'storage':'file'}, headers)
            self.assertTrue(result['configured']); network.assert_not_called()
        self.assertEqual(out.getvalue(), '')
        self.assertNotIn('synthetic-only', json.dumps(result))
        with urlopen(base + '/') as response:
            self.assertIn(b'/desktop.js', response.read())


class SettingsTransitionTests(unittest.TestCase):
    """Fault injection at the helper process boundary; never calls Security.framework."""
    def setUp(self):
        import subprocess
        from types import SimpleNamespace
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(Path(self.temp.name).resolve() / 'Trade Room')
        self.old = {'year':'2026', 'league_id':'123456', 's2':'synthetic-old', 'swid':'{old}'}
        self.new = self.old | {'s2':'synthetic-new', 'swid':'{new}'}
        self.slots = {}
        self.calls = []
        self.fail = lambda action, account: False
        self.fail_after_save = False
        def helper(args, **kwargs):
            self.assertEqual(args[0], str(self.settings.helper))
            action, account = args[1].removeprefix('secret-'), args[2]
            self.assertTrue(self.settings.valid_account(account))
            self.calls.append((action, account))
            if self.fail(action, account):
                raise subprocess.CalledProcessError(1, args)
            result = None
            if action == 'save':
                self.slots[account] = json.loads(kwargs['input'])
                if self.fail_after_save:
                    raise subprocess.TimeoutExpired(args, 60)
            elif action == 'read':
                result = self.slots[account]
            elif action == 'delete':
                self.slots.pop(account, None)
            else:
                self.failTest('Unexpected helper action')
            return SimpleNamespace(stdout=json.dumps(result).encode())
        self.process = patch('desktop.subprocess.run', side_effect=helper).start()
        self.addCleanup(patch.stopall)

    def seed(self, storage, legacy=False):
        if legacy:
            self.slots['league'] = self.old.copy()
            self.settings.write({'version':1, 'welcomed':True, 'storage':'keychain'})
        elif storage:
            self.settings.save(self.old, storage)
        self.calls.clear()

    def assert_private_clean(self):
        self.assertEqual(list(self.settings.directory.iterdir()), [self.settings.path])
        self.assertEqual(stat.S_IMODE(self.settings.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.settings.directory.stat().st_mode), 0o700)

    def test_successful_transitions_and_legacy_slot_retirement(self):
        for source, target in [(None,'keychain'), ('file','keychain'), ('keychain','keychain'),
                               ('keychain','file'), ('file','file')]:
            with self.subTest(source=source, target=target):
                self.settings.forget(); self.seed(source)
                self.settings.save(self.new, target)
                self.assertEqual(self.settings.credentials(), self.new)
                self.assertEqual(len(self.slots), int(target == 'keychain'))
                self.assertFalse(self.settings.status()['cleanup_pending'])
                self.assert_private_clean()
                if target == 'keychain':
                    self.assertNotIn('synthetic-new', self.settings.path.read_text())
        self.settings.forget(); self.seed('keychain', legacy=True)
        self.settings.save(self.new, 'keychain')
        self.assertNotIn('league', self.slots)
        self.assertEqual(self.settings.credentials(), self.new)
        self.settings.forget()
        self.assertFalse(self.settings.status()['configured'])
        self.assertEqual(self.slots, {})

    def test_metadata_replace_failure_never_deletes_active_credentials(self):
        real_replace = os.replace
        for source, target, failure_at in [('file','file',1), ('keychain','file',1),
                ('file','keychain',1), ('file','keychain',2),
                ('keychain','keychain',1), ('keychain','keychain',2),
                (None,'keychain',2)]:
            with self.subTest(source=source, target=target, failure_at=failure_at):
                self.settings.forget(); self.seed(source)
                previous = self.settings.read(); slots = self.slots.copy()
                calls = 0
                def replace(*args):
                    nonlocal calls
                    calls += 1
                    if calls == failure_at: raise OSError('injected metadata failure')
                    return real_replace(*args)
                with patch('desktop.os.replace', side_effect=replace):
                    with self.assertRaises(OSError): self.settings.save(self.new, target)
                self.assertEqual(self.settings.read(), previous)
                self.assertEqual(self.slots, slots)
                if source: self.assertEqual(self.settings.credentials(), self.old)
                self.assert_private_clean()

    def test_helper_save_failure_and_timeout_preserve_previous_and_remove_stage(self):
        for source in [None, 'file', 'keychain']:
            for after in [False, True]:
                with self.subTest(source=source, timeout_after_create=after):
                    self.settings.forget(); self.seed(source)
                    previous = self.settings.read(); slots = self.slots.copy()
                    self.fail = lambda action, account: action == 'save' and not after
                    self.fail_after_save = after
                    with self.assertRaisesRegex(ValueError, 'Keychain access'):
                        self.settings.save(self.new, 'keychain')
                    self.fail = lambda *_: False; self.fail_after_save = False
                    self.assertEqual(self.settings.read(), previous)
                    self.assertEqual(self.slots, slots)
                    self.assert_private_clean()

    def test_failed_forget_metadata_preserves_file_and_keychain(self):
        for source in ['file', 'keychain']:
            with self.subTest(source=source):
                self.settings.forget(); self.seed(source)
                previous = self.settings.path.read_bytes(); slots = self.slots.copy()
                with patch('desktop.os.replace', side_effect=OSError('injected forget failure')):
                    with self.assertRaises(OSError): self.settings.forget()
                self.assertEqual(self.settings.path.read_bytes(), previous)
                self.assertEqual(self.slots, slots)
                self.assertEqual(self.settings.credentials(), self.old)
                self.assert_private_clean()

    def test_cleanup_failure_is_journaled_and_retryable_after_commit(self):
        for target in ['file', 'keychain', None]:
            with self.subTest(target=target):
                self.settings.forget(); self.seed('keychain', legacy=True)
                self.fail = lambda action, account: action == 'delete'
                if target: self.settings.save(self.new, target)
                else: self.settings.forget()
                self.assertEqual(self.settings.read()['storage'], target)
                self.assertTrue(self.settings.status()['cleanup_pending'])
                self.assertIn('league', self.slots)
                if target: self.assertEqual(self.settings.credentials(), self.new)
                self.fail = lambda *_: False
                # New instance models retry after app restart, without in-memory state.
                restarted = Settings(self.settings.directory)
                restarted.forget()
                self.assertEqual(self.slots, {})
                self.assertFalse(restarted.status()['cleanup_pending'])
                self.assert_private_clean()

    def test_failed_rollback_cleanup_keeps_old_active_and_stage_durably_referenced(self):
        self.seed('keychain', legacy=True)
        real_replace = os.replace; writes = 0
        def replace(*args):
            nonlocal writes
            writes += 1
            if writes >= 2: raise OSError('injected commit and rollback failure')
            return real_replace(*args)
        self.fail = lambda action, account: action == 'delete'
        with patch('desktop.os.replace', side_effect=replace):
            with self.assertRaises(OSError): self.settings.save(self.new, 'keychain')
        self.assertEqual(self.settings.credentials(), self.old)
        self.assertEqual(self.settings.read()['keychain_account'] if 'keychain_account' in self.settings.read() else 'league', 'league')
        self.assertEqual(set(self.slots), {'league', *self.settings.read()['keychain_cleanup']})
        self.assertTrue(self.settings.status()['cleanup_pending'])
        self.fail = lambda *_: False
        self.settings.save(self.new, 'file')
        self.assertEqual(self.settings.credentials(), self.new)
        self.assertEqual(self.slots, {})
        self.assert_private_clean()

    def test_successful_cleanup_with_failed_journal_write_is_safe_to_repeat(self):
        self.seed('keychain', legacy=True)
        real_replace = os.replace; writes = 0
        def replace(*args):
            nonlocal writes
            writes += 1
            if writes == 2: raise OSError('injected cleanup journal failure')
            return real_replace(*args)
        with patch('desktop.os.replace', side_effect=replace):
            self.settings.save(self.new, 'file')
        self.assertEqual(self.slots, {})
        self.assertEqual(self.settings.credentials(), self.new)
        self.assertTrue(self.settings.status()['cleanup_pending'])
        self.settings.forget()  # Missing-item delete succeeds, as in the native helper.
        self.assertFalse(self.settings.status()['cleanup_pending'])
        self.assert_private_clean()

    def test_invalid_cleanup_metadata_is_rejected_before_helper_access(self):
        for pending in [['other-app'], 'league', ['league']]:
            self.settings.write({'version':1, 'welcomed':True, 'storage':'keychain',
                                 'keychain_cleanup':pending})
            with self.assertRaises(ValueError): self.settings.status()
        self.process.assert_not_called()

    def test_file_flush_failure_cleans_temp_and_preserves_active_state(self):
        real_fsync = os.fsync
        for source, target, failure_at in [('file','file',1), ('keychain','file',1),
                                           ('file','keychain',2), ('keychain','keychain',2)]:
            with self.subTest(source=source, target=target):
                self.settings.forget(); self.seed(source)
                previous = self.settings.read(); slots = self.slots.copy(); flushes = 0
                def fsync(fd):
                    nonlocal flushes
                    flushes += 1
                    if flushes == failure_at: raise OSError('injected flush failure')
                    return real_fsync(fd)
                with patch('desktop.os.fsync', side_effect=fsync):
                    with self.assertRaises(OSError): self.settings.save(self.new, target)
                self.assertEqual(self.settings.read(), previous)
                self.assertEqual(self.slots, slots)
                self.assertEqual(self.settings.credentials(), self.old)
                self.assert_private_clean()
