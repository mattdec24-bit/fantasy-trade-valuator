"""Explicit metadata-only update checks. Import/status never contact the network."""
import json
from pathlib import Path
import re
from urllib.request import ProxyHandler, Request, build_opener

from evaluator.network import NoRedirect
from version import VERSION, version_tuple

CONFIG = Path(__file__).resolve().parent / 'release.json'
MAX_RESPONSE = 256 * 1024


def repository(path=CONFIG):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or set(value) != {'repository'}:
        raise ValueError('Invalid release configuration.')
    repo = value['repository']
    if repo is not None and (not isinstance(repo, str) or not re.fullmatch(
            r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', repo)
            or repo.split('/')[1] in {'.', '..'}):
        raise ValueError('Release repository must be null or owner/repository.')
    return repo


def status():
    return {'current_version': VERSION, 'enabled': repository() is not None}


def check():
    repo = repository()
    if repo is None:
        return status() | {'state': 'disabled'}
    request = Request(f'https://api.github.com/repos/{repo}/releases/latest', headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': f'TradeRoom/{VERSION}',
        'X-GitHub-Api-Version': '2022-11-28'})
    try:
        # No credentials, cookies, proxies or redirects. No asset request or install.
        with build_opener(ProxyHandler({}), NoRedirect).open(request, timeout=8) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError('Oversized release response')
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get('draft') is not False or data.get('prerelease') is not False:
            raise ValueError('Expected a published stable release')
        tag = data.get('tag_name')
        if not isinstance(tag, str) or not tag.startswith('v'):
            raise ValueError('Expected a stable release tag')
        latest = tag[1:]
        newer = version_tuple(latest) > version_tuple(VERSION)
        # Never trust a URL, HTML or release prose from the response.
        return status() | {'state': 'available' if newer else 'current', 'latest_version': latest,
                           'release_url': f'https://github.com/{repo}/releases/tag/v{latest}'}
    except Exception:
        raise ValueError('Could not check releases. Check your connection or try later. No update was downloaded.') from None
