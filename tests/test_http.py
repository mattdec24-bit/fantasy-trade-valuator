import json
import errno
from http.client import HTTPConnection
import os
import re
import socket
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from app import App, create_server
from evaluator.sources import demo


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=create_server(port=0,token='')
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def request(self,path,data=None,headers=None,method=None):
        headers=headers or {}
        if data is not None:
            headers={'Content-Type':'application/json'}|headers
            data=json.dumps(data).encode()
        req=Request(self.base+path,data=data,headers=headers,method=method)
        try:
            with urlopen(req,timeout=20) as response:return response.status,response.read(),response.headers
        except HTTPError as error:
            with error:return error.code,error.read(),error.headers

    def test_health_and_local_static_security(self):
        code,body,headers=self.request('/health');self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['source'],'synthetic');self.assertTrue(json.loads(body)['read_only'])
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertIn("connect-src 'self'",headers['Content-Security-Policy'])
        self.assertEqual(self.request('/')[0],200)
        self.assertEqual(self.request('/../.env')[0],404)
        self.assertEqual(self.request('/api/league')[0],200)

    def test_no_write_routes_and_cross_origin_or_rebinding(self):
        self.assertEqual(self.request('/api/trade',{},method='POST')[0],404)
        self.assertEqual(self.request('/api/league',{},method='PUT')[0],405)
        self.assertEqual(self.request('/api/evaluate',{},headers={'Origin':'https://untrusted.invalid'})[0],403)
        self.assertEqual(self.request('/health',headers={'Host':'untrusted.invalid'})[0],403)

    def test_compose_local_bootstrap_requires_nonce_and_same_origin(self):
        token = 'synthetic-bootstrap-token-'.ljust(43, 'x')
        server = create_server(port=0, token=token, public_origin='', compose_local_bootstrap=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        original = self.base; self.base = f'http://127.0.0.1:{server.server_port}'
        output = StringIO()
        try:
            with redirect_stderr(output), redirect_stdout(output):
                code, page, page_headers = self.request('/')
                self.assertEqual(code, 200)
                self.assertNotIn(token.encode(), page)
                nonce = re.search(rb'<meta name="trade-room-bootstrap" content="([A-Za-z0-9_-]{43})">', page)[1].decode()
                self.assertNotEqual(nonce, token)
                headers = {'X-Trade-Room-Bootstrap': nonce, 'Sec-Fetch-Site': 'same-origin'}
                for same_origin in (headers, headers | {'Origin': self.base},
                                    {'X-Trade-Room-Bootstrap': nonce, 'Origin': self.base}):
                    code, body, response_headers = self.request('/api/local-bootstrap', headers=same_origin)
                    self.assertEqual(code, 200)
                    self.assertEqual(json.loads(body), {'token': token})
                    self.assertEqual(response_headers['Cache-Control'], 'no-store')
                    self.assertEqual(response_headers['Referrer-Policy'], 'no-referrer')
                    self.assertFalse(any(name.lower().startswith('access-control-') for name in response_headers))
                self.assertEqual(page_headers['Cache-Control'], 'no-store')
                self.assertEqual(page_headers['Referrer-Policy'], 'no-referrer')
                for rejected in ({}, {'Sec-Fetch-Site': 'same-origin'},
                                 {'X-Trade-Room-Bootstrap': nonce},
                                 headers | {'X-Trade-Room-Bootstrap': 'wrong'},
                                 headers | {'X-Trade-Room-Bootstrap': '\u00ff'},
                                 headers | {'Origin': 'http://evil.invalid'},
                                 headers | {'Origin': 'null'},
                                 headers | {'Origin': self.base + '/'},
                                 headers | {'Host': 'evil.invalid'},
                                 headers | {'Sec-Fetch-Site': 'cross-site'},
                                 headers | {'Sec-Fetch-Site': 'same-site', 'Origin': self.base},
                                 headers | {'Sec-Fetch-Site': 'none'},
                                 headers | {'Forwarded': 'host=public.invalid'},
                                 headers | {'X-Forwarded-Host': 'public.invalid'},
                                 headers | {'X-Forwarded-Proto': 'https'},
                                 headers | {'X-Forwarded-For': '192.0.2.1'}):
                    with self.subTest(headers=rejected):
                        code, body, _ = self.request('/api/local-bootstrap', headers=rejected)
                        self.assertIn(code, (400, 403))
                        self.assertNotIn(token.encode(), body)
                self.assertEqual(self.request('/api/local-bootstrap', {}, headers=headers)[0], 403)
                code, body, response_headers = self.request('/api/local-bootstrap', headers={
                    'Origin': 'http://evil.invalid', 'Access-Control-Request-Method': 'GET',
                    'Access-Control-Request-Headers': 'x-trade-room-bootstrap'}, method='OPTIONS')
                self.assertNotEqual(code, 200)
                self.assertNotIn(token.encode(), body)
                self.assertIsNone(response_headers.get('Access-Control-Allow-Origin'))
                self.assertEqual(self.request('/api/league')[0], 401)
                self.assertEqual(self.request('/api/session', headers={'Authorization': 'Bearer ' + token})[0], 200)
                # Duplicate headers must not become an alternate trust path.
                for name, value in [('X-Trade-Room-Bootstrap', nonce), ('Sec-Fetch-Site', 'same-origin'),
                                    ('Origin', self.base), ('Host', f'127.0.0.1:{server.server_port}')]:
                    connection = HTTPConnection('127.0.0.1', server.server_port)
                    try:
                        connection.putrequest('GET', '/api/local-bootstrap')
                        for key, item in headers.items(): connection.putheader(key, item)
                        connection.putheader(name, value)
                        if name == 'Origin': connection.putheader(name, value)
                        connection.endheaders()
                        response = connection.getresponse()
                        self.assertIn(response.status, (400, 403))
                        self.assertNotIn(token.encode(), response.read())
                    finally:
                        connection.close()
            self.assertEqual(output.getvalue(), '')
        finally:
            self.base = original; server.shutdown(); server.server_close(); thread.join()

    def test_manual_bootstrap_disabled_and_public_configuration_rejected(self):
        self.assertNotIn(b'trade-room-bootstrap', self.request('/')[1])
        self.assertEqual(self.request('/api/local-bootstrap', headers={
            'X-Trade-Room-Bootstrap': 'x' * 43, 'Sec-Fetch-Site': 'same-origin'})[0], 403)
        # Reject unsafe configuration before loading any ESPN source.
        with patch('app.load_espn', side_effect=AssertionError('must not load ESPN')):
            for settings in ({'public_origin': 'http://localhost'},
                             {'allowed_hosts': ['localhost', '192.0.2.1']},
                             {'allowed_hosts': ['public.invalid']}, {'host': '192.0.2.1'},
                             {'token': ''}):
                with self.subTest(settings=settings), self.assertRaises(ValueError):
                    create_server(**({'port': 0, 'source': 'espn', 'token': 'x' * 43,
                                      'public_origin': '', 'compose_local_bootstrap': True} | settings))
            with patch.dict(os.environ, {'APP_PUBLIC_ORIGIN': 'https://public.invalid'}):
                with self.assertRaises(ValueError):
                    create_server(port=0, token='x' * 43, source='espn', compose_local_bootstrap=True)

    def test_direct_origin_requires_exact_scheme_host_and_port(self):
        proposal = {'team_id':'harbor','other_id':'orbit','give':['harbor-2'],'receive':['orbit-5']}
        authority = self.base.removeprefix('http://')
        for origin in (None, self.base):
            headers = {} if origin is None else {'Origin':origin}
            self.assertEqual(self.request('/api/evaluate', proposal, headers=headers)[0], 200)
        for origin in ('https://' + authority, 'http://localhost:' + str(self.server.server_port),
                       'http://127.0.0.1:1'):
            with self.subTest(origin=origin):
                self.assertEqual(self.request('/api/evaluate', proposal, headers={'Origin':origin})[0], 403)
        for origin in ('null', '', self.base + '/', self.base + '?', self.base + '#',
                       'http://user@' + authority, 'http://user:pass@' + authority,
                       'http://' + authority + ' ', 'http://127.0.0.1:bad',
                       'http://[::1]garbage', 'http://[::1]garbage:80'):
            with self.subTest(origin=origin):
                self.assertEqual(self.request('/api/evaluate', proposal, headers={'Origin':origin})[0], 400)
        # Untrusted forwarding headers cannot change the effective scheme or host.
        self.assertEqual(self.request('/api/evaluate', proposal, headers={
            'Origin':'https://' + authority, 'X-Forwarded-Proto':'https',
            'X-Forwarded-Host':authority, 'Forwarded':f'proto=https;host="{authority}"'})[0], 403)
        self.assertEqual(self.request('/health', headers={'Host':'localhost', 'Origin':'http://localhost:80'})[0], 200)

    def test_trusted_public_origin_for_https_proxy(self):
        with patch.dict(os.environ, {'APP_PUBLIC_ORIGIN':'https://trades.example:8443'}):
            server = create_server(port=0, token='', allowed_hosts=['trades.example'])
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        original = self.base;self.base = f'http://127.0.0.1:{server.server_port}'
        proposal = {'team_id':'harbor','other_id':'orbit','give':['harbor-2'],'receive':['orbit-5']}
        try:
            headers = {'Host':'trades.example:8443', 'Origin':'https://trades.example:8443'}
            self.assertEqual(self.request('/api/evaluate', proposal, headers=headers)[0], 200)
            for origin in ('http://trades.example:8443', 'https://trades.example', self.base,
                           'https://other.example:8443'):
                self.assertEqual(self.request('/api/evaluate', proposal, headers=headers | {'Origin':origin})[0], 403)
            self.assertEqual(self.request('/health', headers=headers | {'Host':'untrusted.invalid'})[0], 403)
            self.assertEqual(self.request('/health', headers={'Host':'trades.example:8443'})[0], 200)
        finally:
            self.base = original;server.shutdown();server.server_close();thread.join()
        with patch.dict(os.environ, {'APP_PUBLIC_ORIGIN':'http://ignored.example'}):
            server = create_server(port=0, token='', allowed_hosts=['trades.example'],
                                   public_origin='https://trades.example')
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        self.base = f'http://127.0.0.1:{server.server_port}'
        try:
            headers = {'Host':'TRADES.EXAMPLE:443', 'Origin':'https://trades.example:443'}
            self.assertEqual(self.request('/health', headers=headers)[0], 200)
            self.assertEqual(self.request('/health', headers=headers | {'Origin':'http://ignored.example'})[0], 403)
        finally:
            self.base = original;server.shutdown();server.server_close();thread.join()

    def test_public_origin_rejects_other_allowed_host(self):
        public_origin = 'https://trades.example:8443'
        for config in ({}, {'public_origin':public_origin}):
            with self.subTest(config=config), patch.dict(os.environ, {'APP_PUBLIC_ORIGIN':public_origin}):
                server = create_server(port=0, token='',
                                       allowed_hosts=['trades.example', 'other.example', '127.0.0.1'], **config)
                thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
                original = self.base;self.base = f'http://127.0.0.1:{server.server_port}'
                try:
                    for host in ('other.example:8443', f'127.0.0.1:{server.server_port}'):
                        for origin in (None, public_origin):
                            headers = {'Host':host}
                            if origin is not None:
                                headers['Origin'] = origin
                            with self.subTest(host=host, origin=origin):
                                self.assertEqual(self.request('/health', headers=headers)[0], 403)
                                self.assertEqual(self.request('/api/league', headers=headers)[0], 403)
                finally:
                    self.base = original;server.shutdown();server.server_close();thread.join()

    def test_invalid_public_origin_rejected_before_source_load(self):
        for origin in ('ftp://trades.example', 'null', 'https://user@trades.example',
                       'https://trades.example/', 'https://trades.example?', 'https://trades.example#',
                       ' https://trades.example', 'https://trades.example:bad',
                       'https://trades.example:', 'https://trades.example:65536', 'https://',
                       'https://[::1]garbage', 'https://[::1]garbage:443'):
            with self.subTest(origin=origin), patch('app.load_espn') as load:
                with self.assertRaises(ValueError):
                    create_server(port=0, source='espn', token='', public_origin=origin)
                load.assert_not_called()

    def test_ipv6_loopback_binding_and_origin(self):
        with patch('app.socket.has_ipv6', False):
            with self.assertRaisesRegex(ValueError, 'IPv6 binding is unavailable'):
                create_server(host='::1', port=0, token='')
        with self.assertRaisesRegex(ValueError, 'Network binds require'):
            create_server(host='::', port=0, token='short')
        if not socket.has_ipv6:
            self.skipTest('IPv6 not available on this host')
        try:
            server = create_server(host='::1', port=0, token='', public_origin='')
        except OSError as error:
            if error.errno in {errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT, errno.EADDRNOTAVAIL}:
                self.skipTest('IPv6 loopback not available on this host')
            raise
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        try:
            self.assertEqual(server.address_family, socket.AF_INET6)
            for scheme, expected in [('http', 200), ('https', 403)]:
                connection = HTTPConnection('::1', server.server_port, timeout=5)
                try:
                    connection.request('GET', '/api/league', headers={'Origin':f'{scheme}://[::1]:{server.server_port}'})
                    response = connection.getresponse()
                    self.assertEqual(response.status, expected);response.read()
                finally:
                    connection.close()
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_trade_confirmation_and_ownership(self):
        body={'team_id':'harbor','other_id':'orbit','give':['harbor-2'],'receive':['orbit-5'],'source':'ocr'}
        self.assertEqual(self.request('/api/evaluate',body)[0],400)
        self.assertEqual(self.request('/api/evaluate',body|{'confirmed':True})[0],200)
        self.assertEqual(self.request('/api/evaluate',body|{'confirmed':True,'give':['orbit-2']})[0],400)
        self.assertEqual(self.request('/api/evaluate',[])[0],400)

    def test_request_bounds_and_ocr_invalid_content(self):
        self.assertEqual(self.request('/api/ocr',{'image':'not an image'})[0],400)
        self.assertEqual(self.request('/api/evaluate',{'large':'x'*17000})[0],413)
        self.assertEqual(self.request('/api/evaluate',method='POST')[0],413)

    def test_own_roster_confirmation_scans_all_opponents_without_manual_trade(self):
        roster = [p.id for p in demo().teams[0].players]
        body = {'team_id':'harbor', 'source':'ocr', 'roster_ids':roster, 'use_llm':True}
        with patch('app.llm.rank') as rank, patch('app.App.recommendations') as scan:
            for change in ({}, {'confirmed':'true'}, {'confirmed':True, 'roster_ids':roster[:-1]},
                           {'confirmed':True, 'roster_ids':roster + roster[:1]},
                           {'confirmed':True, 'roster_ids':roster[:-1] + ['orbit-1']},
                           {'confirmed':True, 'roster_ids':None}, {'confirmed':True, 'team_id':'unknown'}):
                self.assertEqual(self.request('/api/candidates', body | change)[0], 400)
            scan.assert_not_called()
            rank.assert_not_called()
        code, raw, _ = self.request('/api/candidates', body | {'confirmed':True, 'use_llm':False})
        result = json.loads(raw)
        self.assertEqual(code, 200)
        self.assertEqual(result['opponents'], 5)
        self.assertEqual(result['checked'], 2205)
        self.assertTrue(result['candidates'])
        self.assertTrue(all(c['team_id'] == 'harbor' for c in result['candidates']))

    def test_health_provider_availability_requires_complete_local_opt_in(self):
        for config, expected in [({}, False), ({'LLM_ENABLED':'true'}, False),
                                 ({'LLM_ENABLED':'false','LLM_PROVIDER':'openai','LLM_API_KEY':'test'}, False),
                                 ({'LLM_ENABLED':'true','LLM_PROVIDER':'other','LLM_API_KEY':'test'}, False),
                                 ({'LLM_ENABLED':'true','LLM_PROVIDER':'openai','LLM_API_KEY':'test'}, True)]:
            with patch.dict(os.environ, config, clear=True), patch('evaluator.llm.urlopen') as network:
                self.assertEqual(json.loads(self.request('/health')[1])['llm_available'], expected)
                network.assert_not_called()

    def test_authentication_and_network_binding(self):
        with self.assertRaises(ValueError):create_server(host='0.0.0.0',port=0,token='short')
        server=create_server(port=0,token='test-token')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        original=self.base;self.base=f'http://127.0.0.1:{server.server_port}'
        try:
            self.assertEqual(self.request('/api/league')[0],401)
            self.assertEqual(self.request('/api/league',headers={'Authorization':'Bearer test-token'})[0],200)
            self.assertNotIn(b'trade-room-bootstrap', self.request('/')[1])
            code, body, _ = self.request('/api/local-bootstrap', headers={
                'Authorization': 'Bearer test-token', 'X-Trade-Room-Bootstrap': 'x' * 43,
                'Sec-Fetch-Site': 'same-origin'})
            self.assertEqual(code, 403)
            self.assertNotIn(b'test-token', body)
            self.assertEqual(self.request('/api/session')[0],401)
            code, body, _ = self.request('/api/session', headers={'Authorization':'Bearer test-token'})
            self.assertEqual(code,200)
            self.assertEqual(json.loads(body), {'authenticated':True})
            self.assertEqual(self.request('/api/session?access_token=test-token')[0],401)
            self.assertEqual(self.request('/health')[0],200)
        finally:self.base=original;server.shutdown();server.server_close();thread.join()

    def test_candidates_do_not_invoke_llm_by_default(self):
        with patch('app.llm.rank',side_effect=AssertionError('LLM must not run')):
            code,body,_=self.request('/api/candidates',{'team_id':'harbor'})
            self.assertEqual(code,200);result=json.loads(body)
            self.assertEqual(result['checked'],2205)
            self.assertGreater(len(result['candidates']),0)
            self.assertEqual(result['llm_status'],'not requested')

    def test_manual_and_candidate_llm_require_explicit_opt_in(self):
        proposal = {'team_id':'harbor','other_id':'orbit','give':['harbor-2'],'receive':['orbit-5']}
        with patch.dict(os.environ, {'LLM_ENABLED':'true'}), patch('app.llm.rank') as rank, patch('app.llm.summarize') as summarize:
            for flag in (None, False, 'true', 1):
                self.assertEqual(self.request('/api/evaluate', proposal | {'use_llm':flag})[0], 200)
                self.assertEqual(self.request('/api/candidates', {'team_id':'harbor','use_llm':flag})[0], 200)
            rank.assert_not_called()
            summarize.assert_not_called()
            self.assertEqual(self.request('/api/evaluate', proposal | {'use_llm':True,'source':'ocr'})[0], 400)
            summarize.assert_not_called()
        with patch.dict(os.environ, {'LLM_ENABLED':'false'}), patch('evaluator.llm.urlopen') as network:
            for path, data in (('/api/evaluate', proposal), ('/api/candidates', {'team_id':'harbor'})):
                code, body, _ = self.request(path, data | {'use_llm':True})
                self.assertEqual(code, 200)
                self.assertEqual(json.loads(body)['llm_status'], 'disabled')
            network.assert_not_called()

    def test_llm_summaries_through_http_and_deterministic_failure(self):
        proposal = {'team_id':'harbor','other_id':'orbit','give':['harbor-2'],'receive':['orbit-5']}
        _, body, _ = self.request('/api/evaluate', proposal)
        deterministic_trade = json.loads(body)
        _, body, _ = self.request('/api/candidates', {'team_id':'harbor'})
        deterministic_candidates = json.loads(body)
        env = {'LLM_ENABLED':'true','LLM_PROVIDER':'openai','LLM_API_KEY':'synthetic-key'}
        def provider(request, timeout):
            facts = json.loads(json.loads(request.data)['messages'][1]['content'])
            rows = []
            for fact in reversed(facts):
                self.assertEqual(set(fact), {'id','your_season_delta','their_season_delta','your_week_delta','their_week_delta'})
                summary = {'text': 'These computed deltas describe the season and current-week tradeoffs.'}
                for mode in ('season','week'):
                    a, b = fact[f'your_{mode}_delta'], fact[f'their_{mode}_delta']
                    summary[mode] = ('unchanged' if a == b == 0 else 'both_gain' if min(a,b) > 0
                                     else 'your_gain' if a > 0 else 'their_gain' if b > 0 else 'neither_gain')
                rows.append({'id':fact['id'],'reason':'weekly_gain','summary':summary})
            return BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{
                'role':'assistant','content':json.dumps({'ranking':rows})}}]}).encode())
        def computed(trade):
            return {k:v for k,v in trade.items() if k not in {'llm_reason','llm_summary','llm_status'}}
        with patch.dict(os.environ, env), patch('evaluator.llm.urlopen', side_effect=provider) as network:
            for source in ({}, {'source':'ocr','confirmed':True}):
                code, body, _ = self.request('/api/evaluate', proposal | source | {'use_llm':True})
                result = json.loads(body)
                self.assertEqual(code, 200)
                self.assertEqual(result['llm_status'], 'summarized')
                self.assertTrue(result['llm_summary'])
                self.assertEqual(computed(result), deterministic_trade)
            code, body, _ = self.request('/api/candidates', {'team_id':'harbor','use_llm':True})
            result = json.loads(body)
            self.assertEqual(code, 200)
            self.assertEqual(result['llm_status'], 'ranked and summarized')
            self.assertTrue(all(c['llm_summary'] for c in result['candidates']))
            self.assertEqual([computed(c) for c in result['candidates']], list(reversed(deterministic_candidates['candidates'])))
            self.assertEqual(network.call_count, 3)
        # A provider exception is still a successful deterministic evaluation.
        with patch.dict(os.environ, env), patch('evaluator.llm.urlopen', side_effect=TimeoutError):
            for path, data, expected in (('/api/evaluate', proposal, deterministic_trade),
                                         ('/api/candidates', {'team_id':'harbor'}, deterministic_candidates)):
                code, body, _ = self.request(path, data | {'use_llm':True})
                result = json.loads(body)
                self.assertEqual(code, 200)
                self.assertEqual(result.pop('llm_status'), 'unavailable: deterministic results retained')
                self.assertEqual(result, {k:v for k,v in expected.items() if k != 'llm_status'})
        # Optional annotations and order never contaminate the cached shortlist.
        self.assertEqual(json.loads(self.request('/api/candidates', {'team_id':'harbor'})[1]), deterministic_candidates)

    def test_recommendation_cache_is_not_exposed_to_callers(self):
        app = App(demo())
        expected = app.recommendations('harbor')
        damaged = app.recommendations('harbor')
        damaged['candidates'][0]['yours']['week']['before']['lineup'].clear()
        damaged['candidates'].reverse()
        damaged['checked'] = -1
        self.assertEqual(app.recommendations('harbor'), expected)
