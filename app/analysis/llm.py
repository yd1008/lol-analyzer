"""LLM-powered match analysis with a knowledge-enriched prompt pipeline."""

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import requests
from flask import current_app
from riotwatcher import ApiError

from app.analysis.riot_api import get_watcher

logger = logging.getLogger(__name__)

_TIER_ORDER = {
    'IRON': 0,
    'BRONZE': 1,
    'SILVER': 2,
    'GOLD': 3,
    'PLATINUM': 4,
    'EMERALD': 5,
    'DIAMOND': 6,
    'MASTER': 7,
    'GRANDMASTER': 8,
    'CHALLENGER': 9,
}
_DIVISION_ORDER = {'IV': 1, 'III': 2, 'II': 3, 'I': 4}
_RANKED_QUEUE_MAP = {
    'Ranked Solo': 'RANKED_SOLO_5x5',
    'Ranked Flex': 'RANKED_FLEX_SR',
}
_DDRAGON_VERSIONS_URL = 'https://ddragon.leagueoflegends.com/api/versions.json'
_DDRAGON_CHAMPIONS_URL = 'https://ddragon.leagueoflegends.com/cdn/{patch}/data/en_US/champion.json'
_DDRAGON_ITEMS_URL = 'https://ddragon.leagueoflegends.com/cdn/{patch}/data/en_US/item.json'
_OPENCODE_ZEN_MODELS_URL = 'https://opencode.ai/zen/v1/models'
_OPENCODE_ZEN_DEFAULT_CHAT_MODEL = 'glm-4.7-free'
_OPENCODE_ZEN_CHAT_HINT_MODELS = ('glm-4.7-free', 'kimi-k2.5-free', 'big-pickle')
_LOCAL_KNOWLEDGE_DEFAULT = Path(__file__).with_name('knowledge').joinpath('game_knowledge.json')

_CACHE_LOCK = threading.Lock()
_PATCH_CACHE = {'expires_at': 0.0, 'value': ''}
_DDRAGON_CACHE = {}
_RANK_CACHE = {}
_LOCAL_KNOWLEDGE_CACHE = {'path': None, 'mtime': None, 'data': {}}
_OPENCODE_MODELS_CACHE = {'expires_at': 0.0, 'models': set()}


def _external_knowledge_enabled() -> bool:
    """Whether remote knowledge fetches are enabled for this environment."""
    default = not current_app.config.get('TESTING', False)
    return bool(current_app.config.get('LLM_KNOWLEDGE_EXTERNAL', default))


def _format_position(pos: str) -> str:
    """Convert Riot position code to readable label."""
    return {'TOP': 'Top', 'JUNGLE': 'Jungle', 'MIDDLE': 'Mid', 'BOTTOM': 'Bot', 'UTILITY': 'Support'}.get(pos, pos)


def _is_opencode_zen_url(api_url: str) -> bool:
    return 'opencode.ai/zen/' in (api_url or '').strip().lower()


def _fetch_opencode_zen_models() -> set[str]:
    """Fetch available OpenCode Zen model ids with short-lived cache."""
    now = time.time()
    with _CACHE_LOCK:
        if _OPENCODE_MODELS_CACHE['expires_at'] > now:
            return set(_OPENCODE_MODELS_CACHE['models'])

    models: set[str] = set()
    try:
        resp = requests.get(_OPENCODE_ZEN_MODELS_URL, timeout=4)
        if resp.status_code == 200:
            data = resp.json().get('data', [])
            if isinstance(data, list):
                for row in data:
                    model_id = str((row or {}).get('id', '')).strip()
                    if model_id:
                        models.add(model_id)
    except requests.RequestException:
        models = set()

    with _CACHE_LOCK:
        _OPENCODE_MODELS_CACHE['models'] = set(models)
        _OPENCODE_MODELS_CACHE['expires_at'] = now + 900
    return models


def _resolve_provider_model(api_url: str, model: str) -> tuple[str | None, str | None]:
    """Validate/adapt model for provider endpoint quirks."""
    model = (model or '').strip()
    if not model:
        return None, 'LLM_MODEL is not set.'

    normalized_url = (api_url or '').strip().lower()
    if not _is_opencode_zen_url(normalized_url):
        return model, None

    if not normalized_url.endswith('/chat/completions'):
        return None, (
            "OpenCode Zen endpoint is not chat-completions compatible for this app. "
            "Set LLM_API_URL to https://opencode.ai/zen/v1/chat/completions."
        )

    if model == 'deepseek-chat':
        logger.warning(
            "LLM_MODEL=deepseek-chat is unavailable on OpenCode Zen. Falling back to %s.",
            _OPENCODE_ZEN_DEFAULT_CHAT_MODEL,
        )
        model = _OPENCODE_ZEN_DEFAULT_CHAT_MODEL

    if model.startswith(('gpt-', 'claude-', 'gemini-')):
        hint = ', '.join(_OPENCODE_ZEN_CHAT_HINT_MODELS)
        return None, (
            f"Model '{model}' on OpenCode Zen is not compatible with /chat/completions. "
            f"Use a chat-completions model such as: {hint}."
        )

    available_models = _fetch_opencode_zen_models()
    if available_models and model not in available_models:
        hint = ', '.join(_OPENCODE_ZEN_CHAT_HINT_MODELS)
        return None, (
            f"LLM model '{model}' is not available on OpenCode Zen. "
            f"Choose a model listed by {_OPENCODE_ZEN_MODELS_URL} (for example: {hint})."
        )
    return model, None


def _normalize_text(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', (value or '').lower())


def _strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text or '').replace('\n', ' ').strip()


def _soft_text_clean(value: str) -> str:
    """Convert markdown-ish formatting to plain text for UI-safe rendering."""
    text = (value or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        return ''

    text = re.sub(r'^\s{0,3}#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*>\s?', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+[.)]\s+', '', text, flags=re.MULTILINE)

    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'[*_]{1,3}([^*_]+)[*_]{1,3}', r'\1', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _safe_percentage(wins: int, losses: int) -> float:
    total = wins + losses
    return round((wins * 100) / total, 1) if total else 0.0


def _participant_kda(participant: dict) -> float:
    return round(_safe_ratio(participant.get('kills', 0) + participant.get('assists', 0), max(1, participant.get('deaths', 0))), 2)


def _participant_metrics(participant: dict, duration_minutes: float) -> dict:
    return {
        'kda': _participant_kda(participant),
        'gpm': round(_safe_ratio(participant.get('gold_earned', 0), duration_minutes), 2),
        'dpm': round(_safe_ratio(participant.get('total_damage', 0), duration_minutes), 2),
        'cspm': round(_safe_ratio(participant.get('cs', 0), duration_minutes), 2),
        'vpm': round(_safe_ratio(participant.get('vision_score', 0), duration_minutes), 2),
    }


def _median_metric(metric_dicts: list[dict], key: str) -> float:
    values = [m[key] for m in metric_dicts if key in m]
    return round(median(values), 2) if values else 0.0


def _describe_delta(player_value: float, baseline_value: float, label: str, unit: str = '') -> str:
    delta = round(player_value - baseline_value, 2)
    if abs(delta) < 0.01:
        return f'{label}: on par ({player_value}{unit})'
    direction = 'above' if delta > 0 else 'below'
    return f'{label}: {abs(delta)}{unit} {direction} baseline ({player_value}{unit} vs {baseline_value}{unit})'


def _rank_queue_for_analysis(analysis: dict) -> str:
    return _RANKED_QUEUE_MAP.get(analysis.get('queue_type', ''), '')


def _rank_score(entry: dict) -> float:
    tier = (entry.get('tier') or '').upper()
    division = (entry.get('rank') or '').upper()
    lp = entry.get('leaguePoints', 0) or 0
    return (_TIER_ORDER.get(tier, -1) * 100) + (_DIVISION_ORDER.get(division, 0) * 10) + (lp / 100)


def _format_rank_entry(entry: dict | None) -> str:
    if not entry:
        return 'Unranked/Unavailable'
    tier = entry.get('tier', '?')
    rank = entry.get('rank', '')
    lp = entry.get('leaguePoints', 0)
    wins = entry.get('wins', 0)
    losses = entry.get('losses', 0)
    wr = _safe_percentage(wins, losses)
    return f'{tier} {rank} ({lp} LP, {wr}% WR)'


def _choose_rank_entry(entries: list[dict], rank_queue: str) -> dict | None:
    if not entries:
        return None
    if rank_queue:
        for entry in entries:
            if entry.get('queueType') == rank_queue:
                return entry
    return entries[0]


def _find_player_and_teams(participants: list[dict]) -> tuple[dict | None, list[dict], list[dict]]:
    player = next((p for p in participants if p.get('is_player')), None)
    if not player:
        return None, [], []
    team_id = player.get('team_id')
    allies = [p for p in participants if p.get('team_id') == team_id]
    enemies = [p for p in participants if p.get('team_id') != team_id]
    return player, allies, enemies


def _knowledge_file_path() -> Path:
    configured = (current_app.config.get('LLM_KNOWLEDGE_FILE') or '').strip()
    return Path(configured) if configured else _LOCAL_KNOWLEDGE_DEFAULT


def _load_local_knowledge() -> dict:
    path = _knowledge_file_path()
    if not path.exists():
        return {}
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    with _CACHE_LOCK:
        if _LOCAL_KNOWLEDGE_CACHE['path'] == str(path) and _LOCAL_KNOWLEDGE_CACHE['mtime'] == mtime:
            return _LOCAL_KNOWLEDGE_CACHE['data']
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            data = {}
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to load local LoL knowledge file: %s", path)
        data = {}
    with _CACHE_LOCK:
        _LOCAL_KNOWLEDGE_CACHE['path'] = str(path)
        _LOCAL_KNOWLEDGE_CACHE['mtime'] = mtime
        _LOCAL_KNOWLEDGE_CACHE['data'] = data
    return data


def _fetch_current_patch() -> str:
    if not _external_knowledge_enabled():
        return ''
    now = time.time()
    with _CACHE_LOCK:
        if _PATCH_CACHE['expires_at'] > now:
            return _PATCH_CACHE['value']
    patch = ''
    try:
        resp = requests.get(_DDRAGON_VERSIONS_URL, timeout=5)
        if resp.status_code == 200:
            versions = resp.json()
            if isinstance(versions, list) and versions:
                patch = versions[0]
    except requests.RequestException:
        patch = ''
    with _CACHE_LOCK:
        _PATCH_CACHE['value'] = patch
        _PATCH_CACHE['expires_at'] = now + 6 * 3600
    return patch


def _fetch_ddragon_data(patch: str) -> tuple[dict, dict]:
    """Return (champion_lookup, item_lookup) keyed by normalized aliases/id."""
    if not patch or not _external_knowledge_enabled():
        return {}, {}
    now = time.time()
    with _CACHE_LOCK:
        cached = _DDRAGON_CACHE.get(patch)
        if cached and cached['expires_at'] > now:
            return cached['champions'], cached['items']
    champion_lookup: dict[str, dict] = {}
    item_lookup: dict[int, dict] = {}
    try:
        champ_resp = requests.get(_DDRAGON_CHAMPIONS_URL.format(patch=patch), timeout=6)
        item_resp = requests.get(_DDRAGON_ITEMS_URL.format(patch=patch), timeout=6)
        if champ_resp.status_code == 200:
            champ_data = champ_resp.json().get('data', {})
            if isinstance(champ_data, dict):
                for champ in champ_data.values():
                    aliases = {
                        _normalize_text(champ.get('id', '')),
                        _normalize_text(champ.get('name', '')),
                        _normalize_text(champ.get('key', '')),
                    }
                    for alias in aliases:
                        if alias:
                            champion_lookup[alias] = champ
        if item_resp.status_code == 200:
            items = item_resp.json().get('data', {})
            if isinstance(items, dict):
                for item_id, item in items.items():
                    try:
                        item_lookup[int(item_id)] = item
                    except (TypeError, ValueError):
                        continue
    except requests.RequestException:
        champion_lookup = {}
        item_lookup = {}
    with _CACHE_LOCK:
        _DDRAGON_CACHE[patch] = {
            'expires_at': now + 6 * 3600,
            'champions': champion_lookup,
            'items': item_lookup,
        }
    return champion_lookup, item_lookup


def _resolve_champion(champion_name: str, champion_lookup: dict) -> dict | None:
    return champion_lookup.get(_normalize_text(champion_name))


def _phase_label(level: int) -> str:
    return {0: 'weak', 1: 'average', 2: 'strong'}.get(level, 'average')


def _champion_phase_profile(champion: dict | None, overrides: dict) -> dict:
    if not champion:
        return {}
    champion_name = champion.get('name') or champion.get('id', '')
    override = overrides.get(_normalize_text(champion_name))
    if isinstance(override, dict):
        return {
            'early': override.get('early', 'average'),
            'mid': override.get('mid', 'average'),
            'late': override.get('late', 'average'),
            'notes': override.get('notes', ''),
            'source': 'local_override',
            'tags': champion.get('tags', []),
        }

    early, mid, late = 1, 1, 1
    tags = set(champion.get('tags', []))
    if 'Marksman' in tags:
        early -= 1
        late += 1
    if 'Assassin' in tags:
        early += 1
        late -= 1
    if 'Mage' in tags:
        late += 1
    if 'Tank' in tags:
        early -= 1
        mid += 1
        late += 1
    if 'Support' in tags:
        early += 1
        mid += 1
    if 'Fighter' in tags:
        early += 1
        mid += 1

    stats = champion.get('stats', {})
    hp = stats.get('hp', 0.0)
    hp_growth = stats.get('hpperlevel', 0.0)
    ad = stats.get('attackdamage', 0.0)
    ad_growth = stats.get('attackdamageperlevel', 0.0)
    armor = stats.get('armor', 0.0)
    armor_growth = stats.get('armorperlevel', 0.0)
    mr = stats.get('spellblock', 0.0)
    mr_growth = stats.get('spellblockperlevel', 0.0)
    base_power = hp + (ad * 1.5) + ((armor + mr) * 8)
    late_power = (hp + hp_growth * 18) + ((ad + ad_growth * 18) * 1.5) + ((armor + armor_growth * 18 + mr + mr_growth * 18) * 8)
    growth_ratio = _safe_ratio(late_power, max(base_power, 1))
    if growth_ratio >= 2.2:
        early -= 1
        late += 1
    elif growth_ratio <= 1.8:
        early += 1
        late -= 1

    return {
        'early': _phase_label(_clamp(early, 0, 2)),
        'mid': _phase_label(_clamp(mid, 0, 2)),
        'late': _phase_label(_clamp(late, 0, 2)),
        'notes': f"Heuristic profile from champion tags ({', '.join(sorted(tags))}) and stat growth.",
        'source': 'heuristic',
        'tags': sorted(tags),
    }


def _fetch_rank_entries(platform_region: str, summoner_id: str) -> list[dict]:
    if not _external_knowledge_enabled():
        return []
    if not platform_region or not summoner_id:
        return []
    if not current_app.config.get('RIOT_API_KEY'):
        return []

    key = (platform_region, summoner_id)
    now = time.time()
    with _CACHE_LOCK:
        cached = _RANK_CACHE.get(key)
        if cached and cached['expires_at'] > now:
            return cached['entries']

    entries: list[dict] = []
    try:
        watcher = get_watcher()
        response = watcher.league.by_summoner(platform_region, summoner_id)
        if isinstance(response, list):
            entries = response
    except (ValueError, ApiError, Exception):
        entries = []

    with _CACHE_LOCK:
        _RANK_CACHE[key] = {'expires_at': now + 1800, 'entries': entries}
    return entries


def _build_rank_context(analysis: dict, participants: list[dict], duration_minutes: float) -> dict:
    context = {'available': False}
    rank_queue = _rank_queue_for_analysis(analysis)
    if not rank_queue:
        context['message'] = 'Non-ranked queue: rank benchmark skipped.'
        return context

    platform_region = analysis.get('platform_region', '')
    if not platform_region:
        context['message'] = 'Missing platform region for rank lookup.'
        return context

    player, _, _ = _find_player_and_teams(participants)
    player_summoner_id = analysis.get('player_summoner_id') or (player or {}).get('summoner_id', '')
    if not player_summoner_id:
        context['message'] = 'Missing summoner ID for rank lookup.'
        return context

    player_rank = _choose_rank_entry(_fetch_rank_entries(platform_region, player_summoner_id), rank_queue)
    if not player_rank:
        context['message'] = 'Player rank not available from Riot League API.'
        return context

    rank_by_summoner: dict[str, dict] = {}
    for participant in participants:
        sid = participant.get('summoner_id', '')
        if not sid:
            continue
        entry = _choose_rank_entry(_fetch_rank_entries(platform_region, sid), rank_queue)
        if entry:
            rank_by_summoner[sid] = entry

    tier_counts = {}
    rank_scores = []
    for entry in rank_by_summoner.values():
        tier = entry.get('tier', 'UNRANKED')
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        rank_scores.append(_rank_score(entry))

    player_score = _rank_score(player_rank)
    nearby_peers = []
    for participant in participants:
        sid = participant.get('summoner_id', '')
        entry = rank_by_summoner.get(sid)
        if entry and abs(_rank_score(entry) - player_score) <= 120:
            nearby_peers.append(participant)

    benchmark_lines = []
    if player and len(nearby_peers) >= 2:
        peer_metrics = [_participant_metrics(p, duration_minutes) for p in nearby_peers]
        player_metrics = _participant_metrics(player, duration_minutes)
        benchmark_lines = [
            _describe_delta(player_metrics['gpm'], _median_metric(peer_metrics, 'gpm'), 'Gold/min vs similar-rank lobby', '/min'),
            _describe_delta(player_metrics['dpm'], _median_metric(peer_metrics, 'dpm'), 'Damage/min vs similar-rank lobby', '/min'),
            _describe_delta(player_metrics['cspm'], _median_metric(peer_metrics, 'cspm'), 'CS/min vs similar-rank lobby', '/min'),
            _describe_delta(player_metrics['vpm'], _median_metric(peer_metrics, 'vpm'), 'Vision/min vs similar-rank lobby', '/min'),
        ]

    score_min = min(rank_scores) if rank_scores else None
    score_max = max(rank_scores) if rank_scores else None
    context.update({
        'available': True,
        'queue': rank_queue,
        'player_rank': _format_rank_entry(player_rank),
        'sample_size': len(rank_by_summoner),
        'tier_distribution': tier_counts,
        'rank_spread': [round(score_min, 2), round(score_max, 2)] if score_min is not None and score_max is not None else [],
        'nearby_peer_count': len(nearby_peers),
        'benchmarks': [line for line in benchmark_lines if line],
    })
    return context


def _build_item_context(analysis: dict, player: dict | None, item_lookup: dict) -> dict:
    item_ids = analysis.get('item_ids') or (player or {}).get('item_ids') or []
    if not item_ids:
        return {'items': [], 'tags': {}}

    items = []
    tag_counts: dict[str, int] = {}
    for item_id in item_ids:
        item_data = item_lookup.get(item_id, {})
        item_name = item_data.get('name', f'Item {item_id}')
        tags = item_data.get('tags', [])
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        items.append({
            'id': item_id,
            'name': item_name,
            'tags': tags,
            'description': _strip_html(item_data.get('description', '')),
        })
    return {'items': items, 'tags': tag_counts}


def _team_summary(team: list[dict], champion_lookup: dict, phase_overrides: dict) -> dict:
    tag_counts: dict[str, int] = {}
    phase_counts = {'early': 0, 'mid': 0, 'late': 0}
    for participant in team:
        champion_name = participant.get('champion', '')
        champ_data = _resolve_champion(champion_name, champion_lookup)
        profile = _champion_phase_profile(champ_data, phase_overrides) if champ_data else {}
        for tag in profile.get('tags', []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        if profile.get('early') == 'strong':
            phase_counts['early'] += 1
        if profile.get('mid') == 'strong':
            phase_counts['mid'] += 1
        if profile.get('late') == 'strong':
            phase_counts['late'] += 1

    notes = []
    frontline = tag_counts.get('Tank', 0) + tag_counts.get('Fighter', 0)
    backline = tag_counts.get('Mage', 0) + tag_counts.get('Marksman', 0)
    if frontline <= 1:
        notes.append('Limited frontline durability.')
    if frontline >= 2 and backline >= 2:
        notes.append('Balanced front-to-back teamfight structure.')
    physical = tag_counts.get('Marksman', 0) + tag_counts.get('Assassin', 0) + tag_counts.get('Fighter', 0)
    magic = tag_counts.get('Mage', 0) + tag_counts.get('Support', 0)
    if physical >= 4:
        notes.append('Damage profile skews physical; armor stacking is a risk.')
    if magic >= 4:
        notes.append('Damage profile skews magic; MR stacking is a risk.')
    strongest_phase = max(phase_counts, key=phase_counts.get) if team else ''
    if strongest_phase:
        notes.append(f'Power spike bias: {strongest_phase} game.')
    return {'tags': tag_counts, 'phase_counts': phase_counts, 'notes': notes}


def _build_synergy_notes(allies: list[dict], local_knowledge: dict) -> list[str]:
    synergy_rules = local_knowledge.get('synergy_pairs', [])
    if not isinstance(synergy_rules, list):
        return []
    ally_set = {_normalize_text(p.get('champion', '')) for p in allies}
    notes = []
    for rule in synergy_rules:
        if not isinstance(rule, dict):
            continue
        champs = rule.get('champions', [])
        if not isinstance(champs, list) or len(champs) < 2:
            continue
        needed = {_normalize_text(name) for name in champs}
        if needed.issubset(ally_set):
            reason = rule.get('reason', 'Strong interaction pattern.')
            notes.append(f"{'/'.join(champs)}: {reason}")
    return notes


def _build_team_comp_context(participants: list[dict], champion_lookup: dict, local_knowledge: dict) -> dict:
    player, allies, enemies = _find_player_and_teams(participants)
    if not player:
        return {}
    phase_overrides = local_knowledge.get('champion_phase_overrides', {})
    if not isinstance(phase_overrides, dict):
        phase_overrides = {}
    return {
        'ally': _team_summary(allies, champion_lookup, phase_overrides),
        'enemy': _team_summary(enemies, champion_lookup, phase_overrides),
        'synergy_notes': _build_synergy_notes(allies, local_knowledge),
    }


def _build_relative_performance_context(analysis: dict, participants: list[dict], duration_minutes: float) -> dict:
    player, allies, _ = _find_player_and_teams(participants)
    if not player:
        return {}
    lobby_metrics = [_participant_metrics(p, duration_minutes) for p in participants]
    player_metrics = _participant_metrics(player, duration_minutes)
    lines = [
        _describe_delta(player_metrics['gpm'], _median_metric(lobby_metrics, 'gpm'), 'Gold/min vs full lobby', '/min'),
        _describe_delta(player_metrics['dpm'], _median_metric(lobby_metrics, 'dpm'), 'Damage/min vs full lobby', '/min'),
        _describe_delta(player_metrics['cspm'], _median_metric(lobby_metrics, 'cspm'), 'CS/min vs full lobby', '/min'),
        _describe_delta(player_metrics['vpm'], _median_metric(lobby_metrics, 'vpm'), 'Vision/min vs full lobby', '/min'),
    ]
    team_gold = sum(p.get('gold_earned', 0) for p in allies)
    team_damage = sum(p.get('total_damage', 0) for p in allies)
    if team_gold:
        lines.append(f"Gold share on own team: {round(player.get('gold_earned', 0) * 100 / team_gold, 1)}%")
    if team_damage:
        lines.append(f"Damage share on own team: {round(player.get('total_damage', 0) * 100 / team_damage, 1)}%")
    role_peers = []
    position = player.get('position', '')
    if position:
        role_peers = [p for p in participants if p.get('position') == position and not p.get('is_player')]
    if role_peers:
        role_metrics = [_participant_metrics(p, duration_minutes) for p in role_peers]
        lines.append(_describe_delta(player_metrics['dpm'], _median_metric(role_metrics, 'dpm'), f'Damage/min vs {_format_position(position)} counterpart', '/min'))
        lines.append(_describe_delta(player_metrics['cspm'], _median_metric(role_metrics, 'cspm'), f'CS/min vs {_format_position(position)} counterpart', '/min'))

    lane_opp = analysis.get('lane_opponent')
    lane_text = ''
    if lane_opp:
        lane_kda = round(_safe_ratio(lane_opp.get('kills', 0) + lane_opp.get('assists', 0), max(1, lane_opp.get('deaths', 0))), 2)
        lane_gold = round(_safe_ratio(lane_opp.get('gold_earned', 0), duration_minutes), 2)
        lane_dpm = round(_safe_ratio(lane_opp.get('total_damage', 0), duration_minutes), 2)
        lane_cspm = round(_safe_ratio(lane_opp.get('cs', 0), duration_minutes), 2)
        lane_text = (
            f"Lane matchup vs {lane_opp.get('champion', '?')}: "
            f"KDA {player_metrics['kda']} vs {lane_kda}, "
            f"GPM {player_metrics['gpm']} vs {lane_gold}, "
            f"DPM {player_metrics['dpm']} vs {lane_dpm}, "
            f"CSPM {player_metrics['cspm']} vs {lane_cspm}."
        )
    return {'lines': [line for line in lines if line], 'lane_matchup_line': lane_text}


def _build_champion_context(analysis: dict, champion_lookup: dict, local_knowledge: dict) -> dict:
    phase_overrides = local_knowledge.get('champion_phase_overrides', {})
    if not isinstance(phase_overrides, dict):
        phase_overrides = {}
    player_champion = _resolve_champion(analysis.get('champion', ''), champion_lookup)
    player_profile = _champion_phase_profile(player_champion, phase_overrides) if player_champion else {}
    lane_profile = {}
    lane_opponent = analysis.get('lane_opponent')
    if lane_opponent:
        lane_champion = _resolve_champion(lane_opponent.get('champion', ''), champion_lookup)
        lane_profile = _champion_phase_profile(lane_champion, phase_overrides) if lane_champion else {}
    return {'player_profile': player_profile, 'lane_profile': lane_profile}


def _build_patch_context(local_knowledge: dict) -> dict:
    patch = _fetch_current_patch()
    patch_notes_map = local_knowledge.get('patch_notes', {})
    if not isinstance(patch_notes_map, dict):
        patch_notes_map = {}
    notes = []
    if patch:
        notes.extend(patch_notes_map.get(patch, []))
        patch_mm = '.'.join(patch.split('.')[:2])
        if not notes and patch_mm:
            notes.extend(patch_notes_map.get(patch_mm, []))
        patch_major = patch.split('.')[0]
        if not notes and patch_major:
            notes.extend(patch_notes_map.get(patch_major, []))
    default_notes = local_knowledge.get('default_patch_notes', [])
    if not notes and isinstance(default_notes, list):
        notes = default_notes
    return {'current_patch': patch, 'notes': notes}


def _build_match_timestamp_context(analysis: dict) -> str:
    timestamp = analysis.get('game_start_timestamp')
    if not timestamp:
        return ''
    try:
        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        return dt.strftime('%Y-%m-%d %H:%M UTC')
    except (TypeError, ValueError, OSError):
        return ''


def _build_knowledge_context(analysis: dict) -> dict:
    participants = analysis.get('participants') or []
    duration_minutes = max(float(analysis.get('game_duration', 0) or 0), 1.0)
    local_knowledge = _load_local_knowledge()
    patch_context = _build_patch_context(local_knowledge)
    champion_lookup, item_lookup = _fetch_ddragon_data(patch_context.get('current_patch', ''))
    player, _, _ = _find_player_and_teams(participants)
    return {
        'match_played_at': _build_match_timestamp_context(analysis),
        'patch': patch_context,
        'champions': _build_champion_context(analysis, champion_lookup, local_knowledge),
        'items': _build_item_context(analysis, player, item_lookup),
        'team_comp': _build_team_comp_context(participants, champion_lookup, local_knowledge),
        'relative_performance': _build_relative_performance_context(analysis, participants, duration_minutes),
        'rank': _build_rank_context(analysis, participants, duration_minutes),
    }


def _phase_summary(profile: dict) -> str:
    if not profile:
        return 'unknown'
    note = profile.get('notes', '')
    source = profile.get('source', '')
    suffix = f" ({source})" if source else ''
    if note:
        suffix = f"{suffix}: {note}"
    return f"early {profile.get('early', 'average')}, mid {profile.get('mid', 'average')}, late {profile.get('late', 'average')}{suffix}"


def _format_knowledge_context(context: dict) -> str:
    lines = []
    played_at = context.get('match_played_at', '')
    if played_at:
        lines.append(f"- Match start time: {played_at}")
    patch = context.get('patch', {})
    patch_version = patch.get('current_patch', '') or 'unknown'
    lines.append(f"- Current Data Dragon patch: {patch_version}")
    patch_notes = patch.get('notes', [])
    if patch_notes:
        lines.append(f"- Patch-specific notes: {' | '.join(patch_notes)}")
    else:
        lines.append('- Patch-specific notes: none loaded; do not invent exact buff/nerf details.')

    champions = context.get('champions', {})
    lines.append(f"- Player champion phase profile: {_phase_summary(champions.get('player_profile', {}))}")
    lane_profile = champions.get('lane_profile', {})
    if lane_profile:
        lines.append(f"- Lane opponent phase profile: {_phase_summary(lane_profile)}")

    items = context.get('items', {})
    item_names = [item.get('name', f"Item {item.get('id', '?')}") for item in items.get('items', [])]
    if item_names:
        lines.append(f"- Final build items: {', '.join(item_names)}")
    item_tags = items.get('tags', {})
    if item_tags:
        tag_summary = ', '.join(f"{tag}:{count}" for tag, count in sorted(item_tags.items()))
        lines.append(f"- Item tag mix: {tag_summary}")

    team_comp = context.get('team_comp', {})
    ally_notes = (team_comp.get('ally') or {}).get('notes', [])
    enemy_notes = (team_comp.get('enemy') or {}).get('notes', [])
    if ally_notes:
        lines.append(f"- Ally comp profile: {' | '.join(ally_notes)}")
    if enemy_notes:
        lines.append(f"- Enemy comp profile: {' | '.join(enemy_notes)}")
    synergy_notes = team_comp.get('synergy_notes', [])
    if synergy_notes:
        lines.append(f"- Ally synergy patterns: {' | '.join(synergy_notes)}")

    rank = context.get('rank', {})
    if rank.get('available'):
        lines.append(f"- Player rank ({rank.get('queue', '')}): {rank.get('player_rank', 'Unknown')}")
        lines.append(f"- Ranked sample size in this lobby: {rank.get('sample_size', 0)}")
        tier_distribution = rank.get('tier_distribution', {})
        if tier_distribution:
            dist_text = ', '.join(f"{tier}:{count}" for tier, count in sorted(tier_distribution.items()))
            lines.append(f"- Lobby tier distribution: {dist_text}")
        for line in rank.get('benchmarks', []):
            lines.append(f"- {line}")
    else:
        lines.append(f"- Rank context: {rank.get('message', 'Unavailable')}")

    relative = context.get('relative_performance', {})
    for line in relative.get('lines', []):
        lines.append(f"- {line}")
    lane_line = relative.get('lane_matchup_line', '')
    if lane_line:
        lines.append(f"- {lane_line}")
    return '\n'.join(lines)


def _build_prompt(analysis: dict) -> tuple[str, str]:
    """Build the system and user prompts for LLM analysis."""
    result_str = 'Victory' if analysis['win'] else 'Defeat'
    system = (
        'You are a concise, expert League of Legends coach. '
        'Use provided match data and knowledge context to produce specific, evidence-based advice. '
        'If a knowledge field is unavailable, say so briefly instead of guessing.'
    )

    position = analysis.get('player_position', '')
    position_line = f"- Position: {_format_position(position)}\n" if position else ''
    opponent_section = ''
    lane_opp = analysis.get('lane_opponent')
    if lane_opp:
        opp_kda = f"{lane_opp.get('kills', 0)}/{lane_opp.get('deaths', 0)}/{lane_opp.get('assists', 0)}"
        opponent_section = (
            "\nLane Opponent:\n"
            f"- Champion: {lane_opp.get('champion', '?')}\n"
            f"- KDA: {opp_kda}\n"
            f"- Gold: {lane_opp.get('gold_earned', '?')}\n"
            f"- Damage: {lane_opp.get('total_damage', '?')}\n"
            f"- CS: {lane_opp.get('cs', '?')}\n"
            f"- Vision Score: {lane_opp.get('vision_score', '?')}\n"
        )

    team_section = ''
    participants = analysis.get('participants')
    if participants:
        player_team = None
        for p in participants:
            if p.get('is_player'):
                player_team = p.get('team_id')
                break
        if player_team is not None:
            allies = [p for p in participants if p.get('team_id') == player_team and not p.get('is_player')]
            enemies = [p for p in participants if p.get('team_id') != player_team]
            if allies:
                ally_str = ", ".join(
                    f"{p.get('champion', '?')}({_format_position(p.get('position', ''))})" if p.get('position') else p.get('champion', '?')
                    for p in allies
                )
                team_section += f"\nAlly Team: {ally_str}\n"
            if enemies:
                enemy_str = ", ".join(
                    f"{p.get('champion', '?')}({_format_position(p.get('position', ''))})" if p.get('position') else p.get('champion', '?')
                    for p in enemies
                )
                team_section += f"Enemy Team: {enemy_str}\n"

    knowledge_context = {}
    try:
        knowledge_context = _build_knowledge_context(analysis)
    except Exception:
        logger.exception('Knowledge context build failed; continuing with base metrics prompt.')
    knowledge_section = _format_knowledge_context(knowledge_context) if knowledge_context else '- Knowledge context unavailable.'

    matchup_instruction = ''
    if lane_opp:
        matchup_instruction = '2. Lane matchup performance and matchup dynamics across game phases\n'
    response_token_target = max(0, int(current_app.config.get('LLM_RESPONSE_TOKEN_TARGET', 0) or 0))
    if response_token_target > 0:
        approx_words = max(60, int(response_token_target * 0.75))
        length_instruction = (
            f"Target length: about {response_token_target} tokens (~{approx_words} words). "
            "Treat this as a soft target and still complete every requested section."
        )
    else:
        length_instruction = "Keep the response concise while fully addressing each requested section."

    user = (
        "Analyze this League of Legends match and provide focused coaching advice.\n\n"
        "Match Data:\n"
        f"- Champion: {analysis['champion']}\n"
        f"{position_line}"
        f"- Result: {result_str}\n"
        f"- Queue: {analysis.get('queue_type', 'Unknown')}\n"
        f"- KDA: {analysis['kills']}/{analysis['deaths']}/{analysis['assists']} (Ratio: {analysis['kda']})\n"
        f"- Gold: {analysis['gold_earned']} total ({analysis['gold_per_min']}/min)\n"
        f"- Damage: {analysis['total_damage']} total ({analysis['damage_per_min']}/min)\n"
        f"- Vision Score: {analysis['vision_score']}\n"
        f"- CS: {analysis['cs_total']}\n"
        f"- Game Duration: {analysis['game_duration']} minutes\n"
        f"{opponent_section}"
        f"{team_section}\n"
        "Knowledge Context:\n"
        f"{knowledge_section}\n\n"
        "Provide a concise analysis (3-5 short paragraphs) covering:\n"
        "1. Overall performance in this match relative to role/champion expectations\n"
        f"{matchup_instruction}"
        f"{'3' if lane_opp else '2'}. How itemization, rank context, and team compositions shaped this game\n"
        f"{'4' if lane_opp else '3'}. Key strengths shown in this match\n"
        f"{'5' if lane_opp else '4'}. Specific, actionable improvements for next games\n"
        f"{'6' if lane_opp else '5'}. One concrete practice focus for the next game\n\n"
        "Keep it direct and specific to this data. Avoid generic filler.\n"
        "Output plain text only. Do not use Markdown syntax, code fences, or list markers.\n"
        f"{length_instruction}"
    )
    return system, user


def get_llm_analysis(analysis: dict) -> str | None:
    """Generate deep AI analysis for a match using the LLM API."""
    result, error = get_llm_analysis_detailed(analysis)
    if error:
        logger.error('LLM analysis failed: %s', error)
    return result


def get_llm_analysis_detailed(analysis: dict) -> tuple[str | None, str | None]:
    """Generate LLM analysis and return (result, error_message)."""
    api_key = current_app.config.get('LLM_API_KEY', '')
    api_url = current_app.config.get('LLM_API_URL', '')
    model = current_app.config.get('LLM_MODEL', 'deepseek-chat')
    timeout_seconds = max(5, int(current_app.config.get('LLM_TIMEOUT_SECONDS', 30) or 30))
    retries = max(0, int(current_app.config.get('LLM_RETRIES', 1) or 1))
    retry_backoff = max(0.0, float(current_app.config.get('LLM_RETRY_BACKOFF_SECONDS', 1.5) or 1.5))
    max_tokens = max(256, int(current_app.config.get('LLM_MAX_TOKENS', 2048) or 2048))
    if not api_key:
        return None, 'LLM_API_KEY is not set.'
    if not api_url:
        return None, 'LLM_API_URL is not set.'
    model, model_error = _resolve_provider_model(api_url, model)
    if model_error:
        return None, model_error

    system_prompt, user_prompt = _build_prompt(analysis)
    body = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'max_tokens': max_tokens,
        'temperature': 0.7,
    }
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    last_error = ''
    attempts = retries + 1
    for attempt in range(attempts):
        try:
            resp = requests.post(
                api_url,
                json=body,
                headers=headers,
                timeout=timeout_seconds,
            )
            if resp.status_code == 401:
                return None, f"Authentication failed (401). Check your LLM_API_KEY. Response: {resp.text[:200]}"
            if resp.status_code == 404:
                return None, f"Endpoint not found (404). Check your LLM_API_URL: {api_url}"
            if resp.status_code >= 500:
                last_error = f"LLM API returned status {resp.status_code}: {resp.text[:300]}"
                if attempt < retries:
                    if retry_backoff > 0:
                        time.sleep(retry_backoff * (2 ** attempt))
                    continue
                return None, last_error
            if resp.status_code != 200:
                return None, f"LLM API returned status {resp.status_code}: {resp.text[:300]}"

            raw_body = resp.text
            if not raw_body or not raw_body.strip():
                return None, f"LLM API returned empty response body. URL: {api_url} | Model: {model}"
            try:
                data = resp.json()
            except ValueError:
                return None, f"LLM API returned non-JSON response. URL: {api_url} | Body: {raw_body[:300]}"
            message = data.get('choices', [{}])[0].get('message', {})
            content = message.get('content') or message.get('reasoning_content') or ''
            if not content:
                return None, f"LLM API response missing choices/content. URL: {api_url} | Body: {raw_body[:300]}"
            return _soft_text_clean(content), None
        except requests.Timeout:
            last_error = (
                f"Request timed out after {timeout_seconds}s (attempt {attempt + 1}/{attempts}). "
                f"URL: {api_url} | Model: {model}"
            )
            if attempt < retries:
                if retry_backoff > 0:
                    time.sleep(retry_backoff * (2 ** attempt))
                continue
            return None, (
                f"{last_error} Consider lowering LLM_MAX_TOKENS/LLM_RESPONSE_TOKEN_TARGET "
                "or verifying provider latency/endpoint."
            )
        except requests.RequestException as e:
            last_error = f"Request failed. URL: {api_url} | Error: {e}"
            if attempt < retries:
                if retry_backoff > 0:
                    time.sleep(retry_backoff * (2 ** attempt))
                continue
            return None, last_error

    return None, last_error or 'Unknown LLM request failure.'
