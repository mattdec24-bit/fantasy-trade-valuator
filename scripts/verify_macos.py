#!/usr/bin/env python3
"""Exercise an actual app bundle with synthetic data and a fresh private home.

Use a Python with Pillow (the bundle's Python works). Launches the native app,
checks its actual child listener and HTTP/OCR boundaries. --keep-open allows
manual graphical QA; normal mode quits and verifies that the listener closes.
It never loads ESPN or accesses Keychain. All generated inputs are synthetic.
"""
from io import BytesIO
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--keep-open', action='store_true')
    parser.add_argument('--ui', action='store_true', help='Exercise rendered WebKit UI and capture synthetic snapshots')
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    home = Path(tempfile.mkdtemp(prefix='trade-room-verification-')).resolve()
    home.chmod(0o700)
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (1000, 270), 'white')
    draw = ImageDraw.Draw(image); font = ImageFont.load_default(size=48)
    draw.text((40, 35), 'Bennett Vale', fill='black', font=font)
    draw.text((40, 150), 'Cameron Vale', fill='black', font=font)
    raw = BytesIO(); image.save(raw, format='PNG')
    (home / 'synthetic-roster.png').write_bytes(raw.getvalue())
    env = {'HOME': str(home), 'PATH':'/usr/bin:/bin:/usr/sbin:/sbin', 'LANG':'en_US.UTF-8',
           'LLM_ENABLED':'true', 'LLM_API_KEY':'synthetic-ignored', 'ESPN_S2':'synthetic-ignored',
           'HTTPS_PROXY':'http://invalid.test', 'PYTHONPATH':'/invalid', 'APP_PUBLIC_ORIGIN':'https://invalid.test'}
    process = subprocess.Popen([str(bundle / 'Contents/MacOS/TradeRoom'),
                '--verification-home', str(home), '--offline-verification', *(['--verify-ui'] if args.ui else [])],
                env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    opener = build_opener(ProxyHandler({}))
    base = None
    token = None
    def request(path, data=None, mime='application/json', authenticated=True):
        headers = {'Content-Type':mime}
        if token and authenticated: headers['Authorization'] = 'Bearer ' + token
        raw = json.dumps(data).encode() if data is not None and mime == 'application/json' else data
        with opener.open(Request(base + path, data=raw, headers=headers), timeout=30) as response:
            return response.read()
    try:
        deadline = time.monotonic() + 30
        child = None
        while time.monotonic() < deadline:
            if process.poll() is not None: raise RuntimeError('Native app exited before readiness')
            pids = subprocess.run(['/usr/bin/pgrep', '-P', str(process.pid)], capture_output=True, text=True).stdout.split()
            for pid in pids:
                info = subprocess.run(['/usr/sbin/lsof', '-nP', '-a', '-p', pid, '-iTCP', '-sTCP:LISTEN', '-Fn'], capture_output=True, text=True).stdout
                match = re.search(r'^n127\.0\.0\.1:(\d+)$', info, re.M)
                if match:
                    assert not re.search(r'^n(?!127\.0\.0\.1:)', info, re.M), info
                    base = 'http://127.0.0.1:' + match[1]; child = int(pid); break
            if base: break
            time.sleep(.25)
        assert base and child, 'No native-owned loopback server became ready'
        ui_result = None
        if args.ui:
            deadline = time.monotonic() + 90
            result_path = home / 'ui-result.json'
            while time.monotonic() < deadline:
                if result_path.exists():
                    ui_result = json.loads(result_path.read_text())
                    if ui_result.get('stage') == 'final': break
                time.sleep(.1)
            assert ui_result and ui_result.get('ok'), ui_result or 'WebKit verification timed out'
            time.sleep(.5)  # Allow the asynchronous native snapshot to finish.
        health = json.loads(request('/health', authenticated=False))
        assert health == {'status':'ok', 'read_only':True, 'source':'synthetic',
                          'llm_enabled':False, 'llm_available':False, 'ocr_available':True}, health
        page = request('/', authenticated=False)
        nonce = re.search(rb'<meta name="trade-room-bootstrap" content="([A-Za-z0-9_-]{43})">', page)[1].decode()
        with opener.open(Request(base + '/api/local-bootstrap', headers={
                'Origin':base, 'X-Trade-Room-Bootstrap':nonce}), timeout=5) as response:
            token = json.load(response)['token']
        try:
            request('/api/desktop', authenticated=False)
            raise AssertionError('Setup must require authentication')
        except HTTPError as error:
            assert error.code == 401; error.close()
        assert b'/desktop.js' in page and b'TRADE ROOM' in page
        setup = json.loads(request('/api/desktop'))
        assert not setup['configured'] and setup['welcomed'] == args.ui
        league = json.loads(request('/api/league')); assert len(league['teams']) == 6
        cards = json.loads(request('/api/candidates', {'team_id':'harbor'}))
        assert (cards['checked'], cards['qualified'], len(cards['candidates'])) == (2205, 38, 12)
        candidate = cards['candidates'][0]
        proposal = {key:candidate[key] for key in ('team_id','other_id','give','receive')}
        assert json.loads(request('/api/evaluate', proposal)) == candidate
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new('RGB', (1000, 270), 'white')
        draw = ImageDraw.Draw(image); font = ImageFont.load_default(size=48)
        draw.text((40, 35), 'Bennett Vale', fill='black', font=font)
        draw.text((40, 150), 'Cameron Vale', fill='black', font=font)
        raw = BytesIO(); image.save(raw, format='PNG')
        # Synthetic artifact for manual upload-picker verification only.
        (home / 'synthetic-roster.png').write_bytes(raw.getvalue())
        recognized = json.loads(request('/api/ocr', raw.getvalue(), 'image/png'))
        assert recognized['requires_confirmation'] and not recognized['retained']
        assert 'Bennett Vale' in recognized['text'] and 'Cameron Vale' in recognized['text'], recognized['text']
        detected = {m['player_id'] for row in recognized['suggestions'] for m in row['matches']}
        assert {'harbor-2','harbor-3'} <= detected
        roster = {'team_id':'harbor','source':'ocr', 'roster_ids':[p['id'] for p in league['teams'][0]['players']]}
        try:
            request('/api/candidates', roster)
            raise AssertionError('Unconfirmed OCR scan must fail')
        except HTTPError as error:
            assert error.code == 400; error.close()
        assert json.loads(request('/api/candidates', roster | {'confirmed':True})) == cards
        # Synthetic settings save is local even with an external-network audit hook.
        settings = {'year':'2026','league_id':'123456','s2':'synthetic-only','swid':'{synthetic}'}
        saved = json.loads(request('/api/desktop', {'action':'save','storage':'file','espn':settings}))
        assert saved['configured']
        assert json.loads(request('/health', authenticated=False))['source'] == 'synthetic'
        private = home / 'Library/Application Support/Trade Room'
        assert private.stat().st_mode & 0o777 == 0o700
        assert (private / 'settings.json').stat().st_mode & 0o777 == 0o600
        json.loads(request('/api/desktop', {'action':'forget'}))
        assert not json.loads(request('/api/desktop'))['configured']
        assert 'synthetic-only' not in (private / 'settings.json').read_text()
        result = {'native_pid':process.pid, 'backend_pid':child, 'base':base, 'synthetic_home':str(home),
                  'bundle':str(bundle), 'health':health, 'checked':2205, 'qualified':38, 'cards':12,
                  'real_vision_ocr':recognized['text'], 'setup_save_forget':'passed',
                  'network':'backend external DNS/connections denied by audit hook',
                  'rendered_webkit_ui':ui_result,
                  'clean_stop':'pending' if args.keep_open else 'passed'}
        if args.keep_open:
            print(json.dumps(result, indent=2)); return
    finally:
        if not args.keep_open or sys.exc_info()[0]:
            if process.poll() is None:
                if args.ui:
                    process.stdin.write(b'close\n'); process.stdin.close()
                else:
                    process.send_signal(signal.SIGTERM)
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired: process.kill(); process.wait(); raise AssertionError('Native clean stop timed out')
            if base:
                time.sleep(.3)
                try:
                    request('/health', authenticated=False)
                    raise AssertionError('Local listener remained after native quit')
                except (OSError, URLError): pass
            if args.ui:
                stop = json.loads((home / 'stop-result.json').read_text())
                assert stop == {'backend_exit_status':0, 'backend_alive':False}, stop
            if child:
                try:
                    os.kill(child, 0)
                except ProcessLookupError:
                    pass
                else:
                    raise AssertionError('Backend process remained after native quit')
            # Keep generated synthetic artifacts for reproducible manual QA only.
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
