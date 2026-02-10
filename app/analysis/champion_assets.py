"""Champion asset helpers (Data Dragon icon URLs with cached name/id lookup)."""

import logging
import re
import threading
import time

import requests

logger = logging.getLogger(__name__)

_VERSIONS_URL = 'https://ddragon.leagueoflegends.com/api/versions.json'
_CHAMPIONS_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json'
_ICON_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{champion_id}.png'

_LOCK = threading.Lock()
_VERSION_CACHE = {'value': '', 'expires_at': 0.0}
_MAP_CACHE: dict[str, dict] = {}


def _normalize(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', (value or '').lower())


def _fetch_latest_version() -> str:
    now = time.time()
    with _LOCK:
        if _VERSION_CACHE['expires_at'] > now and _VERSION_CACHE['value']:
            return _VERSION_CACHE['value']

    version = ''
    try:
        resp = requests.get(_VERSIONS_URL, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                version = data[0]
    except requests.RequestException:
        version = ''

    with _LOCK:
        _VERSION_CACHE['value'] = version
        _VERSION_CACHE['expires_at'] = now + 6 * 3600
    return version


def _get_champion_map(version: str) -> dict:
    if not version:
        return {'by_name': {}, 'by_numeric': {}}

    now = time.time()
    with _LOCK:
        cached = _MAP_CACHE.get(version)
        if cached and cached['expires_at'] > now:
            return cached['value']

    by_name: dict[str, str] = {}
    by_numeric: dict[str, str] = {}
    try:
        resp = requests.get(_CHAMPIONS_URL.format(version=version), timeout=8)
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            if isinstance(data, dict):
                for champ in data.values():
                    champ_id = champ.get('id', '')
                    champ_key = str(champ.get('key', ''))
                    aliases = {
                        _normalize(champ_id),
                        _normalize(champ.get('name', '')),
                        _normalize(champ_key),
                    }
                    for alias in aliases:
                        if alias:
                            by_name[alias] = champ_id
                    if champ_key:
                        by_numeric[champ_key] = champ_id
    except requests.RequestException:
        logger.debug("Failed to fetch Data Dragon champion map for version %s", version)

    value = {'by_name': by_name, 'by_numeric': by_numeric}
    with _LOCK:
        _MAP_CACHE[version] = {'expires_at': now + 6 * 3600, 'value': value}
    return value


def champion_icon_url(champion_name: str, champion_numeric_id: int | str | None = None) -> str:
    """Return champion square icon URL from Data Dragon, or empty string if unresolved."""
    version = _fetch_latest_version()
    if not version:
        return ''

    mapping = _get_champion_map(version)
    champ_id = ''
    numeric = str(champion_numeric_id or '').strip()
    if numeric:
        champ_id = mapping['by_numeric'].get(numeric, '')

    if not champ_id and champion_name:
        champ_id = mapping['by_name'].get(_normalize(champion_name), '')

    if not champ_id:
        # Last-resort best effort: strip non-alnum to keep a plausible Data Dragon id.
        fallback = re.sub(r'[^A-Za-z0-9]+', '', champion_name or '')
        champ_id = fallback

    if not champ_id:
        return ''

    return _ICON_URL.format(version=version, champion_id=champ_id)
