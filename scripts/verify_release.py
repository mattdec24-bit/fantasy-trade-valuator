#!/usr/bin/env python3
"""Verify checksums, mount read-only, compare bundles and run synthetic native QA."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from version import VERSION


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True, cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='External build output directory')
    parser.add_argument('--ui', action='store_true', help='Include rendered WebKit checks; requires logged-in Mac desktop')
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.is_relative_to(ROOT):
        raise SystemExit('Release assets must be outside the source tree.')
    dmg = directory / f'Trade-Room-{VERSION}-macOS-arm64.dmg'
    expected = {dmg.name, 'BUILD.json'}
    seen = set()
    for line in (directory / 'SHA256SUMS').read_text().splitlines():
        sha, name = line.split('  ', 1)
        if name not in expected or name in seen:
            raise SystemExit('Unexpected/duplicate checksum entry')
        seen.add(name)
        with (directory / name).open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != sha:
                raise SystemExit('Checksum mismatch: ' + name)
    if seen != expected:
        raise SystemExit('Missing checksum entry')
    run('/usr/bin/hdiutil', 'verify', dmg)
    with tempfile.TemporaryDirectory(prefix='trade-room-mount-') as temporary:
        mount = Path(temporary) / 'volume'; mount.mkdir()
        run('/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, dmg)
        try:
            bundle = mount / 'Trade Room.app'
            resources = bundle / 'Contents/Resources'
            info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
            assert info['CFBundleShortVersionString'] == info['CFBundleVersion'] == VERSION
            assert not (bundle / 'Contents/_CodeSignature').exists(), 'App must remain unsigned'
            assert json.loads((directory / 'BUILD.json').read_text()) == json.loads((resources / 'BUILD.json').read_text())
            verification = directory / 'verification'; verification.mkdir(exist_ok=True)
            with (verification / 'bundle-audit.json').open('w') as stream:
                subprocess.run([sys.executable, str(ROOT / 'scripts/audit_macos.py'),
                    str(directory / bundle.name), '--compare', str(bundle)], stdout=stream, check=True)
            output = subprocess.check_output([str(resources / 'python/bin/python3'),
                str(ROOT / 'scripts/verify_macos.py'), str(bundle), *(['--ui'] if args.ui else [])], text=True)
            (verification / 'native.json').write_text(output)
            # Retain only the known synthetic QA artifacts, never user settings.
            home = Path(json.loads(output)['synthetic_home'])
            for snapshot in home.glob('ui-*.png'):
                shutil.copy2(snapshot, verification / snapshot.name)
            for name in ['ui-result.json', 'stop-result.json']:
                if (home / name).is_file():
                    shutil.copy2(home / name, verification / name)
            print(output)
        finally:
            run('/usr/bin/hdiutil', 'detach', mount)
    print('PASS checksums, read-only mount, identical arm64 bundles, synthetic native workflow and clean shutdown')


if __name__ == '__main__':
    main()
