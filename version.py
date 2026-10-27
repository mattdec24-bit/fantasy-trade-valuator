"""One release version shared by the source server and packaged desktop app."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})', value):
        raise ValueError('Use a stable major.minor.patch version (no leading zeros).')
    result = tuple(map(int, value.split('.')))
    if result[0] == 0:
        raise ValueError('Release versions must start at 1.0.0.')
    return result


VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
version_tuple(VERSION)
