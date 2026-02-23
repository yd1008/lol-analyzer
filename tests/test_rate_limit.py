"""Tests for shared outbound rate-limit helper behavior."""

from unittest.mock import patch

from app.analysis import rate_limit


def test_in_memory_bucket_reports_wait_after_limit():
    rate_limit._LOCAL_BUCKETS.clear()
    wait_first = rate_limit._acquire_local("unit-test", limit=1, window_seconds=60)
    wait_second = rate_limit._acquire_local("unit-test", limit=1, window_seconds=60)
    assert wait_first == 0.0
    assert wait_second > 0.0


def test_redis_unavailable_falls_back_to_local(app):
    rate_limit._REDIS_CLIENT = None
    rate_limit._REDIS_URL = ""
    rate_limit._REDIS_DISABLED = False
    app.config["RATE_LIMIT_REDIS_URL"] = "redis://127.0.0.1:6399/0"

    with app.app_context():
        with patch("app.analysis.rate_limit.redis.Redis.from_url", side_effect=RuntimeError("boom")), patch(
            "app.analysis.rate_limit._acquire_local",
            return_value=0.0,
        ) as acquire_local:
            rate_limit.throttle("fallback-test", limit=1, window_seconds=1)

    assert acquire_local.called
