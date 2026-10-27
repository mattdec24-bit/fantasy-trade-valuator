#!/usr/bin/env python3
"""Read-only release gate; requires an authorized commit, matching tag and repo."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from version import VERSION
from updates import repository


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--repository', required=True)
    args = parser.parse_args()
    if args.tag != 'v' + VERSION:
        raise SystemExit('Release tag must equal v' + VERSION)
    if repository() != args.repository:
        raise SystemExit('Configure release.json with the verified GitHub owner/repository first.')
    if git('status', '--porcelain'):
        raise SystemExit('Release requires a clean committed source tree.')
    if git('rev-parse', '--verify', 'HEAD') != git('rev-parse', '--verify', f'refs/tags/{args.tag}^{{commit}}'):
        raise SystemExit('Release tag must already exist and point to the checked-out commit.')
    print('PASS release source/tag/repository gate')


if __name__ == '__main__':
    main()
