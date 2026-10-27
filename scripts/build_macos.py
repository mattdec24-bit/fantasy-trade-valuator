#!/usr/bin/env python3
"""Build the unsigned arm64 app and DMG. No signing, notarization or publication.

Build host only: macOS arm64, Python 3.11+, Apple command-line compiler tools.
Pinned public runtime and Pillow wheel; no user config, dotfiles or Git metadata
are copied. End users need only macOS 13+ on Apple Silicon.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from version import VERSION
from scripts.packaging_files import bundle_files

ARTIFACTS = ROOT.parent / (ROOT.name + '-artifacts')
PYTHON_URL = 'https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-3.13.16%2B20261013-aarch64-apple-darwin-install_only_stripped.tar.gz'
PYTHON_SHA256 = '16a5332fb0dcb77f163fc8f8cbccd95be1644cc53e68e5d2a79f50afd6680a0e'
LICENSES_URL = 'https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-3.13.16%2B20261013-aarch64-apple-darwin-pgo%2Blto-full.tar.zst'
LICENSES_SHA256 = '3497822d8bf4884bc79258f62668f985654d03d40ec74da4ca9ae7a5667c4362'
# Pillow wheel checksum is pinned after the public wheel is acquired.
PILLOW_NAME = 'pillow-12.3.0-cp313-cp313-macosx_11_0_arm64.whl'
PILLOW_SHA256 = 'd69141514cc30b774ceea5e3ed3a6635c8d8a96edf664689b890f4089111fb35'
PILLOW_VERSION = '12.3.0'


def run(args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, cwd=ROOT, **kwargs)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def acquire(downloads, name, url, expected, offline=False):
    path = downloads / name
    if not path.exists():
        if offline:
            raise RuntimeError('Offline build cache missing: ' + name)
        run(['/usr/bin/curl', '-fL', '--retry', '3', url, '-o', path])
    if digest(path) != expected:
        raise RuntimeError('Public dependency hash mismatch: ' + name)
    return path


def external_path(value):
    path = Path(value).expanduser().resolve()
    if path == ROOT or path.is_relative_to(ROOT) or ROOT.is_relative_to(path):
        raise ValueError('Build outputs/cache must be outside the source tree and its ancestors.')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=external_path, default=ARTIFACTS / VERSION)
    parser.add_argument('--cache-dir', type=external_path, default=ARTIFACTS / 'cache')
    parser.add_argument('--offline', action='store_true', help='Require pre-downloaded hash-verified dependencies')
    args = parser.parse_args()
    DIST = external_path(args.output)
    DOWNLOADS = external_path(args.cache_dir)
    if DIST == DOWNLOADS or DIST.is_relative_to(DOWNLOADS) or DOWNLOADS.is_relative_to(DIST):
        raise SystemExit('Output and cache must be separate directories.')
    BUNDLE = DIST / 'Trade Room.app'
    RESOURCES = BUNDLE / 'Contents/Resources'
    work = DIST / 'work'
    sources = bundle_files()  # Validate before changing output or using network.
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise SystemExit('Build on an Apple Silicon Mac with Apple command-line compiler tools.')
    DOWNLOADS.mkdir(parents=True, exist_ok=True); DIST.mkdir(parents=True, exist_ok=True)
    work.mkdir(exist_ok=True)
    runtime = acquire(DOWNLOADS, 'python.tar.gz', PYTHON_URL, PYTHON_SHA256, args.offline)
    license_archive = acquire(DOWNLOADS, 'python-full.tar.zst', LICENSES_URL, LICENSES_SHA256, args.offline)
    # Rebuild only this known output, never another app or local config.
    if BUNDLE.exists():
        if not (RESOURCES / 'BUILD.json').is_file():
            raise RuntimeError('Refusing to overwrite an unrecognized app bundle.')
        shutil.rmtree(BUNDLE)
    RESOURCES.mkdir(parents=True)
    with tarfile.open(runtime) as archive:
        archive.extractall(RESOURCES, filter='data')
    licenses = work / 'python-licenses'
    licenses.mkdir(exist_ok=True)
    run(['/usr/bin/tar', '-xf', license_archive, '-C', licenses, 'python/licenses', 'python/PYTHON.json'])
    shutil.copytree(licenses / 'python/licenses', RESOURCES / 'licenses/python')
    shutil.copy2(licenses / 'python/PYTHON.json', RESOURCES / 'licenses/python-build.json')
    python = RESOURCES / 'python/bin/python3'
    wheel = DOWNLOADS / PILLOW_NAME
    if not wheel.exists():
        if args.offline:
            raise RuntimeError('Offline build cache missing: ' + PILLOW_NAME)
        run([python, '-I', '-m', 'pip', 'download', '--only-binary=:all:', '--no-deps',
             'Pillow==' + PILLOW_VERSION, '-d', DOWNLOADS])
    if digest(wheel) != PILLOW_SHA256:
        raise RuntimeError('Pillow wheel checksum mismatch')
    run([python, '-I', '-m', 'pip', 'install', '--no-index', '--no-deps', '--no-compile', wheel])
    backend = RESOURCES / 'backend'; backend.mkdir()
    for relative in sources:
        target = backend / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    shutil.copy2(ROOT / 'macos/desktop_entry.py', backend / 'desktop_entry.py')
    shutil.copy2(ROOT / 'macos/verify_ui.js', RESOURCES / 'verify_ui.js')
    macos = BUNDLE / 'Contents/MacOS'; macos.mkdir()
    run(['/usr/bin/swiftc', '-O', '-target', 'arm64-apple-macosx13.0', ROOT / 'macos/NativeHelper.swift', '-o', RESOURCES / 'NativeHelper'])
    run(['/usr/bin/swiftc', '-O', '-target', 'arm64-apple-macosx13.0', ROOT / 'macos/Launcher.swift', '-o', macos / 'TradeRoomNative'])
    # The bundle entry point is truly unsigned. Native arm64 executables keep
    # only their required linker-generated execution hashes, without a bundle seal.
    entry = macos / 'TradeRoom'
    entry.write_text('#!/bin/sh\nexec "${0%/*}/TradeRoomNative" "$@"\n')
    entry.chmod(0o755)
    iconset = work / 'TradeRoom.iconset'
    run([python, '-I', ROOT / 'macos/make_icon.py', iconset])
    run(['/usr/bin/iconutil', '-c', 'icns', iconset, '-o', RESOURCES / 'TradeRoom.icns'])
    for cache in RESOURCES.rglob('__pycache__'):
        shutil.rmtree(cache)
    info = {'CFBundleName':'Trade Room', 'CFBundleDisplayName':'Trade Room',
            'CFBundleIdentifier':'local.traderoom.desktop', 'CFBundleExecutable':'TradeRoom',
            'CFBundlePackageType':'APPL', 'CFBundleShortVersionString':VERSION, 'CFBundleVersion':VERSION,
            'LSMinimumSystemVersion':'13.0', 'NSHighResolutionCapable':True, 'CFBundleIconFile':'TradeRoom',
            'NSAppTransportSecurity':{'NSAllowsLocalNetworking':True},
            'NSHumanReadableCopyright':'Copyright © 2026 Fantasy Trade Valuator contributors. MIT License.'}
    with (BUNDLE / 'Contents/Info.plist').open('wb') as stream: plistlib.dump(info, stream)
    (BUNDLE / 'Contents/PkgInfo').write_bytes(b'APPL????')
    for name in ('MACOS.md', 'LICENSE'):
        shutil.copy2(ROOT / name, RESOURCES / name)
    inputs = sources + ['macos/bundle-files.json', 'macos/Launcher.swift', 'macos/NativeHelper.swift',
        'macos/desktop_entry.py', 'macos/verify_ui.js', 'macos/make_icon.py',
        'scripts/build_macos.py', 'scripts/packaging_files.py', 'MACOS.md']
    manifest = {'version':VERSION, 'source_files_sha256':{name:digest(ROOT / name) for name in sorted(inputs)},
                'source_revision':subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip() or None,
                'source_dirty':bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
                'architecture':'arm64', 'minimum_macos':'13.0', 'python':'3.13.16+20261013',
                'python_url':PYTHON_URL, 'python_archive_sha256':PYTHON_SHA256,
                'python_license_archive_url':LICENSES_URL, 'python_license_archive_sha256':LICENSES_SHA256,
                'pillow':PILLOW_VERSION, 'pillow_wheel':PILLOW_NAME, 'pillow_wheel_sha256':PILLOW_SHA256,
                'ocr':'Apple Vision revision 2; en-US; accurate; on device',
                'developer_id_signed':False, 'notarized':False}
    (RESOURCES / 'BUILD.json').write_text(json.dumps(manifest, indent=2) + '\n')
    stage = work / 'macos-volume'
    if stage.exists(): shutil.rmtree(stage)
    stage.mkdir()
    run(['/usr/bin/ditto', BUNDLE, stage / BUNDLE.name])
    (stage / 'Applications').symlink_to('/Applications', target_is_directory=True)
    shutil.copy2(ROOT / 'MACOS.md', stage / 'READ ME FIRST.md')
    shutil.copy2(ROOT / 'LICENSE', stage / 'LICENSE.txt')
    dmg = DIST / f'Trade-Room-{VERSION}-macOS-arm64.dmg'
    run(['/usr/bin/hdiutil', 'create', '-volname', 'Trade Room', '-srcfolder', stage,
         '-format', 'UDZO', '-ov', dmg])
    shutil.copy2(RESOURCES / 'BUILD.json', DIST / 'BUILD.json')
    (DIST / 'SHA256SUMS').write_text(''.join(f'{digest(path)}  {path.name}\n' for path in (dmg, DIST / 'BUILD.json')))
    print('Built', BUNDLE, 'and', dmg)


if __name__ == '__main__': main()
