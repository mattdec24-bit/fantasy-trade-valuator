#!/usr/bin/env python3
"""Self-hostable app. ESPN reads happen only with explicit --source espn."""
from __future__ import annotations
import argparse
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import threading
from urllib.parse import urlsplit

from evaluator import llm, ocr
from evaluator.model import Engine
from evaluator.sources import demo, load_espn
from version import VERSION

ROOT = Path(__file__).resolve().parent
LOOPBACK_HOSTS = {'localhost', '127.0.0.1', '::1'}
BOOTSTRAP_PATH = '/api/local-bootstrap'


def parse_origin(value):
    """Accept only a serialized HTTP(S) origin, never a URL with extra fields."""
    if not value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Expected an HTTP(S) origin without whitespace')
    parsed = urlsplit(value)
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path or '?' in value or '#' in value or '\\' in value
            or parsed.netloc.endswith(':')):
        raise ValueError('Expected an HTTP(S) origin with no credentials, path, query, or fragment')
    # urlsplit tolerates trailing garbage after a bracketed IPv6 hostname.
    if parsed.netloc.startswith('['):
        suffix = parsed.netloc.partition(']')[2]
        if suffix and not suffix.startswith(':'):
            raise ValueError('Invalid origin authority')
    return parsed.scheme, parsed.hostname, parsed.port if parsed.port is not None else (443 if parsed.scheme == 'https' else 80)


class IPv6HTTPServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6


class App:
    def __init__(self, league, token='', allowed_hosts=None, public_origin=None, compose_local_bootstrap=False):
        self.league = league
        self.engine = Engine(league)
        self.token = token
        self.allowed_hosts = set(allowed_hosts or ['localhost', '127.0.0.1', '::1'])
        self.public_origin = parse_origin(public_origin) if public_origin else None
        self.compose_local_bootstrap = compose_local_bootstrap
        self.bootstrap_nonce = secrets.token_urlsafe(32) if compose_local_bootstrap else ''
        self.cache = {}
        self.lock = threading.Lock()
        self.ocr_gate = threading.BoundedSemaphore(2)

    def recommendations(self, team_id):
        with self.lock:
            if team_id not in self.cache:
                result = self.engine.candidates(team_id)
                self.cache[team_id] = result
            return deepcopy(self.cache[team_id])


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'TradeRoom/' + VERSION
        desktop = None

        def log_error(self, *_):
            pass

        def log_message(self, *_):
            pass  # No URLs, league IDs, OCR, request bodies, or secrets in logs.

        def reply(self, status, payload, content_type='application/json'):
            body = json.dumps(payload, allow_nan=False).encode() if content_type == 'application/json' else payload
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def guard(self):
            try:
                if len(self.headers.get_all('Host', [])) != 1 or len(self.headers.get_all('Origin', [])) > 1:
                    raise ValueError('Ambiguous host or origin')
                local_origin = parse_origin('http://' + self.headers.get('Host', ''))
                if local_origin[1] not in app.allowed_hosts:
                    self.reply(403, {'error': 'Host not allowed; configure --allowed-host'})
                    return False
                if app.public_origin and local_origin[1] != app.public_origin[1]:
                    self.reply(403, {'error': 'Host does not match the configured public origin'})
                    return False
                origin = self.headers.get('Origin')
                if origin is not None and parse_origin(origin) != (app.public_origin or local_origin):
                    self.reply(403, {'error': 'Cross-origin requests are not allowed'})
                    return False
                if self.path == BOOTSTRAP_PATH:
                    # Only the explicit local Compose profile may disclose a token.
                    # The page nonce cannot be read cross-origin. A non-simple
                    # header forces preflight; we implement no CORS/OPTIONS grant.
                    site = self.headers.get('Sec-Fetch-Site')
                    if (self.command != 'GET' or not app.compose_local_bootstrap
                            or app.public_origin or not app.allowed_hosts <= LOOPBACK_HOSTS
                            or local_origin[1] not in LOOPBACK_HOSTS
                            or len(self.headers.get_all('X-Trade-Room-Bootstrap', [])) != 1
                            or not hmac.compare_digest(self.headers.get('X-Trade-Room-Bootstrap', '').encode(), app.bootstrap_nonce.encode())
                            or any(self.headers.get_all(name) for name in ('Forwarded', 'X-Forwarded-For', 'X-Forwarded-Host', 'X-Forwarded-Proto'))
                            or len(self.headers.get_all('Sec-Fetch-Site', [])) > 1
                            or (site is not None and site != 'same-origin')
                            or (site != 'same-origin' and origin is None)):
                        self.reply(403, {'error': 'Local bootstrap not allowed'})
                        return False
                    return True
                if self.path.startswith('/api/') and app.token:
                    value = self.headers.get('Authorization', '')
                    if not hmac.compare_digest(value, 'Bearer ' + app.token):
                        self.reply(401, {'error': 'Enter the deployment access token'})
                        return False
                return True
            except ValueError:
                self.reply(400, {'error': 'Invalid host or origin'})
                return False

        def do_GET(self):
            if not self.guard():
                return
            if self.path == BOOTSTRAP_PATH:
                return self.reply(200, {'token': app.token})
            if self.path == '/health':
                return self.reply(200, {'status': 'ok', 'read_only': True, 'source': 'synthetic' if 'Synthetic' in app.league.source else 'espn',
                                        'llm_enabled': llm.enabled(), 'llm_available': llm.available(),
                                        'ocr_available': ocr.available()})
            if self.path == '/api/league':
                return self.reply(200, app.league.public())
            if self.path == '/api/session':
                return self.reply(200, {'authenticated': True})
            if self.path == '/api/desktop' and self.desktop is not None:
                try:
                    return self.reply(200, self.desktop.status())
                except (OSError, ValueError):
                    return self.reply(400, {'error': 'Local settings unavailable. Quit and check your Application Support/Trade Room settings.'})
            if self.path.startswith('/api/'):
                return self.reply(404, {'error': 'Unknown read-only resource'})
            files = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if self.desktop is not None:
                files['/desktop.js'] = ('desktop.js', 'text/javascript; charset=utf-8')
            if self.path not in files:
                return self.reply(404, {'error': 'Not found'})
            name, mime = files[self.path]
            body = (ROOT / 'static' / name).read_bytes()
            if self.path == '/' and app.compose_local_bootstrap:
                # The nonce is separate from the deployment token; neither is
                # placed in a URL, browser-launch argument, or access log.
                meta = f'<meta name="trade-room-bootstrap" content="{app.bootstrap_nonce}">'
                body = body.replace(b'</head>', meta.encode() + b'</head>')
            if self.path == '/' and self.desktop is not None:
                body = body.replace(b'</head>', b'<script defer src="/desktop.js"></script></head>')
            self.reply(200, body, mime)

        def do_POST(self):
            if not self.guard():
                return
            if self.path == '/api/desktop' and self.desktop is None:
                return self.reply(404, {'error': 'Desktop setup is unavailable in this deployment'})
            if self.path not in {'/api/candidates', '/api/evaluate', '/api/ocr', '/api/desktop'}:
                return self.reply(404, {'error': 'No ESPN write endpoints exist'})
            try:
                if self.headers.get('Transfer-Encoding'):
                    raise ValueError('Chunked uploads are not supported')
                size = int(self.headers.get('Content-Length', '0'))
                maximum = ocr.MAX_UPLOAD if self.path == '/api/ocr' else (48000 if self.path == '/api/desktop' else 16000)
                if not 0 < size <= maximum:
                    return self.reply(413, {'error': 'Request is empty or exceeds the size limit'})
                self.connection.settimeout(20)
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError('Incomplete request')
                if self.path == '/api/ocr':
                    if self.headers.get('Content-Type', '').split(';')[0] not in {'image/png', 'image/jpeg'}:
                        raise ValueError('Upload a PNG or JPEG screenshot')
                    if not app.ocr_gate.acquire(blocking=False):
                        return self.reply(429, {'error': 'Local OCR is busy; retry shortly'})
                    try:
                        text = ocr.extract(raw)
                        return self.reply(200, {'text': text, 'suggestions': ocr.suggestions(text, app.league),
                                               'requires_confirmation': True, 'retained': False})
                    finally:
                        app.ocr_gate.release()
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('Expected application/json')
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError('Expected an object')
                if self.path == '/api/desktop':
                    try:
                        return self.reply(200, self.desktop.action(data, app))
                    except ValueError as error:
                        return self.reply(400, {'error': str(error)})
                    except Exception:
                        return self.reply(503, {'error': 'Local setup unavailable; settings and credentials were not logged.'})
                if self.path == '/api/evaluate':
                    if data.get('source') == 'ocr' and data.get('confirmed') is not True:
                        raise ValueError('Confirm the recognized roster players before evaluation')
                    result = app.engine.evaluate(data.get('team_id'), data.get('other_id'), data.get('give'), data.get('receive'))
                    if data.get('use_llm') is True:
                        result, state = llm.summarize(result)
                        result = result | {'llm_status': state}
                    return self.reply(200, result)
                if data.get('source') == 'ocr':
                    team = app.engine.teams.get(data.get('team_id'))
                    roster = data.get('roster_ids')
                    if (data.get('confirmed') is not True or team is None
                            or not isinstance(roster, list) or any(type(pid) is not str for pid in roster)
                            or len(roster) != len(team.players) or set(roster) != {p.id for p in team.players}):
                        raise ValueError('Confirm your full snapshot roster before scanning')
                result = app.recommendations(data.get('team_id'))
                ranked, state = llm.rank(result['candidates']) if data.get('use_llm') is True else (result['candidates'], 'not requested')
                return self.reply(200, result | {'candidates': ranked, 'llm_status': state})
            except (ValueError, TypeError, KeyError, UnicodeError):
                # Validation messages are controlled by this app; never echo raw input or provider errors.
                self.reply(400, {'error': 'Invalid request, player ownership, roster capacity, or unavailable OCR. Check selections and local OCR setup.'})
            except Exception:
                self.reply(503, {'error': 'Local processing unavailable; no trade was submitted'})

        def do_PUT(self):
            self.reply(405, {'error': 'Read-only application'})
        do_DELETE = do_PUT
        do_PATCH = do_PUT

    return Handler


def create_server(host='127.0.0.1', port=8000, source='demo', token=None, allowed_hosts=None, public_origin=None, compose_local_bootstrap=False):
    token = os.getenv('APP_ACCESS_TOKEN', '') if token is None else token
    if host not in {'127.0.0.1', 'localhost', '::1'} and len(token) < 24:
        raise ValueError('Network binds require APP_ACCESS_TOKEN with at least 24 characters')
    public_origin = os.getenv('APP_PUBLIC_ORIGIN', '') if public_origin is None else public_origin
    # Validate deployment settings before loading even an explicitly selected source.
    if public_origin:
        parse_origin(public_origin)
    if compose_local_bootstrap and (public_origin or not token
                                   or not set(allowed_hosts or LOOPBACK_HOSTS) <= LOOPBACK_HOSTS
                                   or host not in LOOPBACK_HOSTS | {'0.0.0.0'}):
        raise ValueError('Compose local bootstrap requires a token, loopback-only allowed hosts, no public origin, and a local/Compose bind')
    server_class = IPv6HTTPServer if ':' in host else ThreadingHTTPServer
    if server_class is IPv6HTTPServer and not socket.has_ipv6:
        raise ValueError('IPv6 binding is unavailable on this system; use 127.0.0.1')
    league = demo() if source == 'demo' else load_espn()
    app = App(league, token, allowed_hosts, public_origin, compose_local_bootstrap)
    server = server_class((host, port), handler_for(app))
    server.daemon_threads = True
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only fantasy Trade Room')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--source', choices=['demo', 'espn'], default='demo')
    parser.add_argument('--allowed-host', action='append', default=['localhost', '127.0.0.1', '::1'])
    parser.add_argument('--public-origin', help='Trusted browser origin, e.g. https://trades.example.com (or APP_PUBLIC_ORIGIN)')
    parser.add_argument('--compose-local-bootstrap', action='store_true', help='Local Compose profile only: allow guarded same-origin token bootstrap; never enable for public use')
    args = parser.parse_args(argv)
    try:
        server = create_server(args.host, args.port, args.source, allowed_hosts=args.allowed_host, public_origin=args.public_origin,
                               compose_local_bootstrap=args.compose_local_bootstrap)
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + '\n')
    print(f'Trade Room running on port {server.server_port}; source={args.source}; read-only; uploads stay in memory', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
