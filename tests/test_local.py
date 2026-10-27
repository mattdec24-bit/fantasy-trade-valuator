"""Secret-safe local launcher regressions, entirely offline and synthetic."""
from contextlib import redirect_stderr, redirect_stdout
import getpass
from io import StringIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import shlex
import stat
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import warnings

from app import create_server
from scripts import container_start, local

ROOT = Path(__file__).resolve().parent.parent


class LocalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='trade-room test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / '.local'
        self.config_path = self.private / 'config.json'
        for name, value in [('ROOT', self.root), ('PRIVATE', self.private), ('CONFIG', self.config_path)]:
            p = patch.object(local, name, value)
            p.start()
            self.addCleanup(p.stop)

    def quiet(self, action):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = action()
        return result, out.getvalue() + err.getvalue()

    def config(self):
        return self.quiet(local.load_config)[0]

    def test_first_run_private_random_atomic_and_preserved(self):
        first, output = self.quiet(local.load_config)
        self.assertEqual(len(first['token']), 43)
        self.assertNotIn(first['token'], output)
        self.assertEqual(first['espn'], None)
        self.assertEqual(first, local.load_config())
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(self.private.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(self.config_path.stat().st_mode), 0o600)
        self.config_path.unlink()
        second = self.config()
        self.assertNotEqual(first['token'], second['token'])
        self.assertEqual(list(self.private.iterdir()), [self.config_path])
        with patch('scripts.local.os.replace', side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):
                local.save_config(second | {'port': 8001})
        self.assertEqual(local.load_config(), second)
        self.assertEqual(list(self.private.iterdir()), [self.config_path])

    @unittest.skipIf(os.name == 'nt', 'POSIX link/permission checks')
    def test_links_rejected_without_touching_target(self):
        target = self.root / 'target'
        target.write_text('do not modify')
        self.private.mkdir()
        self.config_path.symlink_to(target)
        with self.assertRaises(local.LocalError):
            local.load_config()
        self.assertEqual(target.read_text(), 'do not modify')
        self.config_path.unlink()
        self.private.rmdir()
        self.private.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(local.LocalError):
            local.load_config()

    def test_windows_acl_is_limited_to_current_sid(self):
        config = self.config()
        with patch('scripts.local.os.name', 'nt'), patch('scripts.local.run_quiet', return_value='"local\\member","S-1-5-21-123"\n') as run:
            local.protect(self.config_path)
            self.assertEqual(run.call_args_list[-1].args[0],
                             ['icacls', str(self.config_path), '/inheritance:r', '/grant:r', '*S-1-5-21-123:F'])
            self.assertEqual(run.call_args_list[-2].args[0], ['icacls', str(self.config_path), '/reset'])
        self.assertEqual(local.load_config(), config)

    def test_guided_setup_hides_secrets_and_makes_no_connections(self):
        config = self.config()
        cookies = ('synthetic-$key-"quoted"-\\backslash', '{synthetic-swid}')
        with patch('builtins.input', side_effect=['2026', 'y']), patch('scripts.local.getpass.getpass', side_effect=['123456', *cookies]) as hidden, patch('scripts.local.compose', side_effect=AssertionError('no Docker')), patch('evaluator.sources.urlopen', side_effect=AssertionError('no ESPN')), patch('evaluator.llm.urlopen', side_effect=AssertionError('no provider')):
            result, output = self.quiet(lambda: local.main(['setup-espn']))
        self.assertEqual(result, 0)
        self.assertEqual(hidden.call_count, 3)
        for secret in (*cookies, '123456', config['token']):
            self.assertNotIn(secret, output)
        saved = local.load_config()
        self.assertEqual(saved['espn'], {'year': '2026', 'league_id': '123456', 's2': cookies[0], 'swid': cookies[1]})
        self.assertEqual(saved['token'], config['token'])
        # A rejected input is atomic and does not replace existing working settings.
        with patch('builtins.input', side_effect=['not-a-year', 'n']), patch('scripts.local.getpass.getpass', return_value='123456'):
            result, output = self.quiet(lambda: local.main(['setup-espn']))
        self.assertEqual(result, 1)
        self.assertEqual(local.load_config(), saved)

    def test_hidden_input_never_falls_back_to_echo(self):
        def unavailable(*args):
            warnings.warn('synthetic warning', getpass.GetPassWarning)
            raise AssertionError('must stop before reading stdin')
        with patch('scripts.local.getpass.getpass', side_effect=unavailable):
            with self.assertRaises(local.LocalError):
                local.hidden('Secret: ')

    def test_public_setup_clears_previous_cookies(self):
        config = self.config() | {'espn': {'year': '2026', 'league_id': '123', 's2': 'old', 'swid': 'old'}}
        with patch('builtins.input', side_effect=['2025', 'n']), patch('scripts.local.getpass.getpass', return_value='234'):
            self.quiet(lambda: local.setup_espn(config))
        self.assertEqual(local.load_config()['espn'], {'year': '2025', 'league_id': '234', 's2': '', 'swid': ''})

    def test_container_reads_only_local_config_and_gates_espn_without_provider(self):
        config = self.config() | {'espn': {'year': '2026', 'league_id': '123456', 's2': 'synthetic-${literal}-"\\', 'swid': '{synthetic}'}}
        local.save_config(config)
        inherited = {'APP_ACCESS_TOKEN': 'wrong-token', 'APP_PUBLIC_ORIGIN': 'https://invalid.test',
                     'ESPN_S2': 'wrong-cookie', 'LLM_ENABLED': 'true', 'LLM_API_KEY': 'wrong-key'}
        for source in ('demo', 'espn'):
            observed = {}
            def capture(argv):
                observed.update(os.environ)
                self.assertEqual(argv, ['--host', '0.0.0.0', '--source', source, '--compose-local-bootstrap'])
            with patch.dict(os.environ, inherited, clear=True), patch.object(container_start, 'CONFIG', self.config_path), patch('scripts.container_start.app.main', side_effect=capture):
                self.assertEqual(container_start.main(['--source', source]), 0)
            self.assertEqual(observed['APP_ACCESS_TOKEN'], config['token'])
            self.assertEqual(observed['LLM_ENABLED'], 'false')
            self.assertEqual(observed['LLM_API_KEY'], '')
            if source == 'demo':
                self.assertFalse(any(k.startswith('ESPN_') for k in observed))
            else:
                self.assertEqual(observed['ESPN_S2'], config['espn']['s2'])
                self.assertEqual(observed['ESPN_SWID'], config['espn']['swid'])
        for invalid in ('not json', json.dumps(config | {'espn': None})):
            self.config_path.write_text(invalid)
            with patch.object(container_start, 'CONFIG', self.config_path), patch('scripts.container_start.app.main') as app_main:
                result, output = self.quiet(lambda: container_start.main(['--source', 'espn']))
                self.assertEqual(result, 1)
                self.assertNotIn(config['token'], output)
                app_main.assert_not_called()

    def test_browser_platforms_never_receive_token_in_arguments(self):
        config = self.config()
        url = local.base_url(config) + '/'
        for platform, expected in [('darwin', 'open'), ('linux', 'xdg-open')]:
            with patch('scripts.local.sys.platform', platform), patch('scripts.local.subprocess.run') as run:
                run.return_value.returncode = 0
                _, output = self.quiet(lambda: local.open_browser(config))
                self.assertEqual(run.call_args.args[0], [expected, url])
                self.assertNotIn(config['token'], repr(run.call_args))
                self.assertNotIn(config['token'], output)
                self.assertEqual(run.call_args.kwargs['stdout'], local.subprocess.DEVNULL)
                self.assertEqual(run.call_args.kwargs['stderr'], local.subprocess.DEVNULL)
        with patch('scripts.local.sys.platform', 'win32'), patch('scripts.local.os.startfile', create=True) as start:
            self.quiet(lambda: local.open_browser(config))
            start.assert_called_once_with(url)
            self.assertNotIn(config['token'], repr(start.call_args))
        with patch('scripts.local.sys.platform', 'linux'), patch('scripts.local.subprocess.run', side_effect=OSError('secret error')):
            with self.assertRaises(local.LocalError):
                local.open_browser(config)

    def test_readiness_rejects_wrong_token_source_and_llm(self):
        config = self.config()
        health = {'status': 'ok', 'source': 'synthetic', 'read_only': True, 'llm_enabled': False, 'llm_available': False}
        with patch('scripts.local.request_json', side_effect=[health, {'authenticated': True}]):
            local.wait_ready(config, 'demo', timeout=0)
        for poisoned in (health | {'source': 'espn'}, health | {'llm_enabled': True}, health | {'llm_available': True}, []):
            with patch('scripts.local.request_json', side_effect=[poisoned, {'authenticated': True}]):
                with self.assertRaises(local.LocalError):
                    local.wait_ready(config, 'demo', timeout=0)
        with patch('scripts.local.request_json', side_effect=[health, {'authenticated': False}]):
            with self.assertRaises(local.LocalError):
                local.wait_ready(config, 'demo', timeout=0)

    def test_readiness_never_follows_redirects_or_sends_token_in_request_target(self):
        config = self.config()
        requests = []
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                requests.append((self.path, self.headers.get('Authorization')))
                self.send_response(302)
                self.send_header('Location', '/must-not-follow')
                self.send_header('Content-Length', '0')
                self.end_headers()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config['port'] = server.server_port
            with patch.dict(os.environ, {'HTTP_PROXY':'http://invalid.test', 'NO_PROXY':''}):
                with self.assertRaises(local.LocalError):
                    local.wait_ready(config, 'demo', timeout=0)
            self.assertEqual(requests, [('/health', 'Bearer ' + config['token'])])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    @unittest.skipIf(os.name == 'nt', 'Executable fake harness runs on macOS/Linux; Windows paths are unit-checked')
    def test_fake_docker_full_lifecycle_and_secret_safe_failures(self):
        config = self.config()
        server = create_server(port=0, token=config['token'], source='demo', public_origin='', compose_local_bootstrap=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        config['port'] = server.server_port
        config['espn'] = {'year': '2026', 'league_id': '123456', 's2': '$synthetic-${LLM_API_KEY}-"\\', 'swid': '{synthetic}'}
        local.save_config(config)
        (self.root / 'scripts').mkdir()
        # Keep the test isolated from developer-local compose overrides; only the
        # presence of an env file is relevant to this fake-Docker contract.
        (self.root / 'scripts' / 'compose.env').write_text(
            '# Synthetic test defaults only.\n', encoding='utf-8')
        shutil.copyfile(ROOT / 'scripts' / 'compose-stop.yaml', self.root / 'scripts' / 'compose-stop.yaml')
        shutil.copyfile(ROOT / 'compose.yaml', self.root / 'compose.yaml')
        binary = self.root / 'bin'
        binary.mkdir()
        executable = binary / 'docker'
        # A bundled interpreter can live inside “Trade Room.app”; shebangs
        # cannot quote a path containing spaces. The shim also tests that case.
        executable.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' '
                              + shlex.quote(str(ROOT / 'tests' / 'fake_docker.py')) + ' "$@"\n')
        executable.chmod(0o700)
        # Fake script lives outside repo, so give it the explicit synthetic helper path.
        record = self.root / 'record.jsonl'
        env = {'PATH': str(binary) + os.pathsep + os.environ.get('PATH', ''),
               'PYTHONPATH': str(ROOT), 'FAKE_RECORD': str(record),
               'LLM_ENABLED': 'true', 'LLM_API_KEY': 'inherited-provider-secret',
               'ESPN_S2': 'inherited-espn-secret', 'APP_PUBLIC_ORIGIN': 'https://invalid.test',
               'COMPOSE_FILE': 'bad-override.yaml', 'COMPOSE_PROFILES': 'unsafe',
               'HTTP_PROXY': 'http://invalid.test', 'HTTPS_PROXY': 'http://invalid.test'}
        # The loopback app stands in for the container, whose LLM environment is
        # fixed by Compose rather than the deliberately poisoned parent env.
        with patch.dict(os.environ, env, clear=True), patch('scripts.local.ensure_port_free') as port_check, patch('scripts.local.open_browser') as browser, patch('app.llm.enabled', return_value=False), patch('app.llm.available', return_value=False):
            result, output = self.quiet(lambda: local.main([]))
            self.assertEqual(result, 0, output)
            port_check.assert_called_once_with(server.server_port)
            browser.assert_called_once_with(config)
            row = json.loads(record.read_text().splitlines()[-1])
            service = row['spec']['services']['trade-room']
            self.assertEqual(service['ports'], [f'127.0.0.1:{server.server_port}:8000'])
            self.assertEqual(service['command'][-1], 'demo')
            self.assertEqual(service['environment']['LLM_ENABLED'], 'false')
            self.assertEqual(service['environment']['LLM_API_KEY'], '')
            self.assertFalse(any(k.startswith('ESPN_') for k in service['environment']))
            self.assertNotIn('APP_ACCESS_TOKEN', service['environment'])
            self.assertEqual(service['environment']['APP_PUBLIC_ORIGIN'], '')
            self.assertFalse(row['private_env_keys'])
            self.assertNotIn(config['token'], json.dumps(row['args']))
            self.assertNotIn(config['token'], output)
            result, _ = self.quiet(lambda: local.main(['demo', '--no-open']))
            self.assertEqual(result, 0)
            self.assertEqual(browser.call_count, 1)
            with self.assertRaises(local.LocalError):
                local.wait_ready(config | {'token': 'b' * 43}, 'demo', timeout=0)
            # Explicit source selection still sends no secrets through Docker's
            # environment/argv. The separate bootstrap regression checks reading
            # these values from the private bind mount. No ESPN server starts.
            local.compose(config, 'espn', 'config')
            espn = json.loads(record.read_text().splitlines()[-1])['spec']['services']['trade-room']
            self.assertEqual(espn['command'][-1], 'espn')
            self.assertFalse(any(k.startswith('ESPN_') for k in espn['environment']))
            self.assertEqual(espn['volumes'], service['volumes'])
            # Even Docker output deliberately containing secrets never reaches the terminal.
            with patch.dict(os.environ, {'FAKE_FAIL': '1'}):
                result, output = self.quiet(lambda: local.main(['espn']))
                self.assertEqual(result, 1)
                for secret in (config['token'], config['espn']['s2'], 'inherited-provider-secret'):
                    self.assertNotIn(secret, output)
            result, _ = self.quiet(lambda: local.main(['open']))
            self.assertEqual(result, 0)
            result, _ = self.quiet(lambda: local.main(['stop']))
            self.assertEqual(result, 0)
            self.assertEqual(local.load_config(), config)
            (self.private / 'unrelated').write_text('keep')
            with patch.dict(os.environ, {'FAKE_FAIL': '1'}):
                result, _ = self.quiet(lambda: local.main(['reset']))
                self.assertEqual(result, 1)
                self.assertEqual(local.load_config(), config)
            self.config_path.write_text('{invalid')
            with patch.dict(os.environ, {'FAKE_FAIL': '1'}):
                result, _ = self.quiet(lambda: local.main(['reset']))
                self.assertEqual(result, 1)
                self.assertEqual(self.config_path.read_text(), '{invalid')
            result, _ = self.quiet(lambda: local.main(['reset']))
            self.assertEqual(result, 0)
            self.assertFalse(self.config_path.exists())
            self.assertEqual((self.private / 'unrelated').read_text(), 'keep')
            self.assertNotEqual(self.config()['token'], config['token'])
            # Missing config and missing directory must not create a bind file
            # just to stop. A failed stop preserves the exact pre-reset state.
            self.config_path.unlink()
            for missing_directory in (False, True):
                if missing_directory:
                    (self.private / 'unrelated').unlink()
                    self.private.rmdir()
                for fail in (True, False):
                    with patch.dict(os.environ, {'FAKE_FAIL': '1' if fail else ''}):
                        result, output = self.quiet(lambda: local.main(['reset']))
                    self.assertEqual(result, 1 if fail else 0, output)
                    self.assertFalse(self.config_path.exists())
                    self.assertEqual(self.private.exists(), not missing_directory)
                    last = json.loads(record.read_text().splitlines()[-1])
                    self.assertEqual(last['spec'], {'services': {'trade-room': {'image': 'trade-room-local'}}})

    def test_compose_static_contract_and_ignore_rules(self):
        # JSON is a YAML subset; parsing needs no optional YAML dependency.
        spec = json.loads((ROOT / 'compose.yaml').read_text())
        self.assertEqual(set(spec), {'services'})
        self.assertEqual(set(spec['services']), {'trade-room'})
        service = spec['services']['trade-room']
        self.assertEqual(service['ports'], ['127.0.0.1:${TRADE_ROOM_PORT:-8000}:8000'])
        self.assertNotIn('network_mode', service)
        self.assertEqual(service['volumes'], [{'type':'bind', 'source':'./.local/config.json',
                         'target':'/run/trade-room-config.json', 'read_only':True,
                         'bind':{'create_host_path':False}}])
        self.assertEqual(service['user'], '${TRADE_ROOM_UID:-10001}:${TRADE_ROOM_GID:-10001}')
        self.assertNotIn('APP_ACCESS_TOKEN', service['environment'])
        self.assertFalse(any(k.startswith('ESPN_') for k in service['environment']))
        self.assertEqual(service['environment']['LLM_ENABLED'], 'false')
        self.assertEqual(service['environment']['LLM_PROVIDER'], '')
        self.assertEqual(service['environment']['LLM_API_KEY'], '')
        self.assertTrue(service['read_only'])
        self.assertEqual(service['cap_drop'], ['ALL'])
        self.assertEqual(service['command'][-1], '${TRADE_ROOM_SOURCE:-demo}')
        self.assertEqual(service['restart'], 'no')
        self.assertIn('USER traderoom', (ROOT / 'Dockerfile').read_text())
        for filename in ('.gitignore', '.dockerignore'):
            self.assertIn('.local', (ROOT / filename).read_text())
        ignored = (ROOT / '.dockerignore').read_text().splitlines()
        for entry in ('.git', 'tests', '.github', 'scripts/offline_tests.py', 'scripts/smoke.py',
                      'scripts/make_fixture.py', 'CONTRIBUTING.md', 'VALIDATION.md'):
            self.assertIn(entry, ignored)
        self.assertEqual(json.loads((ROOT / 'scripts' / 'compose-stop.yaml').read_text()),
                         {'services': {'trade-room': {'image': 'trade-room-local'}}})

    @unittest.skipIf(os.name == 'nt', 'POSIX shell wrapper')
    def test_shell_wrapper_handles_spaces_other_cwd_and_exit_status(self):
        launcher = self.root / 'start.sh'
        shutil.copyfile(ROOT / 'start.sh', launcher)
        binary = self.root / 'bin'
        binary.mkdir()
        python = binary / 'python3'
        python.write_text('#!/bin/sh\nif [ "$1" = "-c" ]; then exit 0; fi\nprintf "%s\\n" "$PWD" "$@"\nexit 7\n')
        python.chmod(0o700)
        result = local.subprocess.run(['sh', str(launcher), 'demo', '--no-open'],
                                      cwd=self.root.parent,
                                      env={'PATH': str(binary) + ':/usr/bin:/bin'},
                                      capture_output=True, text=True)
        self.assertEqual(result.returncode, 7)
        lines = result.stdout.splitlines()
        self.assertEqual(Path(lines[0]).resolve(), self.root.resolve())
        self.assertEqual(lines[1:], ['scripts/local.py', 'demo', '--no-open'])
        windows = (ROOT / 'start.cmd').read_text()
        self.assertIn('cd /d "%~dp0"', windows)
        self.assertIn('sys.version_info < (3, 11)', windows)
        self.assertIn('where py', windows)
        self.assertIn('where python3 python3.15 python3.14 python3.13 python3.12 python3.11 python', windows)
        self.assertIn('"%%P" %%V scripts\\local.py %*', windows)
        self.assertIn('"%%P" scripts\\local.py %*', windows)

    @unittest.skipIf(os.name == 'nt', 'POSIX shell wrapper; Windows selection is statically checked')
    def test_shell_wrapper_skips_old_python_and_finds_supported_interpreter(self):
        launcher = self.root / 'start.sh'
        shutil.copyfile(ROOT / 'start.sh', launcher)
        old = self.root / 'old bin'; old.mkdir()
        modern = self.root / 'modern bin'; modern.mkdir()
        (old / 'dirname').symlink_to(shutil.which('dirname'))
        old_python = old / 'python3'
        old_python.write_text('#!/bin/sh\nif [ "$1" = "-c" ]; then exit 1; fi\nexit 99\n')
        old_python.chmod(0o700)
        for name in ('python3.11', 'python3', 'python'):
            python = modern / name
            python.write_text('#!/bin/sh\nif [ "$1" = "-c" ]; then exit 0; fi\nprintf "%s\\n" "$PWD" "$@"\nexit 7\n')
            python.chmod(0o700)
            result = local.subprocess.run(['/bin/sh', str(launcher), 'reset'], cwd=self.root.parent,
                                          env={'PATH': str(old) + os.pathsep + str(modern)},
                                          capture_output=True, text=True)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertEqual(result.stdout.splitlines()[1:], ['scripts/local.py', 'reset'])
            python.unlink()
        result = local.subprocess.run(['/bin/sh', str(launcher)], env={'PATH': str(old)},
                                      capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Install Python 3.11+', result.stderr)

    def test_missing_docker_remote_context_unconfigured_espn_and_port_collision(self):
        config = self.config()
        with patch('scripts.local.shutil.which', return_value=None):
            with self.assertRaises(local.LocalError):
                local.docker_ready({})
        with patch('scripts.local.shutil.which', return_value='/fake/docker'):
            for settings in ({'DOCKER_HOST': 'tcp://remote:2375'}, {'DOCKER_TLS_VERIFY': '1'}):
                with self.assertRaises(local.LocalError):
                    local.docker_ready(settings)
            with patch('scripts.local.run_quiet', return_value='[{"Endpoints":{"docker":{"Host":"ssh://remote"}}}]') as run:
                with self.assertRaises(local.LocalError):
                    local.docker_ready({})
                self.assertEqual(run.call_count, 1)
        with self.assertRaises(local.LocalError):
            local.docker_environment(config, 'espn')
        with local.socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            with self.assertRaises(local.LocalError):
                local.ensure_port_free(occupied.getsockname()[1])
