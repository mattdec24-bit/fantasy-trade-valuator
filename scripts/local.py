#!/usr/bin/env python3
"""Local Compose UX. Standard library only; setup never contacts ESPN/providers.

Secrets live in .local/config.json and app memory, never Docker's saved
environment, CLI arguments, shell-evaluated env files, or HTTP query strings.
"""
from __future__ import annotations

import argparse
import csv
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
import warnings

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / '.local'
CONFIG = PRIVATE / 'config.json'
TOKEN_PATTERN = re.compile(r'[A-Za-z0-9_-]{43}')


class LocalError(Exception):
    """Only controlled messages may be shown to the user."""


def run_quiet(args, *, env=None, timeout=30):
    # Docker errors can contain interpolated settings. Never forward their output.
    try:
        result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise LocalError('Local command unavailable or timed out. Check Docker is installed and running.') from None
    if result.returncode:
        raise LocalError('Local command failed. Check Docker is running, Compose v2 is installed, and the port is free. No command output was printed because it may contain secrets.')
    return result.stdout


def checked_path(path, directory=False):
    if not path.exists() and not path.is_symlink():
        return
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
            or (directory and not stat.S_ISDIR(info.st_mode))
            or (not directory and not stat.S_ISREG(info.st_mode))):
        raise LocalError('Private config paths must be ordinary local directories/files, never links.')
    if os.name != 'nt' and info.st_uid != os.getuid():
        raise LocalError('Private config must be owned by the current local user.')


def protect(path, directory=False):
    checked_path(path, directory)
    if os.name == 'nt':
        # Reset removes explicit grants as well as old inherited permissions.
        output = run_quiet(['whoami', '/user', '/fo', 'csv', '/nh'])
        try:
            sid = next(csv.reader([output.strip()]))[1]
            if not re.fullmatch(r'S-1-[0-9-]+', sid):
                raise ValueError
        except (IndexError, StopIteration, ValueError):
            raise LocalError('Cannot determine the Windows user for private config permissions.') from None
        run_quiet(['icacls', str(path), '/reset'])
        grant = f'*{sid}:' + ('(OI)(CI)F' if directory else 'F')
        run_quiet(['icacls', str(path), '/inheritance:r', '/grant:r', grant])
    else:
        path.chmod(0o700 if directory else 0o600)


def private_directory():
    checked_path(PRIVATE, directory=True)
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    protect(PRIVATE, directory=True)


def validate(config):
    try:
        if (set(config) != {'version', 'token', 'port', 'espn'} or type(config['version']) is not int or config['version'] != 1
                or not isinstance(config['token'], str) or not TOKEN_PATTERN.fullmatch(config['token'])
                or type(config['port']) is not int or not 1024 <= config['port'] <= 65535):
            raise ValueError
        espn = config['espn']
        if espn is not None:
            if (not isinstance(espn, dict) or set(espn) != {'year', 'league_id', 's2', 'swid'}
                    or not all(isinstance(value, str) for value in espn.values())
                    or not re.fullmatch(r'20[0-9]{2}', espn['year'])
                    or not re.fullmatch(r'[0-9]{1,20}', espn['league_id'])
                    or bool(espn['s2']) != bool(espn['swid'])
                    or any(len(value) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in value)
                           for value in (espn['s2'], espn['swid']))):
                raise ValueError
    except (KeyError, TypeError, ValueError):
        raise LocalError('Local config is invalid. Restore a private backup or use reset; values were not printed.') from None
    return config


def save_config(config):
    validate(config)
    private_directory()
    checked_path(CONFIG)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=PRIVATE,
                                         prefix='config-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            protect(temporary)
            json.dump(config, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, CONFIG)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def load_config(create=True):
    checked_path(PRIVATE, directory=True)
    checked_path(CONFIG)
    if not CONFIG.exists():
        if not create:
            raise LocalError('No local config yet. Run start.sh or start.cmd first.')
        config = {'version': 1, 'token': secrets.token_urlsafe(32), 'port': 8000, 'espn': None}
        save_config(config)
        print('Created private .local/config.json with a random deployment token.')
        return config
    private_directory()
    protect(CONFIG)
    try:
        if CONFIG.stat().st_size > 65536:
            raise ValueError
        return validate(json.loads(CONFIG.read_text(encoding='utf-8')))
    except (ValueError, UnicodeError):
        raise LocalError('Cannot read local config. Restore a private backup or use reset; values were not printed.') from None


def hidden(prompt):
    # getpass normally falls back to echoing on non-TTY input. Fail closed instead.
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            return getpass.getpass(prompt)
        except getpass.GetPassWarning:
            raise LocalError('Hidden input requires an interactive terminal. Open Terminal or PowerShell and run setup-espn there.') from None


def setup_espn(config):
    print('Use only a league and ESPN account you are authorized to read.')
    print('This saves settings locally; it makes no connection and does not start ESPN.')
    print('Find the league ID in your league page. For a private league, find espn_s2 and SWID in your signed-in browser cookie storage. Do not paste them into chat or commands.')
    year = input('Season year (four digits, e.g. 2026): ').strip()
    league_id = hidden('League ID (hidden): ').strip()
    private = input('Private league? [Y/n]: ').strip().lower()
    if private not in {'', 'y', 'yes', 'n', 'no'}:
        raise LocalError('Choose y or n. Settings were not changed.')
    s2 = swid = ''
    if private not in {'n', 'no'}:
        s2 = hidden('espn_s2 cookie (hidden): ')
        swid = hidden('SWID cookie, including braces if present (hidden): ')
        if not s2 or not swid:
            raise LocalError('Both private-league cookies are required. Settings were not changed.')
    updated = config | {'espn': {'year': year, 'league_id': league_id, 's2': s2, 'swid': swid}}
    save_config(updated)
    print('Saved private ESPN settings. No credentials were tested or sent. Stop the current demo, then run start.sh espn / start.cmd espn when ready to read ESPN. LLM stays off.')


def docker_environment(config, source='demo'):
    # Prevent inherited secrets, Compose overrides, .env files and provider gates
    # from silently changing a launch. No credentials in command arguments.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('APP_', 'ESPN_', 'LLM_', 'COMPOSE_', 'TRADE_ROOM_'))}
    uid, gid = (os.getuid(), os.getgid()) if os.name != 'nt' else (10001, 10001)
    if uid == 0:
        raise LocalError('Run this launcher as your regular local account, without sudo, so private config and the container stay non-root.')
    env.update(TRADE_ROOM_PORT=str(config['port']), TRADE_ROOM_SOURCE=source,
               TRADE_ROOM_UID=str(uid), TRADE_ROOM_GID=str(gid))
    if source == 'espn':
        if config['espn'] is None:
            raise LocalError('Configure your own ESPN settings first: start.sh setup-espn / start.cmd setup-espn.')
    return env


def docker_ready(env):
    if not shutil.which('docker'):
        raise LocalError('Docker was not found. Install/start Docker Desktop (or local Docker Engine with Compose v2 on Linux), then rerun the launcher.')
    if any(env.get(key) for key in ('DOCKER_HOST', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH')):
        raise LocalError('Unset DOCKER_HOST, DOCKER_TLS_VERIFY and DOCKER_CERT_PATH. This launcher accepts only a local Docker socket context.')
    try:
        contexts = json.loads(run_quiet(['docker', 'context', 'inspect'], env=env))
        endpoint = contexts[0]['Endpoints']['docker']['Host']
        if len(contexts) != 1 or not isinstance(endpoint, str) or not endpoint.startswith(('unix:///', 'npipe:////./pipe/')):
            raise ValueError
    except (ValueError, KeyError, IndexError, TypeError):
        raise LocalError('Select a local Docker context (Unix socket or Windows named pipe). Remote Docker endpoints are not supported.') from None
    run_quiet(['docker', 'compose', 'version'], env=env)
    run_quiet(['docker', 'info'], env=env)


def compose(config, source, *args):
    env = docker_environment(config, source)
    docker_ready(env)
    # Down identifies containers by project/service labels. Its minimal manifest
    # has no bind, so missing config cannot prevent reset (create_host_path=false).
    manifest = ROOT / 'scripts' / 'compose-stop.yaml' if args and args[0] == 'down' else ROOT / 'compose.yaml'
    return run_quiet(['docker', 'compose', '--project-name', 'trade-room-local',
                      '--project-directory', str(ROOT), '--env-file', str(ROOT / 'scripts' / 'compose.env'),
                      '--file', str(manifest), *args], env=env, timeout=900)


def base_url(config):
    return f"http://127.0.0.1:{config['port']}"


def request_json(config, path):
    # Explicitly bypass all system HTTP proxies; never follow redirects with auth.
    from evaluator.network import NoRedirect
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(base_url(config) + path,
                      headers={'Authorization': 'Bearer ' + config['token']})
    with opener.open(request, timeout=2) as response:
        return json.loads(response.read(65536))


def wait_ready(config, source=None, timeout=90):
    deadline = time.monotonic() + timeout
    while True:
        try:
            health = request_json(config, '/health')
            session = request_json(config, '/api/session')
            if (isinstance(health, dict) and health.get('status') == 'ok' and health.get('read_only') is True
                    and health.get('llm_enabled') is False and health.get('llm_available') is False
                    and (source is None or health.get('source') == ('synthetic' if source == 'demo' else 'espn'))
                    and session == {'authenticated': True}):
                return
        except (OSError, URLError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise LocalError('App did not become ready with the expected source, token and LLM off. Check Docker Desktop, try stop then demo, or choose another --port. No browser was opened.')
        time.sleep(0.5)


def open_browser(config):
    url = base_url(config) + '/'
    try:
        if sys.platform == 'win32':
            os.startfile(url)
        else:
            command = ['open' if sys.platform == 'darwin' else 'xdg-open', url]
            # Do not use webbrowser's text-browser fallback, which may print URLs.
            result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            if result.returncode:
                raise OSError
    except (OSError, subprocess.TimeoutExpired):
        raise LocalError('App is ready, but a graphical browser could not be opened. Run the open command again from a desktop terminal. The token was not printed.') from None
    print('Opened your browser with local authentication. The access token was not printed.')


def ensure_port_free(port):
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            raise LocalError('That local port is already in use. Use open for the running app, stop it first, or choose --port 8001.') from None


def main(argv=None):
    parser = argparse.ArgumentParser(description='Private, local-only Trade Room launcher; Docker Compose v2 and Python 3.11+ required.')
    parser.add_argument('action', nargs='?', default='demo', choices=['demo', 'setup-espn', 'espn', 'open', 'stop', 'reset'])
    parser.add_argument('--port', type=int, help='Local port 1024–65535 for demo/espn; saved for open/stop')
    parser.add_argument('--no-open', action='store_true', help='Start without opening a browser; use open later')
    args = parser.parse_args(argv)
    if args.port is not None and (args.action not in {'demo', 'espn'} or not 1024 <= args.port <= 65535):
        parser.error('--port requires demo/espn and a port from 1024 to 65535')
    try:
        if sys.version_info < (3, 11):
            raise LocalError('Python 3.11+ is required. Install a newer Python interpreter and rerun.')
        if args.action == 'reset':
            # Reset must also recover missing/corrupt config. Refuse links first.
            checked_path(PRIVATE, directory=True)
            checked_path(CONFIG)
            try:
                config = load_config(create=False)
            except LocalError:
                config = {'version': 1, 'token': secrets.token_urlsafe(32), 'port': 8000, 'espn': None}
        else:
            config = load_config(create=args.action in {'demo', 'espn', 'setup-espn'})
        if args.action == 'setup-espn':
            setup_espn(config)
        elif args.action in {'stop', 'reset'}:
            compose(config, 'demo', 'down', '--remove-orphans')
            if args.action == 'reset':
                # Delete only our config, not arbitrary files in .local.
                CONFIG.unlink(missing_ok=True)
                print('Stopped and removed local config, ESPN cookies and token. Next launch creates a new token. Image/build cache is retained.')
            else:
                print('Stopped. Private settings are retained for your next launch.')
        elif args.action == 'open':
            wait_ready(config, timeout=3)
            open_browser(config)
        else:
            if args.port is not None:
                config = config | {'port': args.port}
            # Validate ESPN before changing the port/config or starting Docker.
            docker_environment(config, args.action)
            ensure_port_free(config['port'])
            save_config(config)
            print('Starting local ' + args.action + ' with LLM off. First image build may take several minutes; Docker output is hidden to protect settings.', flush=True)
            compose(config, args.action, 'up', '--detach', '--build', '--force-recreate')
            wait_ready(config, args.action)
            print('Ready at ' + base_url(config) + '. Stop with start.sh stop / start.cmd stop.')
            if not args.no_open:
                open_browser(config)
        return 0
    except (LocalError, OSError, EOFError, KeyboardInterrupt):
        error = sys.exc_info()[1]
        print(str(error) if isinstance(error, LocalError) else 'Local operation interrupted or unavailable; settings and secrets were not printed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    # Support direct invocation without a package install.
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
