#!/usr/bin/env python3
"""Audit bundle contents and Mach-O dependencies without invoking signing tools."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    files, links, binaries = {}, {}, {}
    for path in sorted(bundle.rglob('*')):
        relative = str(path.relative_to(bundle))
        if path.is_symlink():
            links[relative] = str(path.readlink())
            assert path.resolve().is_relative_to(bundle) and path.exists(), relative
            continue
        if not path.is_file(): continue
        data = path.read_bytes()
        files[relative] = hashlib.sha256(data).hexdigest()
        if data[:4] in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
            output = subprocess.check_output(['/usr/bin/otool', '-L', str(path)], text=True)
            dependencies = [line.strip().split(' (compatibility')[0] for line in output.splitlines()[1:]]
            identifiers = subprocess.check_output(['/usr/bin/otool', '-D', str(path)], text=True).splitlines()[1:]
            dependencies = [item for item in dependencies if item not in identifiers]  # LC_ID_DYLIB is not an edge.
            assert all(item.startswith(('/usr/lib/', '/System/Library/', '@loader_path/', '@rpath/', '@executable_path/')) for item in dependencies), (relative, dependencies)
            description = subprocess.check_output(['/usr/bin/file', '-b', str(path)], text=True).strip()
            assert 'arm64' in description, (relative, description)
            binaries[relative] = dependencies
        assert not any(part in {'.git', '.env', '.local', 'node_modules', '__pycache__'} for part in path.relative_to(bundle).parts), relative
        assert path.name not in {'config.json', 'settings.json', '.env'}, relative
    # Resolve every @loader_path edge in the dependency closure, including Pillow's dylibs.
    for relative, dependencies in binaries.items():
        path = bundle / relative
        for dependency in dependencies:
            if dependency.startswith('@loader_path/'):
                resolved = (path.parent / dependency.removeprefix('@loader_path/')).resolve()
                assert resolved.is_file() and resolved.is_relative_to(bundle), (relative, dependency)
    if args.compare:
        other = args.compare.resolve()
        for relative, sha in files.items():
            assert hashlib.sha256((other / relative).read_bytes()).hexdigest() == sha, relative
        assert set(files) == {str(p.relative_to(other)) for p in other.rglob('*') if p.is_file() and not p.is_symlink()}
        for relative, target in links.items(): assert str((other / relative).readlink()) == target
        assert set(links) == {str(p.relative_to(other)) for p in other.rglob('*') if p.is_symlink()}
    print(json.dumps({'file_count':len(files), 'symlink_count':len(links), 'macho_count':len(binaries),
                      'all_architectures_include_arm64':True, 'external_dependencies':'Apple system libraries only; other edges bundled',
                      'mounted_bundle_matches_build':bool(args.compare), 'binaries':binaries,
                      'files_sha256':files, 'symlinks':links}, indent=2))


if __name__ == '__main__': main()
