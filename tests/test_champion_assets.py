"""Tests for champion icon Data Dragon asset resolution."""

import requests

from app.analysis import champion_assets as assets


def _reset_cache_state():
    assets._VERSION_CACHE['value'] = ''
    assets._VERSION_CACHE['expires_at'] = 0.0
    assets._MAP_CACHE.clear()


class TestVersionCaching:
    def test_failed_version_lookup_is_cached_for_backoff(self, monkeypatch):
        _reset_cache_state()
        calls = {'n': 0}

        def fail_get(*args, **kwargs):
            calls['n'] += 1
            raise requests.Timeout("ddragon timeout")

        monkeypatch.setattr(assets.requests, 'get', fail_get)

        v1 = assets._fetch_latest_version()
        v2 = assets._fetch_latest_version()

        assert v1 == ''
        assert v2 == ''
        assert calls['n'] == 1

    def test_failure_backoff_expiry_retries(self, monkeypatch):
        _reset_cache_state()
        calls = {'n': 0}

        def fail_get(*args, **kwargs):
            calls['n'] += 1
            raise requests.Timeout("ddragon timeout")

        monkeypatch.setattr(assets.requests, 'get', fail_get)

        assets._fetch_latest_version()
        assets._VERSION_CACHE['expires_at'] = 0.0
        assets._fetch_latest_version()

        assert calls['n'] == 2

    def test_successful_version_lookup_uses_cache(self, monkeypatch):
        _reset_cache_state()
        calls = {'n': 0}

        class Resp:
            status_code = 200

            @staticmethod
            def json():
                return ['26.3.1', '26.3.0']

        def ok_get(*args, **kwargs):
            calls['n'] += 1
            return Resp()

        monkeypatch.setattr(assets.requests, 'get', ok_get)

        v1 = assets._fetch_latest_version()
        v2 = assets._fetch_latest_version()

        assert v1 == '26.3.1'
        assert v2 == '26.3.1'
        assert calls['n'] == 1
