"""Tests for auth and basic routes."""

import json
from unittest.mock import patch

from app.models import User, MatchAnalysis


class TestLandingPage:
    def test_landing_page_loads(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_riot_txt(self, client, app):
        resp = client.get("/riot.txt")
        assert resp.status_code == 200
        assert resp.data.decode() == app.config["RIOT_VERIFICATION_UUID"]

    def test_terms_page(self, client):
        resp = client.get("/terms")
        assert resp.status_code == 200

    def test_privacy_page(self, client):
        resp = client.get("/privacy")
        assert resp.status_code == 200


class TestRegister:
    def test_register_page_loads(self, client):
        resp = client.get("/auth/register")
        assert resp.status_code == 200

    def test_register_success(self, client, db):
        resp = client.post("/auth/register", data={
            "email": "newuser@example.com",
            "password": "securepass123",
            "confirm_password": "securepass123",
        }, follow_redirects=True)
        assert resp.status_code == 200

        user = User.query.filter_by(email="newuser@example.com").first()
        assert user is not None
        assert user.settings is not None

    def test_register_duplicate_email(self, client, user):
        resp = client.post("/auth/register", data={
            "email": "test@example.com",
            "password": "anotherpass123",
            "confirm_password": "anotherpass123",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert User.query.filter_by(email="test@example.com").count() == 1

    def test_register_password_mismatch(self, client, db):
        resp = client.post("/auth/register", data={
            "email": "mismatch@example.com",
            "password": "password123",
            "confirm_password": "different123",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert User.query.filter_by(email="mismatch@example.com").first() is None

    def test_register_empty_password_fields_show_required_messages(self, client, db):
        resp = client.post("/auth/register", data={
            "email": "empty-password@example.com",
            "password": "",
            "confirm_password": "",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Password is required." in resp.data
        assert b"Please confirm your password." in resp.data


class TestLogin:
    def test_login_page_loads(self, client):
        resp = client.get("/auth/login")
        assert resp.status_code == 200

    def test_login_success(self, client, user):
        resp = client.post("/auth/login", data={
            "email": "test@example.com",
            "password": "testpass123",
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_wrong_password(self, client, user):
        resp = client.post("/auth/login", data={
            "email": "test@example.com",
            "password": "wrongpassword",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Invalid" in resp.data

    def test_login_nonexistent_user(self, client, db):
        resp = client.post("/auth/login", data={
            "email": "nobody@example.com",
            "password": "testpass123",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Invalid" in resp.data


class TestLogout:
    def test_logout(self, auth_client):
        resp = auth_client.get("/auth/logout", follow_redirects=True)
        assert resp.status_code == 200


class TestDashboardAccess:
    def test_dashboard_requires_login(self, client):
        resp = client.get("/dashboard/")
        assert resp.status_code in (302, 401)

    def test_dashboard_accessible_when_logged_in(self, auth_client):
        resp = auth_client.get("/dashboard/")
        assert resp.status_code == 200

    def test_dashboard_shows_ai_coach_focus_plan(self, auth_client):
        resp = auth_client.get("/dashboard/")
        assert resp.status_code == 200
        assert b"AI Coach Focus Plan" in resp.data
        assert b"Actionable next-game goal" in resp.data

    def test_settings_requires_login(self, client):
        resp = client.get("/dashboard/settings")
        assert resp.status_code in (302, 401)


class TestAdminAccess:
    def test_admin_requires_login(self, client):
        resp = client.get("/admin/")
        assert resp.status_code in (302, 401)

    def test_admin_requires_admin_email(self, auth_client):
        resp = auth_client.get("/admin/", follow_redirects=True)
        assert resp.status_code == 200
        # Non-admin user should be redirected with "Access denied"

    def test_admin_accessible_for_admin(self, client, db, app):
        admin = User(email="admin@test.com")
        admin.set_password("adminpass")
        db.session.add(admin)
        db.session.commit()

        client.post("/auth/login", data={
            "email": "admin@test.com",
            "password": "adminpass",
        })
        resp = client.get("/admin/")
        assert resp.status_code == 200


class TestAiAnalysisRoute:
    def _parse_ndjson(self, response):
        return [json.loads(line) for line in response.data.decode().splitlines() if line.strip()]

    def test_ai_analysis_non_object_payload_does_not_crash(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_non_object_payload",
            champion="Ahri",
            win=True,
            kills=5,
            deaths=2,
            assists=7,
            kda=6.0,
            gold_earned=12000,
            gold_per_min=400.0,
            total_damage=20000,
            damage_per_min=700.0,
            vision_score=25,
            cs_total=180,
            game_duration=30.0,
            recommendations=[],
            llm_analysis="cached analysis",
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        resp = auth_client.post(
            f"/dashboard/api/matches/{match.id}/ai-analysis",
            json=[1],
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["cached"] is True
        assert payload["analysis"] == "cached analysis"

    def test_ai_analysis_force_regenerates(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_test",
            champion="Ahri",
            win=True,
            kills=5,
            deaths=2,
            assists=7,
            kda=6.0,
            gold_earned=12000,
            gold_per_min=400.0,
            total_damage=20000,
            damage_per_min=700.0,
            vision_score=25,
            cs_total=180,
            game_duration=30.0,
            recommendations=[],
            llm_analysis="cached analysis",
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        resp_cached = auth_client.post(f"/dashboard/api/matches/{match.id}/ai-analysis", json={})
        assert resp_cached.status_code == 200
        cached_json = resp_cached.get_json()
        assert cached_json["cached"] is True
        assert cached_json["analysis"] == "cached analysis"

        with patch("app.dashboard.routes.get_llm_analysis_detailed", return_value=("fresh analysis", None)) as mock_llm:
            resp_force = auth_client.post(
                f"/dashboard/api/matches/{match.id}/ai-analysis",
                json={"force": True, "coach_mode": "aggressive"},
            )

        assert resp_force.status_code == 200
        force_json = resp_force.get_json()
        assert force_json["cached"] is False
        assert force_json["regenerated"] is True
        assert force_json["analysis"] == "fresh analysis"

        llm_payload = mock_llm.call_args[0][0]
        assert llm_payload["coach_mode"] == "aggressive"

        reloaded = db.session.get(MatchAnalysis, match.id)
        assert reloaded.llm_analysis == "fresh analysis"

    def test_ai_analysis_invalid_coach_mode_falls_back_to_balanced(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_mode_fallback",
            champion="Ahri",
            win=True,
            kills=5,
            deaths=2,
            assists=7,
            kda=6.0,
            gold_earned=12000,
            gold_per_min=400.0,
            total_damage=20000,
            damage_per_min=700.0,
            vision_score=25,
            cs_total=180,
            game_duration=30.0,
            recommendations=[],
            llm_analysis=None,
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        with patch("app.dashboard.routes.get_llm_analysis_detailed", return_value=("fresh analysis", None)) as mock_llm:
            resp_force = auth_client.post(
                f"/dashboard/api/matches/{match.id}/ai-analysis",
                json={"force": True, "coach_mode": "ultra-tilt-mode"},
            )

        assert resp_force.status_code == 200
        llm_payload = mock_llm.call_args[0][0]
        assert llm_payload["coach_mode"] == "balanced"

    def test_ai_analysis_timeout_returns_504_without_cached_analysis(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_timeout_no_cache",
            champion="Ahri",
            win=True,
            kills=5,
            deaths=2,
            assists=7,
            kda=6.0,
            gold_earned=12000,
            gold_per_min=400.0,
            total_damage=20000,
            damage_per_min=700.0,
            vision_score=25,
            cs_total=180,
            game_duration=30.0,
            recommendations=[],
            llm_analysis=None,
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        with patch(
            "app.dashboard.routes.get_llm_analysis_detailed",
            return_value=(None, "Request timed out after 30s. URL: https://example.test/v1/chat/completions"),
        ):
            resp = auth_client.post(f"/dashboard/api/matches/{match.id}/ai-analysis", json={"force": True})

        assert resp.status_code == 504
        payload = resp.get_json()
        assert "timed out" in payload["error"].lower()

    def test_ai_analysis_timeout_returns_stale_cached_analysis(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_timeout_with_cache",
            champion="Ahri",
            win=True,
            kills=5,
            deaths=2,
            assists=7,
            kda=6.0,
            gold_earned=12000,
            gold_per_min=400.0,
            total_damage=20000,
            damage_per_min=700.0,
            vision_score=25,
            cs_total=180,
            game_duration=30.0,
            recommendations=[],
            llm_analysis="existing cached analysis",
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        with patch(
            "app.dashboard.routes.get_llm_analysis_detailed",
            return_value=(None, "Request timed out after 30s. URL: https://example.test/v1/chat/completions"),
        ):
            resp = auth_client.post(f"/dashboard/api/matches/{match.id}/ai-analysis", json={"force": True})

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["cached"] is True
        assert payload["stale"] is True
        assert payload["analysis"] == "existing cached analysis"
        assert "timed out" in payload["error"].lower()

    def test_ai_analysis_configuration_error_returns_400_without_cached_analysis(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_bad_model",
            champion="Ahri",
            win=True,
            kills=5,
            deaths=2,
            assists=7,
            kda=6.0,
            gold_earned=12000,
            gold_per_min=400.0,
            total_damage=20000,
            damage_per_min=700.0,
            vision_score=25,
            cs_total=180,
            game_duration=30.0,
            recommendations=[],
            llm_analysis=None,
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        with patch(
            "app.dashboard.routes.get_llm_analysis_detailed",
            return_value=(None, "Model 'gpt-5.2' on OpenCode Zen is not compatible with /chat/completions."),
        ):
            resp = auth_client.post(f"/dashboard/api/matches/{match.id}/ai-analysis", json={"force": True})

        assert resp.status_code == 400
        payload = resp.get_json()
        assert "not compatible with /chat/completions" in payload["error"]

    def test_ai_analysis_stream_returns_cached_done_when_not_forced(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_stream_cached",
            champion="Ahri",
            win=True,
            kills=5,
            deaths=2,
            assists=7,
            kda=6.0,
            gold_earned=12000,
            gold_per_min=400.0,
            total_damage=20000,
            damage_per_min=700.0,
            vision_score=25,
            cs_total=180,
            game_duration=30.0,
            recommendations=[],
            llm_analysis="already cached",
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        resp = auth_client.post(f"/dashboard/api/matches/{match.id}/ai-analysis/stream", json={})
        assert resp.status_code == 200
        events = self._parse_ndjson(resp)
        assert events[0]["type"] == "meta"
        assert events[0]["cached"] is True
        assert events[1]["type"] == "done"
        assert events[1]["analysis"] == "already cached"
        assert events[1]["cached"] is True

    def test_ai_analysis_stream_emits_chunk_then_done_and_persists(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_stream_success",
            champion="Ahri",
            win=True,
            kills=5,
            deaths=2,
            assists=7,
            kda=6.0,
            gold_earned=12000,
            gold_per_min=400.0,
            total_damage=20000,
            damage_per_min=700.0,
            vision_score=25,
            cs_total=180,
            game_duration=30.0,
            recommendations=[],
            llm_analysis=None,
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        stream_events = [
            {"type": "chunk", "delta": "First part. "},
            {"type": "done", "analysis": "First part. Final part."},
        ]
        with patch("app.dashboard.routes.iter_llm_analysis_stream", return_value=stream_events):
            resp = auth_client.post(f"/dashboard/api/matches/{match.id}/ai-analysis/stream", json={"force": True})
            events = self._parse_ndjson(resp)

        assert resp.status_code == 200
        assert events[0]["type"] == "meta"
        assert events[1]["type"] == "chunk"
        assert events[2]["type"] == "done"
        assert events[2]["analysis"] == "First part. Final part."
        reloaded = db.session.get(MatchAnalysis, match.id)
        assert reloaded.llm_analysis == "First part. Final part."

    def test_ai_analysis_stream_emits_stale_when_stream_fails_with_cache(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_stream_stale",
            champion="Ahri",
            win=True,
            kills=5,
            deaths=2,
            assists=7,
            kda=6.0,
            gold_earned=12000,
            gold_per_min=400.0,
            total_damage=20000,
            damage_per_min=700.0,
            vision_score=25,
            cs_total=180,
            game_duration=30.0,
            recommendations=[],
            llm_analysis="cached fallback",
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        with patch(
            "app.dashboard.routes.iter_llm_analysis_stream",
            return_value=[{"type": "error", "error": "Request timed out after 30s"}],
        ):
            resp = auth_client.post(f"/dashboard/api/matches/{match.id}/ai-analysis/stream", json={"force": True})
            events = self._parse_ndjson(resp)

        assert resp.status_code == 200
        assert events[-1]["type"] == "stale"
        assert events[-1]["analysis"] == "cached fallback"
        assert events[-1]["cached"] is True
        assert events[-1]["stale"] is True

    def test_ai_analysis_stream_emits_error_when_stream_fails_without_cache(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_stream_error",
            champion="Ahri",
            win=True,
            kills=5,
            deaths=2,
            assists=7,
            kda=6.0,
            gold_earned=12000,
            gold_per_min=400.0,
            total_damage=20000,
            damage_per_min=700.0,
            vision_score=25,
            cs_total=180,
            game_duration=30.0,
            recommendations=[],
            llm_analysis=None,
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        with patch(
            "app.dashboard.routes.iter_llm_analysis_stream",
            return_value=[{"type": "error", "error": "not compatible with /chat/completions"}],
        ):
            resp = auth_client.post(f"/dashboard/api/matches/{match.id}/ai-analysis/stream", json={"force": True})
            events = self._parse_ndjson(resp)

        assert resp.status_code == 200
        assert events[-1]["type"] == "error"
        assert events[-1]["status"] == 400

    def test_ai_analysis_reads_language_specific_cache(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_lang_cache",
            champion="Ahri",
            win=True,
            kills=5,
            deaths=2,
            assists=7,
            kda=6.0,
            gold_earned=12000,
            gold_per_min=400.0,
            total_damage=20000,
            damage_per_min=700.0,
            vision_score=25,
            cs_total=180,
            game_duration=30.0,
            recommendations=[],
            llm_analysis="legacy english cache",
            llm_analysis_en="english cache",
            llm_analysis_zh="中文缓存",
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        resp_zh = auth_client.post(
            f"/dashboard/api/matches/{match.id}/ai-analysis",
            json={"language": "zh-CN"},
        )
        assert resp_zh.status_code == 200
        payload_zh = resp_zh.get_json()
        assert payload_zh["analysis"] == "中文缓存"
        assert payload_zh["cached"] is True
        assert payload_zh["language"] == "zh-CN"

        resp_en = auth_client.post(
            f"/dashboard/api/matches/{match.id}/ai-analysis",
            json={"language": "en"},
        )
        assert resp_en.status_code == 200
        payload_en = resp_en.get_json()
        assert payload_en["analysis"] == "english cache"
        assert payload_en["cached"] is True
        assert payload_en["language"] == "en"

    def test_ai_analysis_force_writes_requested_language_column(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_lang_write",
            champion="Ahri",
            win=True,
            kills=5,
            deaths=2,
            assists=7,
            kda=6.0,
            gold_earned=12000,
            gold_per_min=400.0,
            total_damage=20000,
            damage_per_min=700.0,
            vision_score=25,
            cs_total=180,
            game_duration=30.0,
            recommendations=[],
            llm_analysis="legacy english cache",
            llm_analysis_en="legacy english cache",
            llm_analysis_zh=None,
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        with patch("app.dashboard.routes.get_llm_analysis_detailed", return_value=("新的中文分析", None)):
            resp = auth_client.post(
                f"/dashboard/api/matches/{match.id}/ai-analysis",
                json={"force": True, "language": "zh-CN"},
            )

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["analysis"] == "新的中文分析"
        assert payload["language"] == "zh-CN"
        reloaded = db.session.get(MatchAnalysis, match.id)
        assert reloaded.llm_analysis_zh == "新的中文分析"
        assert reloaded.llm_analysis_en == "legacy english cache"


class TestMatchDetailRoute:
    @patch("app.dashboard.routes.champion_icon_url", return_value="")
    @patch("app.dashboard.routes.item_icon_url", return_value="")
    @patch("app.dashboard.routes.rune_icons", return_value={"primary": "", "secondary": ""})
    def test_match_detail_handles_null_gold_total(
        self,
        _mock_runes,
        _mock_item_icon,
        _mock_champion_icon,
        auth_client,
        db,
        user,
    ):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_null_gold",
            champion="Ahri",
            win=True,
            kills=5,
            deaths=2,
            assists=7,
            kda=6.0,
            gold_earned=None,
            gold_per_min=400.0,
            total_damage=20000,
            damage_per_min=700.0,
            vision_score=25,
            cs_total=180,
            game_duration=30.0,
            recommendations=[],
            llm_analysis=None,
            queue_type="Ranked Solo",
            participants_json=[
                {
                    "is_player": True,
                    "team_id": 100,
                    "position": "MIDDLE",
                    "champion": "Ahri",
                    "summoner_name": "TestPlayer",
                    "item_ids": [],
                },
                {
                    "is_player": False,
                    "team_id": 200,
                    "position": "MIDDLE",
                    "champion": "Syndra",
                    "summoner_name": "EnemyPlayer",
                    "item_ids": [],
                },
            ],
        )
        db.session.add(match)
        db.session.commit()

        resp = auth_client.get(f"/dashboard/matches/{match.id}")
        assert resp.status_code == 200
        assert b"Gold Total" in resp.data
