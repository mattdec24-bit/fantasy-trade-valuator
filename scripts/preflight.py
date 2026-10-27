#!/usr/bin/env python3
"""Run the same synthetic source checks locally and in CI, without staging files."""
import argparse
import ast
from importlib.metadata import version as installed_version, PackageNotFoundError
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.packaging_files import bundle_files
from scripts.build_macos import PILLOW_VERSION, PILLOW_NAME
from version import VERSION
import updates


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workflows', action='store_true', help='Also require installed actionlint and zizmor')
    args = parser.parse_args()
    try:
        if installed_version('Pillow') != PILLOW_VERSION:
            raise PackageNotFoundError
    except PackageNotFoundError:
        raise SystemExit('Use a Python environment with the pinned requirements.txt installed.') from None
    files = bundle_files()
    updates.repository()
    if ('Pillow==' + PILLOW_VERSION not in (ROOT / 'requirements.txt').read_text().splitlines()
            or not PILLOW_NAME.startswith('pillow-' + PILLOW_VERSION + '-')):
        raise SystemExit('Review requirements.txt and the pinned macOS Pillow wheel/version together.')
    for root in [ROOT, ROOT / 'scripts', ROOT / 'tests', ROOT / 'macos', ROOT / 'evaluator']:
        for path in root.glob('*.py'):
            ast.parse(path.read_text(), filename=str(path))
    for directory in ['static', 'tests', 'macos']:
        for path in sorted((ROOT / directory).iterdir()):
            if path.suffix in {'.js', '.cjs'}:
                run('node', '--check', str(path))
    run('sh', '-n', 'start.sh')
    run('git', 'diff', '--check')
    run('git', 'diff', '--cached', '--check')
    run(sys.executable, 'scripts/offline_tests.py')
    run('node', 'tests/test_ui.cjs')
    run(sys.executable, 'scripts/smoke.py')
    if args.workflows:
        if not shutil.which('actionlint') or not shutil.which('zizmor'):
            raise SystemExit('Install actionlint and zizmor as described in MAINTAINING.md.')
        workflows = [str(path) for path in sorted((ROOT / '.github/workflows').glob('*.yml'))]
        # Explicit filenames also work before the first Git commit exists.
        run('actionlint', '-shellcheck=', *workflows)
        run('zizmor', '--offline', '--no-progress', '--min-severity', 'low', '.github/workflows')
    print(f'PASS preflight: version {VERSION}; {len(files)} packaged source files; synthetic checks only', flush=True)


if __name__ == '__main__':
    main()
