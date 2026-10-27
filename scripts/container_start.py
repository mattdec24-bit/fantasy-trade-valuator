#!/usr/bin/env python3
"""Compose bootstrap: read the private bind mount, never persist secret env.

Docker's saved environment contains no credentials. Only this process and its
app children get the token/explicit ESPN settings, after reading the local file.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app
from scripts.local import LocalError, validate

CONFIG = Path('/run/trade-room-config.json')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local Compose app bootstrap')
    parser.add_argument('--source', choices=['demo', 'espn'], default='demo')
    args = parser.parse_args(argv)
    try:
        if CONFIG.stat().st_size > 65536:
            raise LocalError('Invalid config')
        config = validate(json.loads(CONFIG.read_text(encoding='utf-8')))
        if args.source == 'espn' and config['espn'] is None:
            raise LocalError('ESPN not configured')
    except (OSError, ValueError, LocalError):
        print('Private local config unavailable or invalid. Use the launcher and guided setup; no settings were printed.', file=sys.stderr)
        return 1
    for key in list(os.environ):
        if key.startswith(('APP_', 'ESPN_', 'LLM_')):
            del os.environ[key]
    os.environ.update(APP_ACCESS_TOKEN=config['token'], APP_PUBLIC_ORIGIN='',
                      LLM_ENABLED='false', LLM_PROVIDER='', LLM_API_KEY='')
    if args.source == 'espn':
        os.environ.update({f'ESPN_{key}': config['espn'][field] for key, field in
                          [('FANTASY_YEAR', 'year'), ('LEAGUE_ID', 'league_id'), ('S2', 's2'), ('SWID', 'swid')]})
    app.main(['--host', '0.0.0.0', '--source', args.source, '--compose-local-bootstrap'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
