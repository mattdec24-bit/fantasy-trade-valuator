"""Native desktop backend. All launch-time state is local; demo is unconditional."""
from __future__ import annotations
from datetime import date
import json
import os
from pathlib import Path
import secrets
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading

import app
import updates
from evaluator import ocr
from evaluator.model import Engine
from evaluator.sources import demo, load_espn
from scripts.local import validate, LocalError

ROOT = Path(__file__).resolve().parent
HELPER = ROOT.parent / 'NativeHelper'


def isolate_environment():
    # Neither a terminal's provider/ESPN values nor proxies can opt this app in.
    for key in list(os.environ):
        if key.startswith(('ESPN_', 'LLM_', 'APP_', 'PYTHON', 'DYLD_')) or key.lower().endswith('_proxy'):
            os.environ.pop(key, None)
    os.environ.update(LLM_ENABLED='false', LLM_PROVIDER='', LLM_API_KEY='',
                      PATH='/usr/bin:/bin:/usr/sbin:/sbin', PYTHONDONTWRITEBYTECODE='1')


class Settings:
    def __init__(self, directory, helper=HELPER):
        self.directory = Path(directory)
        self.path = self.directory / 'settings.json'
        self.helper = Path(helper)
        self.lock = threading.RLock()

    def check(self, path, directory=False):
        if not path.exists() and not path.is_symlink():
            return
        info = path.lstat()
        if (info.st_uid != os.getuid() or stat.S_ISLNK(info.st_mode)
                or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))):
            raise ValueError('Local settings must be ordinary files owned by your account.')
        path.chmod(0o700 if directory else 0o600)

    def prepare(self):
        # Inspect every existing ancestor, but only change our own directory.
        for parent in self.directory.parents:
            if parent.is_symlink():
                raise ValueError('Local settings cannot use linked directories.')
        self.check(self.directory, True)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.check(self.directory, True)
        self.check(self.path)

    def read(self):
        self.prepare()
        if not self.path.exists():
            return {'version': 1, 'welcomed': False, 'storage': None}
        if self.path.stat().st_size > 24000:
            raise ValueError('Local settings are invalid. Remove settings.json to reset.')
        try:
            value = json.loads(self.path.read_text())
            if (value['version'] != 1 or type(value['welcomed']) is not bool
                    or value['storage'] not in {None, 'keychain', 'file'}):
                raise ValueError
            if value['storage'] == 'file':
                self.valid_espn(value['espn'])
            account = value.get('keychain_account', 'league')
            pending = value.get('keychain_cleanup', [])
            if (not self.valid_account(account) or not isinstance(pending, list)
                    or not all(self.valid_account(item) for item in pending)
                    or (value['storage'] == 'keychain' and account in pending)):
                raise ValueError
            return value
        except (ValueError, KeyError, TypeError):
            raise ValueError('Local settings are invalid. Remove settings.json to reset.') from None

    def write(self, value):
        self.prepare()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile('w', dir=self.directory, prefix='.settings-', delete=False) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                json.dump(value, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def valid_espn(value):
        try:
            validate({'version': 1, 'token': 'x' * 43, 'port': 8000, 'espn': value})
            if value is None:
                raise ValueError
            # Cookie delimiters cannot introduce additional cookies or headers.
            if any(';' in value[k] for k in ('s2', 'swid')):
                raise ValueError
            return value
        except (LocalError, ValueError):
            raise ValueError('Enter a four-digit season, numeric league ID, and both cookies for a private league.') from None

    @staticmethod
    def valid_account(account):
        return isinstance(account, str) and re.fullmatch(r"league(?:-[0-9a-f]{32})?", account) is not None

    def keychain(self, action, value=None, account='league'):
        try:
            result = subprocess.run([str(self.helper), 'secret-' + action, account],
                input=json.dumps(value).encode() if value is not None else b'',
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60, check=True)
            return json.loads(result.stdout) if action == 'read' else None
        except (OSError, subprocess.SubprocessError, ValueError):
            raise ValueError('Keychain access was cancelled or unavailable. Unlock your login Keychain and retry, or explicitly choose private local file storage.') from None

    def status(self):
        value = self.read()
        return {'configured': value['storage'] is not None, 'welcomed': value['welcomed'],
                'storage': value['storage'], 'year': str(date.today().year), 'llm': 'disabled',
                'ocr': 'Apple Vision · English · on device',
                'cleanup_pending': bool(value.get('keychain_cleanup'))}

    def cleanup(self, value):
        """Retired slots stay journaled until removal succeeds; deletion is idempotent.

        A failed cleanup never rolls back a committed, working configuration.
        If the final journal write fails, retrying an already deleted slot is safe.
        """
        pending = value.get('keychain_cleanup', [])
        remaining = []
        for account in pending:
            try:
                self.keychain('delete', account=account)
            except ValueError:
                remaining.append(account)
        cleaned = {k: v for k, v in value.items() if k != 'keychain_cleanup'}
        if remaining:
            cleaned['keychain_cleanup'] = remaining
        if cleaned != value:
            try:
                self.write(cleaned)
            except OSError:
                pass  # The committed metadata still journals every retired slot.

    def save(self, value, storage):
        self.valid_espn(value)
        if storage not in {'keychain', 'file'}:
            raise ValueError('Choose Keychain or private local file storage.')
        with self.lock:
            previous = self.read()
            pending = list(previous.get('keychain_cleanup', []))
            committed = {'version': 1, 'welcomed': True, 'storage': storage}
            if previous['storage'] == 'keychain':
                pending.append(previous.get('keychain_account', 'league'))
            if storage == 'file':
                committed['espn'] = value
            else:
                # Copy-on-write: never overwrite the active Keychain slot. Journal
                # the new slot BEFORE creating it, so even failed rollback cleanup
                # leaves a durable reference, without storing cookies in metadata.
                account = 'league-' + secrets.token_hex(16)
                staged = previous | {'keychain_cleanup': [*previous.get('keychain_cleanup', []), account]}
                self.write(staged)
                try:
                    self.keychain('save', value, account=account)
                    committed['keychain_account'] = account
                    if pending:
                        committed['keychain_cleanup'] = pending
                    self.write(committed)
                except (ValueError, OSError):
                    self.cleanup(staged)
                    raise
                self.cleanup(committed)
                return
            if pending:
                committed['keychain_cleanup'] = pending
            # Migration commits the new working credentials before retiring old ones.
            self.write(committed)
            self.cleanup(committed)

    def credentials(self):
        with self.lock:
            value = self.read()
            if value['storage'] is None:
                raise ValueError('Save your local ESPN settings first.')
            return self.valid_espn(self.keychain('read', account=value.get('keychain_account', 'league'))
                                   if value['storage'] == 'keychain' else value['espn'])

    def forget(self):
        with self.lock:
            previous = self.read()
            pending = list(previous.get('keychain_cleanup', []))
            if previous['storage'] == 'keychain':
                pending.append(previous.get('keychain_account', 'league'))
            committed = {'version': 1, 'welcomed': True, 'storage': None}
            if pending:
                committed['keychain_cleanup'] = pending
            self.write(committed)
            self.cleanup(committed)

    def welcome(self):
        with self.lock:
            self.write(self.read() | {'welcomed': True})


class Desktop:
    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.Lock()

    def status(self):
        return self.settings.status() | {'updates': updates.status()}

    def action(self, data, state):
        # Remote reads require explicit ESPN or metadata-only update actions.
        if not self.lock.acquire(blocking=False):
            raise ValueError('A local setup operation is already running.')
        try:
            action = data.get('action')
            if action == 'check-updates':
                return updates.check()
            elif action == 'save':
                self.settings.save(data.get('espn'), data.get('storage'))
            elif action == 'welcome':
                self.settings.welcome()
            elif action == 'forget':
                self.settings.forget()
                self.replace(state, demo())
            elif action == 'demo':
                self.replace(state, demo())
            elif action == 'espn':
                credentials = self.settings.credentials()
                try:
                    os.environ.update({key: credentials[field] for key, field in (
                        ('ESPN_FANTASY_YEAR', 'year'), ('ESPN_LEAGUE_ID', 'league_id'),
                        ('ESPN_S2', 's2'), ('ESPN_SWID', 'swid'))})
                    league = load_espn()
                except Exception:
                    raise ValueError('ESPN could not load a supported snapshot. Check your local settings, connection, and roster/IR configuration. Your previous source is still available; no trade was submitted.') from None
                finally:
                    for key in list(os.environ):
                        if key.startswith('ESPN_'):
                            os.environ.pop(key, None)
                self.replace(state, league)
            else:
                raise ValueError('Unknown desktop action.')
            return self.status()
        finally:
            self.lock.release()

    @staticmethod
    def replace(state, league):
        with state.lock:
            state.league, state.engine, state.cache = league, Engine(league), {}


def main():
    isolate_environment()
    if os.getpgrp() != os.getpid():
        os.setsid()  # Foundation may already have created our isolated process group.
    if '--offline-verification' in sys.argv:
        def deny_external(event, args):
            if event == 'socket.getaddrinfo':
                host = args[0]
            elif event == 'socket.connect' and isinstance(args[1], tuple):
                host = args[1][0]
            else:
                return
            if host not in {'localhost', '127.0.0.1', '::1'}:
                raise RuntimeError('Offline verification blocked external network')
        sys.addaudithook(deny_external)
    ocr.configure_native(HELPER)
    directory = Path.home() / 'Library' / 'Application Support' / 'Trade Room'
    settings = Settings(directory)
    # Demo startup never reads Keychain or loads saved ESPN cookies into env.
    settings.status()
    server = app.create_server(port=0, source='demo', token=secrets.token_urlsafe(32),
                               public_origin='', compose_local_bootstrap=True)
    server.handle_error = lambda *_: None
    server.RequestHandlerClass.desktop = Desktop(settings)
    stopping = threading.Event()
    def stop(*_):
        if not stopping.is_set():
            stopping.set()
            os.killpg(os.getpgrp(), signal.SIGTERM)
            threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # Native parent owns stdin; EOF also stops the server after a parent crash.
    def parent_watch():
        try:
            while os.read(0, 4096):
                pass
        except OSError:
            pass
        stop()
    threading.Thread(target=parent_watch, daemon=True).start()
    print(json.dumps({'url': f'http://127.0.0.1:{server.server_port}/'}), flush=True)
    try:
        server.serve_forever(poll_interval=.1)
    finally:
        server.server_close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Native launcher supplies actionable UI; no traceback/settings go to logs.
        raise SystemExit(1) from None
