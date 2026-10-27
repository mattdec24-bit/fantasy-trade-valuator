"""Reviewable runtime manifest; new files in approved directories are automatic."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def bundle_files(root=ROOT):
    root = root.resolve()
    manifest = json.loads((root / 'macos/bundle-files.json').read_text())
    result = set(manifest['files'])
    for name, suffixes in manifest['directories'].items():
        directory = root / name
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError('Invalid runtime directory: ' + name)
        for path in directory.rglob('*'):
            relative = path.relative_to(root)
            if '__pycache__' in relative.parts or path.name == '.DS_Store':
                continue
            if path.is_symlink():
                raise ValueError('Runtime links are not allowed: ' + str(relative))
            if path.is_file():
                if path.suffix not in suffixes or any(p.startswith('.') for p in relative.parts):
                    raise ValueError('Review new runtime file type in macos/bundle-files.json: ' + str(relative))
                result.add(relative.as_posix())
    for name in result:
        path = root / name
        if (Path(name).is_absolute() or '..' in Path(name).parts or not path.is_file()
                or any(part.startswith('.') for part in Path(name).parts)
                or any(parent.is_symlink() for parent in [path, *path.parents] if parent.is_relative_to(root))
                or not path.resolve().is_relative_to(root.resolve())):
            raise ValueError('Unsafe/missing runtime file: ' + name)
    return sorted(result)
