#!/usr/bin/env python3
"""Offline fake Docker executable used by test_local.py. Does not emulate builds.

Records argv and rendered settings only inside the test's private temp directory.
The real app runs on ephemeral loopback in the parent, not in a container.
"""
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.offline_tests import deny_external_network
sys.addaudithook(deny_external_network)


def main():
    args = sys.argv[1:]
    if args == ['context', 'inspect']:
        print(json.dumps([{'Endpoints': {'docker': {'Host': os.environ.get('FAKE_ENDPOINT', 'unix:///fake/docker.sock')}}}]))
    elif args == ['compose', 'version']:
        print('Docker Compose version v2.fake')
    elif args == ['info']:
        print('offline fake local engine')
    elif args and args[0] == 'compose':
        assert args[args.index('--project-name') + 1] == 'trade-room-local'
        assert '--project-directory' in args
        assert Path(args[args.index('--env-file') + 1]).name == 'compose.env'
        manifest = Path(args[args.index('--file') + 1])
        spec = json.loads(manifest.read_text())
        project = Path(args[args.index('--project-directory') + 1])
        # Enforce the required host bind even on down: this catches attempts to
        # reset using a manifest that references an absent config. Not a daemon.
        for service in spec['services'].values():
            for volume in service.get('volumes', []):
                if volume.get('bind', {}).get('create_host_path') is False:
                    assert (project / volume['source']).is_file(), 'Required bind source missing'
        if 'down' in args:
            assert manifest.name == 'compose-stop.yaml'
            assert spec == {'services': {'trade-room': {'image': 'trade-room-local'}}}
        else:
            assert manifest.name == 'compose.yaml'
        def interpolate(value):
            if isinstance(value, dict):
                return {k: interpolate(v) for k, v in value.items()}
            if isinstance(value, list):
                return [interpolate(v) for v in value]
            if isinstance(value, str):
                def replace(match):
                    name, operation, default = match.groups()
                    item = os.environ.get(name, '')
                    if operation == '?' and not item:
                        raise AssertionError('Required fake config missing')
                    return item or default
                return re.sub(r'\$\{([A-Z_][A-Z0-9_]*):([-?])(.*?)\}', replace, value)
            return value
        rendered = interpolate(spec)
        with Path(os.environ['FAKE_RECORD']).open('a') as stream:
            stream.write(json.dumps({'args': args, 'spec': rendered,
                                     'private_env_keys': sorted(k for k in os.environ if k.startswith(('ESPN_', 'LLM_', 'APP_', 'COMPOSE_')))}) + '\n')
        if os.environ.get('FAKE_FAIL'):
            try:
                private = json.loads((project / '.local' / 'config.json').read_text())
            except (OSError, ValueError):
                private = {'token': 'synthetic-failed-stop', 'espn': None}
            print(private['token'], file=sys.stderr)
            print((private['espn'] or {}).get('s2', ''), file=sys.stderr)
            return 1
        print('offline fake compose success')
    else:
        raise AssertionError('Unexpected fake docker command')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
