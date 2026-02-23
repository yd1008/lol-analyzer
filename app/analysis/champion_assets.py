"""Champion asset helpers (Data Dragon icon URLs with cached name/id lookup)."""

import logging
import re
import threading
import time

import requests
from flask import has_app_context

logger = logging.getLogger(__name__)

_VERSIONS_URL = 'https://ddragon.leagueoflegends.com/api/versions.json'
_CHAMPIONS_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json'
_ITEMS_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/item.json'
_RUNES_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/runesReforged.json'
_ICON_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{champion_id}.png'
_ITEM_ICON_URL = 'https://ddragon.leagueoflegends.com/cdn/{version}/img/item/{item_id}.png'
_RUNE_ICON_URL = 'https://ddragon.leagueoflegends.com/cdn/img/{icon_path}'
_VERSION_SUCCESS_TTL_SECONDS = 6 * 3600
_VERSION_FAILURE_TTL_SECONDS = 120

_LOCK = threading.Lock()
_VERSION_CACHE = {'value': '', 'expires_at': 0.0}
_MAP_CACHE: dict[str, dict] = {}
_ITEM_CACHE: dict[str, dict] = {}
_RUNE_CACHE: dict[str, dict] = {}


def _cache_get(key: str):
    if not has_app_context():
        return None
    try:
        from app.extensions import cache
        return cache.get(key)
    except Exception:
        return None


def _cache_set(key: str, value, timeout: int) -> None:
    if not has_app_context():
        return
    try:
        from app.extensions import cache
        cache.set(key, value, timeout=timeout)
    except Exception:
        return


def _cache_delete(key: str) -> None:
    if not has_app_context():
        return
    try:
        from app.extensions import cache
        cache.delete(key)
    except Exception:
        return


def _normalize(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', (value or '').lower())


def _fetch_latest_version() -> str:
    shared_cached = _cache_get('champion_assets:latest_version')
    if isinstance(shared_cached, str) and shared_cached:
        return shared_cached

    now = time.time()
    with _LOCK:
        if _VERSION_CACHE['expires_at'] > now:
            return _VERSION_CACHE['value']

    version = ''
    fetch_success = False
    try:
        resp = requests.get(_VERSIONS_URL, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                version = data[0]
                fetch_success = True
    except requests.RequestException:
        version = ''

    with _LOCK:
        if fetch_success:
            _VERSION_CACHE['value'] = version
            _VERSION_CACHE['expires_at'] = now + _VERSION_SUCCESS_TTL_SECONDS
            _cache_set('champion_assets:latest_version', version, timeout=_VERSION_SUCCESS_TTL_SECONDS)
        else:
            # Back off quickly during outages; keep previous value if one exists.
            _VERSION_CACHE['expires_at'] = now + _VERSION_FAILURE_TTL_SECONDS
    return _VERSION_CACHE['value']


def _get_champion_map(version: str) -> dict:
    if not version:
        return {'by_name': {}, 'by_numeric': {}}

    shared_cached = _cache_get(f'champion_assets:map:{version}')
    if isinstance(shared_cached, dict):
        return shared_cached

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
    _cache_set(f'champion_assets:map:{version}', value, timeout=6 * 3600)
    return value


def _get_item_set(version: str) -> set[int]:
    if not version:
        return set()

    shared_cached = _cache_get(f'champion_assets:items:{version}')
    if isinstance(shared_cached, set):
        return shared_cached
    if isinstance(shared_cached, list):
        return set(shared_cached)

    now = time.time()
    with _LOCK:
        cached = _ITEM_CACHE.get(version)
        if cached and cached['expires_at'] > now:
            return cached['value']

    item_ids: set[int] = set()
    try:
        resp = requests.get(_ITEMS_URL.format(version=version), timeout=8)
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            if isinstance(data, dict):
                for item_id in data.keys():
                    try:
                        item_ids.add(int(item_id))
                    except (TypeError, ValueError):
                        continue
    except requests.RequestException:
        logger.debug("Failed to fetch Data Dragon item map for version %s", version)

    with _LOCK:
        _ITEM_CACHE[version] = {'expires_at': now + 6 * 3600, 'value': item_ids}
    _cache_set(f'champion_assets:items:{version}', list(item_ids), timeout=6 * 3600)
    return item_ids


def _get_rune_maps(version: str) -> dict:
    if not version:
        return {'perks': {}, 'styles': {}}

    shared_cached = _cache_get(f'champion_assets:runes:{version}')
    if isinstance(shared_cached, dict):
        return shared_cached

    now = time.time()
    with _LOCK:
        cached = _RUNE_CACHE.get(version)
        if cached and cached['expires_at'] > now:
            return cached['value']

    perk_icons: dict[int, str] = {}
    style_icons: dict[int, str] = {}
    try:
        resp = requests.get(_RUNES_URL.format(version=version), timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                for style in data:
                    style_id = style.get('id')
                    style_icon = style.get('icon', '')
                    if style_id and style_icon:
                        try:
                            style_icons[int(style_id)] = style_icon
                        except (TypeError, ValueError):
                            pass
                    slots = style.get('slots', [])
                    for slot in slots:
                        for rune in slot.get('runes', []):
                            rune_id = rune.get('id')
                            rune_icon = rune.get('icon', '')
                            if rune_id and rune_icon:
                                try:
                                    perk_icons[int(rune_id)] = rune_icon
                                except (TypeError, ValueError):
                                    pass
    except requests.RequestException:
        logger.debug("Failed to fetch Data Dragon rune map for version %s", version)

    value = {'perks': perk_icons, 'styles': style_icons}
    with _LOCK:
        _RUNE_CACHE[version] = {'expires_at': now + 6 * 3600, 'value': value}
    _cache_set(f'champion_assets:runes:{version}', value, timeout=6 * 3600)
    return value


def _versioned_rune_icon(version: str, icon_path: str) -> str:
    if not version or not icon_path:
        return ''
    return _RUNE_ICON_URL.format(icon_path=icon_path.strip('/'))


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


def item_icon_url(item_id: int | str | None) -> str:
    """Return item icon URL from Data Dragon, or empty string for invalid/unknown items."""
    version = _fetch_latest_version()
    if not version:
        return ''
    try:
        item_id_int = int(item_id or 0)
    except (TypeError, ValueError):
        return ''
    if item_id_int <= 0:
        return ''
    item_set = _get_item_set(version)
    if item_set and item_id_int not in item_set:
        return ''
    return _ITEM_ICON_URL.format(version=version, item_id=item_id_int)


def rune_icon_url(rune_id: int | str | None) -> str:
    """Return primary rune (perk) icon URL."""
    version = _fetch_latest_version()
    if not version:
        return ''
    try:
        rune_id_int = int(rune_id or 0)
    except (TypeError, ValueError):
        return ''
    if rune_id_int <= 0:
        return ''
    maps = _get_rune_maps(version)
    return _versioned_rune_icon(version, maps['perks'].get(rune_id_int, ''))


def rune_style_icon_url(style_id: int | str | None) -> str:
    """Return rune style icon URL."""
    version = _fetch_latest_version()
    if not version:
        return ''
    try:
        style_id_int = int(style_id or 0)
    except (TypeError, ValueError):
        return ''
    if style_id_int <= 0:
        return ''
    maps = _get_rune_maps(version)
    return _versioned_rune_icon(version, maps['styles'].get(style_id_int, ''))


def rune_icons(primary_rune_id: int | str | None, secondary_style_id: int | str | None) -> dict:
    """Return primary and secondary rune icons."""
    return {
        'primary': rune_icon_url(primary_rune_id),
        'secondary': rune_style_icon_url(secondary_style_id),
    }


def refresh_asset_caches(force: bool = False) -> dict:
    """Warm and refresh champion/item/rune caches.

    Returns summary metadata for logging/monitoring.
    """
    if force:
        with _LOCK:
            _VERSION_CACHE['expires_at'] = 0.0
        _cache_delete('champion_assets:latest_version')

    version = _fetch_latest_version()
    champion_count = 0
    item_count = 0
    rune_count = 0
    style_count = 0
    if version:
        champion_count = len(_get_champion_map(version).get('by_name', {}))
        item_count = len(_get_item_set(version))
        rune_maps = _get_rune_maps(version)
        rune_count = len(rune_maps.get('perks', {}))
        style_count = len(rune_maps.get('styles', {}))

    return {
        'version': version,
        'champion_aliases': champion_count,
        'items': item_count,
        'runes': rune_count,
        'styles': style_count,
    }
