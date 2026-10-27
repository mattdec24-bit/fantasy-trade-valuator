"""Synthetic release metadata and packaging boundaries; no remote calls/assets."""
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import updates
from version import VERSION, version_tuple
from scripts.build_macos import external_path
from scripts.packaging_files import bundle_files
from scripts import release_preflight

ROOT = Path(__file__).resolve().parent.parent


class UpdateTests(unittest.TestCase):
    def setUp(self):
        version = patch('updates.VERSION', '1.0.0')
        version.start(); self.addCleanup(version.stop)

    def response(self, **changes):
        return BytesIO(json.dumps({'tag_name':'v1.0.1', 'draft':False, 'prerelease':False,
            'html_url':'https://untrusted.invalid/payload', 'body':'<script>untrusted</script>',
            'assets':[{'browser_download_url':'https://untrusted.invalid/payload'}]} | changes).encode())

    def test_disabled_check_and_status_never_create_a_transport(self):
        with patch('updates.repository', return_value=None), patch('updates.build_opener') as network:
            self.assertFalse(updates.status()['enabled'])
            self.assertEqual(updates.check()['state'], 'disabled')
            network.assert_not_called()

    def test_configured_status_does_not_connect(self):
        with patch('updates.repository', return_value='example/synthetic'), patch('updates.build_opener') as network:
            self.assertTrue(updates.status()['enabled'])
            network.assert_not_called()

    def test_explicit_check_has_no_secrets_and_only_fixed_metadata_request(self):
        with patch('updates.repository', return_value='example/synthetic'), patch('updates.build_opener') as network:
            network.return_value.open.return_value = self.response()
            result = updates.check()
            self.assertEqual(result['state'], 'available')
            self.assertEqual(result['release_url'], 'https://github.com/example/synthetic/releases/tag/v1.0.1')
            self.assertNotIn('untrusted', json.dumps(result))
            network.return_value.open.assert_called_once()
            request = network.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, 'https://api.github.com/repos/example/synthetic/releases/latest')
            self.assertEqual(request.get_method(), 'GET')
            self.assertIsNone(request.data)
            self.assertEqual(set(k.lower() for k in request.headers), {'accept', 'user-agent', 'x-github-api-version'})
            self.assertEqual(network.return_value.open.call_args.kwargs['timeout'], 8)
            handlers = network.call_args.args
            self.assertEqual(handlers[0].proxies, {})
            self.assertIsNone(handlers[1]().redirect_request(None, None, 302, '', {}, 'https://invalid.test'))

    def test_numeric_versions_and_no_downgrade(self):
        for tag, state in [('v1.0.0','current'), ('v1.0.1','available'), ('v1.10.0','available')]:
            with self.subTest(tag=tag), patch('updates.repository', return_value='example/synthetic'), patch('updates.build_opener') as network:
                network.return_value.open.return_value = self.response(tag_name=tag)
                self.assertEqual(updates.check()['state'], state)
        with patch('updates.VERSION', '2.0.0'), patch('updates.repository', return_value='example/synthetic'), patch('updates.build_opener') as network:
            network.return_value.open.return_value = self.response()
            self.assertEqual(updates.check()['state'], 'current')

    def test_bad_responses_do_not_expose_data_or_offer_install(self):
        changes = [{'draft':True}, {'prerelease':True}, {'tag_name':'v1.0.1-beta'},
                   {'tag_name':'v01.0.1'}, {'tag_name':'v1.0.1/../../payload'}, {'tag_name':None}]
        for change in changes:
            with self.subTest(change=change), patch('updates.repository', return_value='example/synthetic'), patch('updates.build_opener') as network:
                network.return_value.open.return_value = self.response(**change)
                with self.assertRaisesRegex(ValueError, 'No update was downloaded'):
                    updates.check()
        for response in [BytesIO(b'not json'), BytesIO(b'x' * (updates.MAX_RESPONSE + 1)), BytesIO(b'[]')]:
            with patch('updates.repository', return_value='example/synthetic'), patch('updates.build_opener') as network:
                network.return_value.open.return_value = response
                with self.assertRaises(ValueError): updates.check()

    def test_timeout_404_and_redirect_fail_closed(self):
        from urllib.error import HTTPError
        for error in [TimeoutError('private'), HTTPError('private',404,'private',{},None), HTTPError('private',302,'private',{},None)]:
            with patch('updates.repository', return_value='example/synthetic'), patch('updates.build_opener') as network:
                network.return_value.open.side_effect = error
                with self.assertRaises(ValueError) as caught: updates.check()
                self.assertNotIn('private', str(caught.exception))

    def test_invalid_repository_identifiers_cannot_change_host_or_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / 'release.json'
            for value in ['https://invalid.test/repo', 'owner/repo/extra', 'owner/..', '', 'a/repo?token=x', 'a/repo\n', 123]:
                config.write_text(json.dumps({'repository':value}))
                with self.subTest(value=value), self.assertRaises(ValueError): updates.repository(config)
            config.write_text('{"repository":"example/synthetic"}')
            self.assertEqual(updates.repository(config), 'example/synthetic')

    def test_http_requires_authenticated_explicit_action(self):
        from app import create_server
        from desktop import Desktop
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from unittest.mock import Mock
        import threading
        server = create_server(port=0, token='synthetic-token', public_origin='')
        server.RequestHandlerClass.desktop = Desktop(Mock())
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(thread.join); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        address = f'http://127.0.0.1:{server.server_port}/api/desktop'
        with patch('desktop.updates.check', return_value={'state':'disabled'}) as check:
            for headers, code in [({},401), ({'Authorization':'Bearer synthetic-token', 'Origin':'https://invalid.test'},403)]:
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(address, data=b'{"action":"check-updates"}', headers=headers))
                self.assertEqual(caught.exception.code, code); caught.exception.close()
            check.assert_not_called()
            with urlopen(Request(address, data=b'{"action":"check-updates"}', headers={
                    'Authorization':'Bearer synthetic-token', 'Content-Type':'application/json'})) as response:
                self.assertEqual(json.load(response), {'state':'disabled'})
            check.assert_called_once_with()


class PackagingTests(unittest.TestCase):
    def test_version_and_runtime_manifest(self):
        self.assertGreaterEqual(version_tuple(VERSION), (1,0,0))
        files = bundle_files()
        self.assertTrue({'VERSION','version.py','updates.py','release.json','fixtures/demo.json'} <= set(files))
        self.assertFalse(any('.env' in name or name.startswith(('tests/','private/','.local/')) for name in files))

    def test_unsafe_version_values(self):
        for value in ['1.0', '01.0.0', '1.0.0-beta', 'v1.0.0', '0.0.0', '1.0.0\n', None]:
            with self.subTest(value=value), self.assertRaises(ValueError): version_tuple(value)

    def test_external_output_guard(self):
        for value in [ROOT, ROOT / 'dist', ROOT.parent, ROOT / 'build/cache']:
            with self.subTest(value=value), self.assertRaises(ValueError): external_path(value)
        self.assertEqual(external_path(ROOT.parent / 'synthetic-artifacts'), ROOT.parent / 'synthetic-artifacts')

    def test_new_runtime_file_automatic_and_private_files_links_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'macos').mkdir(); (root / 'static').mkdir()
            (root / 'macos/bundle-files.json').write_text('{"files":[],"directories":{"static":[".js"]}}')
            (root / 'static/new.js').write_text('// synthetic')
            self.assertEqual(bundle_files(root), ['static/new.js'])
            for name in ['.secret.js', 'secret.json', 'symlink.js']:
                path = root / 'static' / name
                if name == 'symlink.js': path.symlink_to(root / 'static/new.js')
                else: path.write_text('synthetic')
                with self.subTest(name=name), self.assertRaises(ValueError): bundle_files(root)
                path.unlink()


class ReleaseGateTests(unittest.TestCase):
    def test_release_requires_matching_version_repository_clean_commit_and_tag(self):
        cases = [
            ('v9.9.9', 'example/synthetic', [], 'Release tag'),
            ('v' + VERSION, None, [], 'Configure'),
            ('v' + VERSION, 'example/synthetic', [' M app.py'], 'clean committed'),
            ('v' + VERSION, 'example/synthetic', ['', 'commit-a', 'commit-b'], 'already exist'),
        ]
        for tag, repo, results, error in cases:
            with self.subTest(error=error), patch('sys.argv', ['release_preflight.py','--tag',tag,'--repository','example/synthetic']), patch.object(release_preflight, 'repository', return_value=repo), patch.object(release_preflight, 'git', side_effect=results):
                with self.assertRaisesRegex(SystemExit, error): release_preflight.main()

    def test_matching_release_gate_is_read_only(self):
        from contextlib import redirect_stdout
        from io import StringIO
        with patch('sys.argv', ['release_preflight.py','--tag','v' + VERSION,'--repository','example/synthetic']), patch.object(release_preflight, 'repository', return_value='example/synthetic'), patch.object(release_preflight, 'git', side_effect=['','commit-a','commit-a']) as git, redirect_stdout(StringIO()):
            release_preflight.main()
        self.assertEqual([call.args for call in git.call_args_list], [
            ('status','--porcelain'), ('rev-parse','--verify','HEAD'),
            ('rev-parse','--verify',f'refs/tags/v{VERSION}^{{commit}}')])
