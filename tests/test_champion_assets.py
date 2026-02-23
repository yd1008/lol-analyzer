"""Tests for champion icon Data Dragon asset resolution."""

import requests

from app.analysis import champion_assets as assets


def _reset_cache_state():
    assets._VERSION_CACHE['value'] = ''
    assets._VERSION_CACHE['expires_at'] = 0.0
    assets._MAP_CACHE.clear()
    assets._ITEM_CACHE.clear()
    assets._RUNE_CACHE.clear()


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


class TestItemAndRuneIcons:
    def test_item_icon_url_uses_item_set(self, monkeypatch):
        monkeypatch.setattr(assets, '_fetch_latest_version', lambda: '26.3.1')
        monkeypatch.setattr(assets, '_get_item_set', lambda version: {1056, 3157})

        assert assets.item_icon_url(1056).endswith('/26.3.1/img/item/1056.png')
        assert assets.item_icon_url(999999) == ''
        assert assets.item_icon_url(0) == ''

    def test_item_set_cache_expiry_refetches_data(self, monkeypatch):
        _reset_cache_state()

        payloads = [
            {'1001': {}, '2003': {}},
            {'1001': {}, '2003': {}, '3157': {}},
        ]
        calls = {'n': 0}

        class Resp:
            status_code = 200

            def __init__(self, data):
                self._data = data

            def json(self):
                return {'data': self._data}

        def fake_get(*args, **kwargs):
            calls['n'] += 1
            idx = 0 if calls['n'] == 1 else 1
            return Resp(payloads[idx])

        monkeypatch.setattr(assets.requests, 'get', fake_get)

        initial = assets._get_item_set('26.3.1')
        cached = assets._get_item_set('26.3.1')

        assert initial == {1001, 2003}
        assert cached == {1001, 2003}
        assert calls['n'] == 1

        assets._ITEM_CACHE['26.3.1']['expires_at'] = 0.0
        refreshed = assets._get_item_set('26.3.1')

        assert calls['n'] == 2
        assert refreshed == {1001, 2003, 3157}

    def test_rune_map_cache_expiry_refetches_data(self, monkeypatch):
        _reset_cache_state()

        payloads = [
            [
                {
                    'id': 8200,
                    'icon': 'perk-images/Styles/7202_Sorcery.png',
                    'slots': [
                        {
                            'runes': [
                                {'id': 8229, 'icon': 'perk-images/Styles/Sorcery/ArcaneComet/ArcaneComet.png'},
                            ]
                        }
                    ],
                }
            ],
            [
                {
                    'id': 8200,
                    'icon': 'perk-images/Styles/7202_Sorcery.png',
                    'slots': [
                        {
                            'runes': [
                                {'id': 8229, 'icon': 'perk-images/Styles/Sorcery/ArcaneComet/ArcaneComet.png'},
                                {'id': 8230, 'icon': 'perk-images/Styles/Sorcery/PhaseRush/PhaseRush.png'},
                            ]
                        }
                    ],
                }
            ],
        ]
        calls = {'n': 0}

        class Resp:
            status_code = 200

            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

        def fake_get(*args, **kwargs):
            calls['n'] += 1
            idx = 0 if calls['n'] == 1 else 1
            return Resp(payloads[idx])

        monkeypatch.setattr(assets.requests, 'get', fake_get)

        initial = assets._get_rune_maps('26.3.1')
        cached = assets._get_rune_maps('26.3.1')

        assert calls['n'] == 1
        assert 8229 in initial['perks']
        assert 8230 not in cached['perks']

        assets._RUNE_CACHE['26.3.1']['expires_at'] = 0.0
        refreshed = assets._get_rune_maps('26.3.1')

        assert calls['n'] == 2
        assert 8230 in refreshed['perks']

    def test_rune_icons_from_mapped_paths(self, monkeypatch):
        monkeypatch.setattr(assets, '_fetch_latest_version', lambda: '26.3.1')
        monkeypatch.setattr(
            assets,
            '_get_rune_maps',
            lambda version: {
                'perks': {8229: 'perk-images/Styles/Sorcery/ArcaneComet/ArcaneComet.png'},
                'styles': {8200: 'perk-images/Styles/7202_Sorcery.png'},
            },
        )

        icons = assets.rune_icons(8229, 8200)
        assert icons['primary'].endswith('/cdn/img/perk-images/Styles/Sorcery/ArcaneComet/ArcaneComet.png')
        assert icons['secondary'].endswith('/cdn/img/perk-images/Styles/7202_Sorcery.png')
