"""Shared outbound rate limiting helpers (Redis-first, in-memory fallback)."""

from __future__ import annotations

import logging
import threading
import time

from flask import current_app, has_app_context

try:
    import redis
except ImportError:  # pragma: no cover - optional dependency in minimal environments
    redis = None

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_LOCAL_BUCKETS: dict[str, int] = {}
_REDIS_CLIENT = None
_REDIS_URL = ''
_REDIS_DISABLED = False


def _window_bucket(now: float, window_seconds: int) -> int:
    return int(now // max(1, window_seconds))


def _get_redis_client():
    global _REDIS_CLIENT, _REDIS_URL, _REDIS_DISABLED
    if _REDIS_DISABLED or redis is None:
        return None

    if not has_app_context():
        return None

    url = (current_app.config.get('RATE_LIMIT_REDIS_URL', '') or '').strip()
    if not url:
        return None

    if _REDIS_CLIENT is not None and _REDIS_URL == url:
        return _REDIS_CLIENT

    try:
        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
            health_check_interval=30,
        )
        client.ping()
        _REDIS_CLIENT = client
        _REDIS_URL = url
        return _REDIS_CLIENT
    except Exception:
        logger.exception("Failed to initialize Redis rate-limit backend. Falling back to in-memory buckets.")
        _REDIS_DISABLED = True
        _REDIS_CLIENT = None
        return None


def _acquire_local(key: str, limit: int, window_seconds: int) -> float:
    now = time.time()
    bucket = _window_bucket(now, window_seconds)
    full_key = f"{key}:{window_seconds}:{bucket}"
    with _LOCK:
        count = _LOCAL_BUCKETS.get(full_key, 0) + 1
        _LOCAL_BUCKETS[full_key] = count
        # Best-effort cleanup of stale buckets.
        stale_prefix = f"{key}:{window_seconds}:"
        stale_cutoff = bucket - 2
        stale_keys = [
            k for k in _LOCAL_BUCKETS
            if k.startswith(stale_prefix) and int(k.rsplit(':', 1)[-1]) < stale_cutoff
        ]
        for stale in stale_keys:
            _LOCAL_BUCKETS.pop(stale, None)
    if count <= limit:
        return 0.0
    return ((bucket + 1) * window_seconds) - now


def _acquire_redis(client, key: str, limit: int, window_seconds: int) -> float:
    now = time.time()
    bucket = _window_bucket(now, window_seconds)
    redis_key = f"rl:{key}:{window_seconds}:{bucket}"
    try:
        count = int(client.incr(redis_key))
        if count == 1:
            client.expire(redis_key, max(1, window_seconds + 1))
    except Exception:
        logger.exception("Redis rate-limit acquire failed for key=%s. Falling back to in-memory.", key)
        return _acquire_local(key, limit, window_seconds)

    if count <= limit:
        return 0.0
    return ((bucket + 1) * window_seconds) - now


def throttle(key: str, limit: int, window_seconds: int) -> None:
    """Block briefly until an outbound request key is within configured budget."""
    if limit <= 0:
        return

    while True:
        client = _get_redis_client()
        if client is not None:
            wait_seconds = _acquire_redis(client, key, limit, window_seconds)
        else:
            wait_seconds = _acquire_local(key, limit, window_seconds)

        if wait_seconds <= 0:
            return
        time.sleep(max(0.01, min(wait_seconds, 1.0)))


def throttle_riot_api(operation: str = 'default') -> None:
    if not has_app_context():
        return
    limit = int(current_app.config.get('RIOT_RATE_LIMIT_PER_MINUTE', 100) or 100)
    throttle(f"riot:{operation}", limit=limit, window_seconds=60)


def throttle_discord_api(operation: str = 'send_message') -> None:
    if not has_app_context():
        return
    count = int(current_app.config.get('DISCORD_RATE_LIMIT_COUNT', 10) or 10)
    window = int(current_app.config.get('DISCORD_RATE_LIMIT_WINDOW_SECONDS', 10) or 10)
    throttle(f"discord:{operation}", limit=count, window_seconds=window)
