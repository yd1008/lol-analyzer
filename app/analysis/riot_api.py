"""Riot API helper functions for multi-user usage."""

import logging
import requests as http_requests
from flask import current_app
from riotwatcher import LolWatcher, ApiError
from app.i18n import lt

logger = logging.getLogger(__name__)

REGION_TO_ROUTING = {
    'na1': 'americas',
    'br1': 'americas',
    'la1': 'americas',
    'la2': 'americas',
    'oc1': 'sea',
    'ph2': 'sea',
    'sg2': 'sea',
    'th2': 'sea',
    'tw2': 'sea',
    'vn2': 'sea',
    'euw1': 'europe',
    'eun1': 'europe',
    'tr1': 'europe',
    'ru': 'europe',
    'jp1': 'asia',
    'kr': 'asia',
}

REGION_DISPLAY = {
    'na1': 'NA', 'br1': 'BR', 'la1': 'LAN', 'la2': 'LAS',
    'oc1': 'OCE', 'ph2': 'PH', 'sg2': 'SG', 'th2': 'TH',
    'tw2': 'TW', 'vn2': 'VN', 'euw1': 'EUW', 'eun1': 'EUNE',
    'tr1': 'TR', 'ru': 'RU', 'jp1': 'JP', 'kr': 'KR',
}

VALID_REGIONS = list(REGION_TO_ROUTING.keys())


def get_watcher() -> LolWatcher:
    """Create a LolWatcher instance using the configured API key."""
    api_key = current_app.config['RIOT_API_KEY']
    if not api_key:
        raise ValueError("RIOT_API_KEY not configured")
    return LolWatcher(api_key)


def get_routing_value(region: str) -> str:
    """Get the routing value for a given platform region."""
    return REGION_TO_ROUTING.get(region, 'americas')


def resolve_puuid(summoner_name: str, tagline: str, region: str) -> tuple[str | None, str | None]:
    """Resolve a summoner name + tagline to a PUUID.

    Returns (puuid, error_message). On success error_message is None.
    On failure puuid is None and error_message describes the problem.
    """
    if not current_app.config.get('RIOT_API_KEY'):
        return None, lt(
            "Riot API key is not configured. Please contact the site administrator.",
            "Riot API 密钥未配置，请联系站点管理员。",
        )

    try:
        api_key = current_app.config['RIOT_API_KEY']
        routing = get_routing_value(region)
        url = f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{summoner_name}/{tagline}"
        resp = http_requests.get(url, headers={"X-Riot-Token": api_key}, timeout=10)

        if resp.status_code == 200:
            return resp.json()['puuid'], None

        display = REGION_DISPLAY.get(region, region.upper())
        if resp.status_code == 404:
            return None, (
                lt(
                    f'Summoner "{summoner_name}#{tagline}" was not found on {display}. '
                    f'Make sure your Riot ID is spelled correctly (case-insensitive) '
                    f'and that you selected the right region. '
                    f'Your Riot ID is shown at the top of your League client.',
                    f'在 {display} 未找到召唤师“{summoner_name}#{tagline}”。'
                    f'请确认 Riot ID 拼写正确（不区分大小写）并选择了正确服务器。'
                    f'你的 Riot ID 可在英雄联盟客户端顶部查看。',
                )
            )
        if resp.status_code == 403:
            return None, lt(
                "Riot API key is invalid or expired. Please contact the site administrator.",
                "Riot API 密钥无效或已过期，请联系站点管理员。",
            )
        if resp.status_code == 429:
            return None, lt(
                "Too many requests to Riot API. Please wait a minute and try again.",
                "Riot API 请求过于频繁，请稍后再试。",
            )
        logger.error("Riot API error resolving PUUID for %s#%s: status %d", summoner_name, tagline, resp.status_code)
        return None, lt(
            f"Riot API returned an error (code {resp.status_code}). Please try again later.",
            f"Riot API 返回错误（代码 {resp.status_code}），请稍后重试。",
        )
    except ValueError as e:
        return None, str(e)
    except Exception as e:
        logger.error("Error resolving PUUID for %s#%s: %s", summoner_name, tagline, e)
        return None, lt(
            "An unexpected error occurred. Please try again later.",
            "发生未知错误，请稍后重试。",
        )


def get_recent_matches(region: str, puuid: str, count: int = 10) -> list[str]:
    """Get recent match IDs for a player."""
    try:
        watcher = get_watcher()
        routing = get_routing_value(region)
        return watcher.match.matchlist_by_puuid(routing, puuid, count=count)
    except ApiError as e:
        logger.error("Riot API error fetching matches for %s: %s", puuid, e)
        return []
    except Exception as e:
        logger.error("Error fetching matches for %s: %s", puuid, e)
        return []


def get_matches_since(region: str, puuid: str, start_timestamp_ms: int) -> list[str]:
    """Get match IDs since a given timestamp (milliseconds)."""
    try:
        watcher = get_watcher()
        routing = get_routing_value(region)
        return watcher.match.matchlist_by_puuid(
            routing, puuid,
            start_time=start_timestamp_ms // 1000,
            count=100
        )
    except ApiError as e:
        logger.error("Riot API error fetching matches since timestamp: %s", e)
        return []
    except Exception as e:
        logger.error("Error fetching matches since timestamp: %s", e)
        return []
