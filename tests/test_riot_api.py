"""Tests for Riot API helper functions."""

from unittest.mock import patch, MagicMock
from app.analysis.riot_api import resolve_puuid, get_routing_value, get_recent_matches


class TestGetRoutingValue:
    def test_na_region(self):
        assert get_routing_value("na1") == "americas"

    def test_euw_region(self):
        assert get_routing_value("euw1") == "europe"

    def test_kr_region(self):
        assert get_routing_value("kr") == "asia"

    def test_unknown_region_defaults_to_americas(self):
        assert get_routing_value("unknown") == "americas"


class TestResolvePuuid:
    @patch("app.analysis.riot_api.http_requests.get")
    def test_success(self, mock_get, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"puuid": "abc-123-puuid"}
        mock_get.return_value = mock_resp

        with app.app_context():
            puuid, error = resolve_puuid("TestPlayer", "NA1", "na1")

        assert puuid == "abc-123-puuid"
        assert error is None
        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert "americas.api.riotgames.com" in call_url
        assert "TestPlayer" in call_url
        assert "NA1" in call_url

    @patch("app.analysis.riot_api.http_requests.get")
    def test_summoner_not_found(self, mock_get, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        with app.app_context():
            puuid, error = resolve_puuid("FakePlayer", "FAKE", "na1")

        assert puuid is None
        assert ("not found" in error.lower()) or ("未找到" in error)
        assert "FakePlayer#FAKE" in error

    @patch("app.analysis.riot_api.http_requests.get")
    def test_forbidden_api_key(self, mock_get, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        with app.app_context():
            puuid, error = resolve_puuid("Player", "TAG", "euw1")

        assert puuid is None
        assert ("invalid or expired" in error.lower()) or ("无效或已过期" in error)

    @patch("app.analysis.riot_api.http_requests.get")
    def test_rate_limited(self, mock_get, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp

        with app.app_context():
            puuid, error = resolve_puuid("Player", "TAG", "kr")

        assert puuid is None
        assert ("too many requests" in error.lower()) or ("请求过于频繁" in error)

    @patch("app.analysis.riot_api.http_requests.get")
    def test_server_error(self, mock_get, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        with app.app_context():
            puuid, error = resolve_puuid("Player", "TAG", "na1")

        assert puuid is None
        assert "500" in error

    @patch("app.analysis.riot_api.http_requests.get")
    def test_network_exception(self, mock_get, app):
        mock_get.side_effect = ConnectionError("Network unreachable")

        with app.app_context():
            puuid, error = resolve_puuid("Player", "TAG", "na1")

        assert puuid is None
        assert ("unexpected error" in error.lower()) or ("未知错误" in error)

    def test_no_api_key(self, app):
        with app.app_context():
            app.config["RIOT_API_KEY"] = ""
            puuid, error = resolve_puuid("Player", "TAG", "na1")
            app.config["RIOT_API_KEY"] = "RGAPI-test-key"

        assert puuid is None
        assert ("not configured" in error.lower()) or ("未配置" in error)


class TestGetRecentMatches:
    @patch("app.analysis.riot_api.get_watcher")
    def test_success(self, mock_get_watcher, app):
        mock_watcher = MagicMock()
        mock_watcher.match.matchlist_by_puuid.return_value = ["NA1_111", "NA1_222"]
        mock_get_watcher.return_value = mock_watcher

        with app.app_context():
            matches = get_recent_matches("na1", "test-puuid", count=2)

        assert matches == ["NA1_111", "NA1_222"]

    @patch("app.analysis.riot_api.get_watcher")
    def test_api_error_returns_empty(self, mock_get_watcher, app):
        from riotwatcher import ApiError

        mock_watcher = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_watcher.match.matchlist_by_puuid.side_effect = ApiError(
            "test", mock_response
        )
        mock_get_watcher.return_value = mock_watcher

        with app.app_context():
            matches = get_recent_matches("na1", "test-puuid")

        assert matches == []
