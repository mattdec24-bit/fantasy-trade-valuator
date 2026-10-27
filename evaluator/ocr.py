"""Local OCR with no disk writes, remote requests, or retained upload state."""
from difflib import SequenceMatcher
from io import BytesIO
import re
import importlib.util
from pathlib import Path
import shutil
import subprocess
import warnings

MAX_UPLOAD = 5 * 1024 * 1024
_native_helper = None


def configure_native(path):
    """Desktop-only fixed bundled helper, never discovered from PATH or uploads."""
    global _native_helper
    helper = Path(path).resolve()
    try:
        result = subprocess.run([str(helper), 'ocr-check'], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=15, check=True)
        if result.stdout.strip() != b'apple-vision-en-US':
            raise ValueError
    except (OSError, subprocess.SubprocessError, ValueError):
        raise ValueError('Bundled on-device English OCR is unavailable') from None
    _native_helper = str(helper)


def available():
    return bool(_native_helper or shutil.which('tesseract')) and importlib.util.find_spec('PIL') is not None


def key(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


def suggestions(text, league):
    players = [(p, t.id) for t in league.teams for p in t.players]
    rows = []
    for line in text.splitlines()[:100]:
        line = line.strip()[:200]
        if not line:
            continue
        normalized = key(line)
        matches = sorted(((1.0 if key(p.name) in normalized else SequenceMatcher(None, normalized, key(p.name)).ratio(), p, tid)
                          for p, tid in players), key=lambda v: (-v[0], v[1].id))[:3]
        choices = [{'player_id': p.id, 'team_id': tid, 'name': p.name, 'confidence': round(score, 2)}
                   for score, p, tid in matches if score >= .45]
        rows.append({'text': line, 'matches': choices})
    return rows


def extract(image_bytes):
    if not image_bytes or len(image_bytes) > MAX_UPLOAD:
        raise ValueError('Upload a PNG or JPEG screenshot up to 5 MiB')
    try:
        from PIL import Image
    except ImportError:
        raise ValueError('Install Pillow to enable local screenshot OCR') from None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            with Image.open(BytesIO(image_bytes)) as source:
                if source.format not in {'PNG', 'JPEG'} or source.width * source.height > 16_000_000 or getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('Use a single PNG/JPEG image with at most 16 million pixels')
                source.load()
                with source.convert('RGB') as decoded:
                    decoded.thumbnail((2800, 2800))
                    # A new pixel-only image inherits neither info nor EXIF state.
                    image = Image.new('RGB', decoded.size)
                    image.paste(decoded)
                clean = BytesIO()
                with image:
                    image.save(clean, format='PNG')
    except Exception:
        raise ValueError('Invalid, unsupported, or oversized PNG/JPEG image') from None
    binary = _native_helper or shutil.which('tesseract')
    if not binary:
        raise ValueError('Tesseract is not installed; manual player selection remains available')
    try:
        command = [binary, 'ocr'] if _native_helper else [binary, 'stdin', 'stdout', '-l', 'eng', '--psm', '6']
        result = subprocess.run(command,
                                input=clean.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=15, check=True)
    except (subprocess.SubprocessError, OSError):
        raise ValueError('Local OCR failed or timed out; try a clearer crop or select players manually') from None
    return result.stdout.decode('utf-8', errors='replace')[:12000]
