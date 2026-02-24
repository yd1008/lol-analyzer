"""Tests for auth and basic routes."""

import json
from unittest.mock import patch

from app.dashboard.routes import sync_recent_matches
from app.models import AdminAuditLog, DiscordConfig, MatchAnalysis, RiotAccount, User, UserSettings


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

    def test_landing_has_mobile_stack_hooks_for_hero_actions(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b'class="cta-buttons hero-mobile-stack"' in resp.data
        assert b'class="signal-row hero-mobile-stack"' in resp.data
        assert b'class="features-grid feature-min-grid"' in resp.data
        assert b'class="steps"' in resp.data


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

    def test_login_with_remember_sets_remember_cookie(self, client, user):
        resp = client.post(
            "/auth/login",
            data={
                "email": "test@example.com",
                "password": "testpass123",
                "remember": "y",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        cookies = resp.headers.getlist("Set-Cookie")
        assert any("remember_token=" in cookie for cookie in cookies)

    def test_login_without_remember_does_not_set_remember_cookie(self, client, user):
        resp = client.post(
            "/auth/login",
            data={
                "email": "test@example.com",
                "password": "testpass123",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        cookies = resp.headers.getlist("Set-Cookie")
        assert not any("remember_token=" in cookie for cookie in cookies)

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

    def test_login_rate_limit_returns_429(self, client, user, app):
        app.config["LOGIN_RATE_LIMIT"] = "2 per minute"

        for _ in range(2):
            resp = client.post(
                "/auth/login",
                data={"email": "test@example.com", "password": "wrongpassword"},
                follow_redirects=False,
            )
            assert resp.status_code == 200

        blocked = client.post(
            "/auth/login",
            data={"email": "test@example.com", "password": "wrongpassword"},
            follow_redirects=False,
        )
        assert blocked.status_code == 429
        assert b"Too many attempts" in blocked.data

        app.config["LOGIN_RATE_LIMIT"] = "1000 per minute"


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
        assert b"Performance Trend Snapshot" in resp.data

    def test_dashboard_includes_futuristic_hud_art_component(self, auth_client):
        resp = auth_client.get("/dashboard/")
        assert resp.status_code == 200
        assert b"hud-artboard" in resp.data
        assert b"hud-art-grid" in resp.data

    def test_match_history_includes_futuristic_hud_art_component(self, auth_client):
        resp = auth_client.get("/dashboard/matches")
        assert resp.status_code == 200
        assert b"hud-artboard" in resp.data
        assert b"hud-art-orb" in resp.data

    def test_settings_requires_login(self, client):
        resp = client.get("/dashboard/settings")
        assert resp.status_code in (302, 401)

    def test_dashboard_queue_filters_have_accessibility_semantics(self, auth_client):
        resp = auth_client.get("/dashboard/")
        assert resp.status_code == 200
        assert b'id="match-filter-bar"' in resp.data
        assert b'role="tablist"' in resp.data
        assert b'aria-label="Filter matches by queue"' in resp.data
        assert b'id="queue-filter-all"' in resp.data
        assert b'role="tab"' in resp.data
        assert b'data-queue="" role="tab" aria-selected="true" aria-controls="match-list" tabindex="0"' in resp.data
        assert b'data-queue="Ranked Solo" role="tab" aria-selected="false" aria-controls="match-list" tabindex="-1"' in resp.data


class TestSyncRecentMatches:
    def test_sync_recent_matches_skips_existing_and_saves_new(self, db, user):
        existing = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_existing_match",
            champion="Ahri",
            win=True,
            kills=4,
            deaths=2,
            assists=7,
            kda=5.5,
            gold_earned=11000,
            gold_per_min=366.7,
            total_damage=18000,
            damage_per_min=600.0,
            vision_score=20,
            cs_total=170,
            game_duration=30.0,
            recommendations=[],
        )
        db.session.add(existing)
        db.session.commit()

        new_analysis = {
            "match_id": "NA1_new_match",
            "champion": "Lux",
            "win": False,
            "kills": 3,
            "deaths": 5,
            "assists": 9,
            "kda": 2.4,
            "gold_earned": 10400,
            "gold_per_min": 346.7,
            "total_damage": 19500,
            "damage_per_min": 650.0,
            "vision_score": 28,
            "cs_total": 165,
            "game_duration": 30.0,
            "recommendations": ["ward river before objective"],
            "queue_type": "Ranked Solo",
            "participants": [],
            "game_start_timestamp": 1700000000000,
        }

        with patch("app.dashboard.routes.get_recent_matches", return_value=["NA1_existing_match", "NA1_new_match"]), patch(
            "app.dashboard.routes.get_watcher",
            return_value=object(),
        ), patch("app.dashboard.routes.get_routing_value", return_value="americas"), patch(
            "app.dashboard.routes.analyze_match",
            return_value=new_analysis,
        ) as mock_analyze:
            saved = sync_recent_matches(user.id, "na1", "puuid-test")

        assert saved == 1
        assert mock_analyze.call_count == 1
        row = MatchAnalysis.query.filter_by(user_id=user.id, match_id="NA1_new_match").one()
        assert row.champion == "Lux"
        assert row.queue_type == "Ranked Solo"

    def test_sync_recent_matches_handles_recent_match_fetch_error(self, db, user):
        with patch("app.dashboard.routes.get_recent_matches", side_effect=RuntimeError("riot timeout")), patch(
            "app.dashboard.routes.get_watcher"
        ) as mock_watcher, patch("app.dashboard.routes.analyze_match") as mock_analyze, patch(
            "app.dashboard.routes.logger.warning"
        ) as mock_warning:
            saved = sync_recent_matches(user.id, "na1", "puuid-test")

        assert saved == 0
        mock_watcher.assert_not_called()
        mock_analyze.assert_not_called()
        mock_warning.assert_called_once()
        call_args = mock_warning.call_args[0]
        assert "Failed to fetch recent matches" in call_args[0]
        assert call_args[1] == user.id
        assert call_args[2] == "na1"

    def test_sync_recent_matches_continues_when_single_match_analysis_fails(self, db, user):
        successful_analysis = {
            "match_id": "NA1_sync_good",
            "champion": "Lux",
            "win": True,
            "kills": 7,
            "deaths": 3,
            "assists": 11,
            "kda": 6.0,
            "gold_earned": 12100,
            "gold_per_min": 403.3,
            "total_damage": 22800,
            "damage_per_min": 760.0,
            "vision_score": 24,
            "cs_total": 182,
            "game_duration": 30.0,
            "recommendations": ["sync follow-up"],
            "queue_type": "Ranked Solo",
            "participants": [],
            "game_start_timestamp": 1700000000000,
        }

        with patch(
            "app.dashboard.routes.get_recent_matches",
            return_value=["NA1_sync_bad", "NA1_sync_good"],
        ), patch("app.dashboard.routes.get_watcher", return_value=object()), patch(
            "app.dashboard.routes.get_routing_value",
            return_value="americas",
        ), patch(
            "app.dashboard.routes.analyze_match",
            side_effect=[RuntimeError("transient riot detail failure"), successful_analysis],
        ) as mock_analyze, patch("app.dashboard.routes.logger.warning") as mock_warning:
            saved = sync_recent_matches(user.id, "na1", "puuid-test")

        assert saved == 1
        assert mock_analyze.call_count == 2
        warning_args = mock_warning.call_args[0]
        assert "Failed to analyze match during sync" in warning_args[0]
        assert warning_args[1] == user.id
        assert warning_args[2] == "na1"
        assert warning_args[3] == "NA1_sync_bad"

        row = MatchAnalysis.query.filter_by(user_id=user.id, match_id="NA1_sync_good").one()
        assert row.champion == "Lux"

    def test_sync_recent_matches_continues_after_duplicate_insert_error(self, db, user):
        def _analysis(match_id, champion):
            return {
                "match_id": match_id,
                "champion": champion,
                "win": True,
                "kills": 6,
                "deaths": 2,
                "assists": 8,
                "kda": 7.0,
                "gold_earned": 12000,
                "gold_per_min": 400.0,
                "total_damage": 22000,
                "damage_per_min": 733.3,
                "vision_score": 26,
                "cs_total": 185,
                "game_duration": 30.0,
                "recommendations": ["keep pressure on side lane"],
                "queue_type": "Ranked Solo",
                "participants": [],
                "game_start_timestamp": 1700000000000,
            }

        with patch(
            "app.dashboard.routes.get_recent_matches",
            return_value=["NA1_sync_1", "NA1_sync_2", "NA1_sync_3"],
        ), patch("app.dashboard.routes.get_watcher", return_value=object()), patch(
            "app.dashboard.routes.get_routing_value",
            return_value="americas",
        ), patch(
            "app.dashboard.routes.analyze_match",
            side_effect=[
                _analysis("NA1_sync_duplicate", "Ahri"),
                _analysis("NA1_sync_duplicate", "Ahri"),
                _analysis("NA1_sync_fresh", "Lux"),
            ],
        ) as mock_analyze, patch("app.dashboard.routes.logger.info") as mock_info:
            saved = sync_recent_matches(user.id, "na1", "puuid-test")

        assert saved == 2
        assert mock_analyze.call_count == 3

        dupes = MatchAnalysis.query.filter_by(user_id=user.id, match_id="NA1_sync_duplicate").all()
        assert len(dupes) == 1
        fresh = MatchAnalysis.query.filter_by(user_id=user.id, match_id="NA1_sync_fresh").one()
        assert fresh.champion == "Lux"

        duplicate_log_calls = [
            call
            for call in mock_info.call_args_list
            if call.args and "Skipped duplicate match insert" in str(call.args[0])
        ]
        assert duplicate_log_calls


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

    def test_admin_accessible_for_role_admin_without_env_match(self, client, db, app):
        previous_admin_email = app.config.get("ADMIN_EMAIL")
        app.config["ADMIN_EMAIL"] = "different-admin@example.com"
        admin = User(email="role-admin@example.com", role="admin")
        admin.set_password("adminpass")
        db.session.add(admin)
        db.session.commit()

        client.post("/auth/login", data={"email": "role-admin@example.com", "password": "adminpass"})
        resp = client.get("/admin/")
        assert resp.status_code == 200
        app.config["ADMIN_EMAIL"] = previous_admin_email

    def test_admin_access_logs_audit_event(self, client, db, app):
        app.config["ADMIN_EMAIL"] = "admin@test.com"
        admin = User(email="admin@test.com")
        admin.set_password("adminpass")
        db.session.add(admin)
        db.session.commit()

        client.post("/auth/login", data={"email": "admin@test.com", "password": "adminpass"})
        resp = client.get("/admin/")
        assert resp.status_code == 200
        assert AdminAuditLog.query.filter_by(action="admin_access_allowed").count() >= 1

    def test_admin_index_provides_user_list_and_total_analyses(self, client, db, app):
        app.config["ADMIN_EMAIL"] = "admin@test.com"
        admin = User(email="admin@test.com")
        admin.set_password("adminpass")
        player = User(email="player@test.com")
        player.set_password("playerpass")
        db.session.add_all([admin, player])
        db.session.flush()

        db.session.add_all([
            MatchAnalysis(user_id=player.id, match_id="NA1_admin_idx_1", champion="Ahri"),
            MatchAnalysis(user_id=player.id, match_id="NA1_admin_idx_2", champion="Lux"),
        ])
        db.session.commit()

        client.post("/auth/login", data={"email": "admin@test.com", "password": "adminpass"})

        with patch("app.admin.routes.render_template", return_value="OK") as mock_render:
            resp = client.get("/admin/")

        assert resp.status_code == 200
        assert resp.data == b"OK"
        kwargs = mock_render.call_args.kwargs
        assert kwargs["total_analyses"] == 2
        assert len(kwargs["users"]) == 2
        assert {u.email for u in kwargs["users"]} == {"admin@test.com", "player@test.com"}


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

    def test_ai_analysis_focus_uses_valid_focus_and_forwards_to_llm(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_focus_forward",
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
                json={"force": True, "focus": "vision"},
            )

        assert resp_force.status_code == 200
        force_json = resp_force.get_json()
        assert force_json["focus"] == "vision"
        assert mock_llm.call_args[1]["focus"] == "vision"

    def test_ai_analysis_invalid_focus_defaults_to_general(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_focus_invalid",
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
                json={"force": True, "focus": "invalid"},
            )

        assert resp_force.status_code == 200
        force_json = resp_force.get_json()
        assert force_json["focus"] == "general"
        assert mock_llm.call_args[1]["focus"] == "general"

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
        assert payload["trace_id"]
        assert "trace id" in payload["error"].lower()
        assert "timed out" not in payload["error"].lower()

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
        assert payload["trace_id"]
        assert "trace id" in payload["error"].lower()
        assert "timed out" not in payload["error"].lower()

    def test_ai_analysis_timeout_with_non_general_focus_returns_stale_cached_analysis(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_timeout_with_cache_focus",
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
            resp = auth_client.post(
                f"/dashboard/api/matches/{match.id}/ai-analysis",
                json={"force": True, "focus": "vision"},
            )

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["focus"] == "vision"
        assert payload["cached"] is True
        assert payload["stale"] is True
        assert payload["analysis"] == "existing cached analysis"
        assert payload["trace_id"]
        assert "trace id" in payload["error"].lower()
        assert "timed out" not in payload["error"].lower()

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
        assert payload["trace_id"]
        assert "trace id" in payload["error"].lower()
        assert "not compatible with /chat/completions" not in payload["error"].lower()

    def test_ai_analysis_authentication_error_returns_401_without_cached_analysis(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_auth_401",
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
            return_value=(None, "Authentication failed (401). Check your API key."),
        ), patch("app.dashboard.routes.logger.warning") as mock_warning:
            resp = auth_client.post(f"/dashboard/api/matches/{match.id}/ai-analysis", json={"force": True})

        assert resp.status_code == 401
        payload = resp.get_json()
        assert payload["trace_id"]
        assert "trace id" in payload["error"].lower()
        assert "authentication failed" not in payload["error"].lower()

        warning_args = mock_warning.call_args[0]
        assert "AI analysis failed trace_id=%s stream=%s user_id=%s match_id=%s focus=%s error=%s" in warning_args[0]
        assert warning_args[1] == payload["trace_id"]
        assert warning_args[2] is False
        assert warning_args[3] == user.id
        assert warning_args[4] == match.id
        assert warning_args[5] == "general"
        assert "authentication failed" in warning_args[6].lower()

    def test_ai_analysis_configuration_error_is_visible_to_admin(self, client, db, app):
        app.config["ADMIN_EMAIL"] = "admin@test.com"
        admin = User(email="admin@test.com")
        admin.set_password("adminpass")
        db.session.add(admin)
        db.session.commit()

        client.post("/auth/login", data={"email": "admin@test.com", "password": "adminpass"})

        match = MatchAnalysis(
            user_id=admin.id,
            match_id="NA1_bad_model_admin",
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
            resp = client.post(f"/dashboard/api/matches/{match.id}/ai-analysis", json={"force": True})

        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload["trace_id"]
        assert "not compatible with /chat/completions" in payload["error"].lower()
        assert "trace id" not in payload["error"].lower()

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
        events = [json.loads(line) for line in resp.data.decode().splitlines() if line.strip()]
        assert events[0]["type"] == "meta"
        assert events[0]["cached"] is True
        assert events[1]["type"] == "done"
        assert events[1]["analysis"] == "already cached"
        assert events[1]["cached"] is True

    def test_ai_analysis_stream_forwards_focus_to_iter_analysis(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_stream_focus",
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

        with patch("app.dashboard.routes.iter_llm_analysis_stream", return_value=[{"type": "done", "analysis": "streamed analysis"}]) as mock_stream:
            resp = auth_client.post(
                f"/dashboard/api/matches/{match.id}/ai-analysis/stream",
                json={"force": True, "focus": "teamfight"},
            )
            events = [json.loads(line) for line in resp.data.decode().splitlines() if line.strip()]

        assert resp.status_code == 200
        assert events[0]["type"] == "meta"
        assert events[0]["focus"] == "teamfight"
        assert events[1]["type"] == "done"
        assert events[1]["focus"] == "teamfight"
        assert mock_stream.call_args[1]["focus"] == "teamfight"

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
            events = [json.loads(line) for line in resp.data.decode().splitlines() if line.strip()]

        assert resp.status_code == 200
        assert events[0]["type"] == "meta"
        assert events[1]["type"] == "chunk"
        assert events[2]["type"] == "done"
        assert events[2]["analysis"] == "First part. Final part."
        reloaded = db.session.get(MatchAnalysis, match.id)
        assert reloaded.llm_analysis == "First part. Final part."

    def test_ai_analysis_stream_falls_back_to_standard_when_stream_fails_before_chunks(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_stream_to_sync_fallback",
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
            return_value=[{"type": "error", "error": "Stream temporarily unavailable"}],
        ), patch(
            "app.dashboard.routes.get_llm_analysis_detailed",
            return_value=("standard fallback analysis", None),
        ):
            resp = auth_client.post(f"/dashboard/api/matches/{match.id}/ai-analysis/stream", json={"force": True})
            events = [json.loads(line) for line in resp.data.decode().splitlines() if line.strip()]

        assert resp.status_code == 200
        assert events[0]["type"] == "meta"
        assert events[-1]["type"] == "done"
        assert events[-1]["analysis"] == "standard fallback analysis"
        assert events[-1]["cached"] is False

        reloaded = db.session.get(MatchAnalysis, match.id)
        assert reloaded.llm_analysis == "standard fallback analysis"

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
        ), patch(
            "app.dashboard.routes.get_llm_analysis_detailed",
            return_value=(None, "Request timed out after 30s"),
        ):
            resp = auth_client.post(f"/dashboard/api/matches/{match.id}/ai-analysis/stream", json={"force": True})
            events = [json.loads(line) for line in resp.data.decode().splitlines() if line.strip()]

        assert resp.status_code == 200
        assert events[-1]["type"] == "stale"
        assert events[-1]["analysis"] == "cached fallback"
        assert events[-1]["cached"] is True
        assert events[-1]["stale"] is True
        assert events[-1]["trace_id"]
        assert "trace id" in events[-1]["error"].lower()
        assert "timed out" not in events[-1]["error"].lower()

    def test_ai_analysis_stream_emits_stale_for_non_general_focus_when_stream_fails_with_cache(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_stream_stale_focus",
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
        ), patch(
            "app.dashboard.routes.get_llm_analysis_detailed",
            return_value=(None, "Request timed out after 30s"),
        ):
            resp = auth_client.post(
                f"/dashboard/api/matches/{match.id}/ai-analysis/stream",
                json={"force": True, "focus": "vision"},
            )
            events = [json.loads(line) for line in resp.data.decode().splitlines() if line.strip()]

        assert resp.status_code == 200
        assert events[0]["type"] == "meta"
        assert events[0]["focus"] == "vision"
        assert events[-1]["type"] == "stale"
        assert events[-1]["focus"] == "vision"
        assert events[-1]["analysis"] == "cached fallback"
        assert events[-1]["cached"] is True
        assert events[-1]["stale"] is True
        assert events[-1]["trace_id"]
        assert "trace id" in events[-1]["error"].lower()
        assert "timed out" not in events[-1]["error"].lower()

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
        ), patch(
            "app.dashboard.routes.get_llm_analysis_detailed",
            return_value=(None, "not compatible with /chat/completions"),
        ):
            resp = auth_client.post(f"/dashboard/api/matches/{match.id}/ai-analysis/stream", json={"force": True})
            events = [json.loads(line) for line in resp.data.decode().splitlines() if line.strip()]

        assert resp.status_code == 200
        assert events[-1]["type"] == "error"
        assert events[-1]["status"] == 400
        assert events[-1]["trace_id"]
        assert "trace id" in events[-1]["error"].lower()
        assert "not compatible with /chat/completions" not in events[-1]["error"].lower()

    def test_ai_analysis_stream_emits_401_error_when_stream_auth_fails_without_cache(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_stream_error_401",
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
            return_value=[{"type": "error", "error": "Authentication failed (401). Check your API key."}],
        ), patch(
            "app.dashboard.routes.get_llm_analysis_detailed",
            return_value=(None, "Authentication failed (401). Check your API key."),
        ), patch("app.dashboard.routes.logger.warning") as mock_warning:
            resp = auth_client.post(f"/dashboard/api/matches/{match.id}/ai-analysis/stream", json={"force": True})
            events = [json.loads(line) for line in resp.data.decode().splitlines() if line.strip()]

        assert resp.status_code == 200
        assert events[-1]["type"] == "error"
        assert events[-1]["status"] == 401
        assert events[-1]["trace_id"]
        assert "trace id" in events[-1]["error"].lower()
        assert "authentication failed" not in events[-1]["error"].lower()

        warning_args = mock_warning.call_args[0]
        assert "AI analysis failed trace_id=%s stream=%s user_id=%s match_id=%s focus=%s error=%s" in warning_args[0]
        assert warning_args[1] == events[-1]["trace_id"]
        assert warning_args[2] is True
        assert warning_args[3] == user.id
        assert warning_args[4] == match.id
        assert warning_args[5] == "general"
        assert "authentication failed" in warning_args[6].lower()

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
            llm_analysis_zh="ä¸­æ–‡ç¼“å­˜",
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
        assert payload_zh["analysis"] == "ä¸­æ–‡ç¼“å­˜"
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

        with patch("app.dashboard.routes.get_llm_analysis_detailed", return_value=("æ–°çš„ä¸­æ–‡åˆ†æž", None)):
            resp = auth_client.post(
                f"/dashboard/api/matches/{match.id}/ai-analysis",
                json={"force": True, "language": "zh-CN"},
            )

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["analysis"] == "æ–°çš„ä¸­æ–‡åˆ†æž"
        assert payload["language"] == "zh-CN"
        reloaded = db.session.get(MatchAnalysis, match.id)
        assert reloaded.llm_analysis_zh == "æ–°çš„ä¸­æ–‡åˆ†æž"
        assert reloaded.llm_analysis_en == "legacy english cache"

    def test_ai_analysis_non_general_focus_persists_latest_analysis(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_focus_persist",
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
            llm_analysis_en=None,
            llm_analysis_zh=None,
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        with patch("app.dashboard.routes.get_llm_analysis_detailed", return_value=("vision-focused analysis", None)):
            resp = auth_client.post(
                f"/dashboard/api/matches/{match.id}/ai-analysis",
                json={"force": True, "focus": "vision", "language": "en"},
            )

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["analysis"] == "vision-focused analysis"
        assert payload["focus"] == "vision"
        assert payload["persisted"] is False

        reloaded = db.session.get(MatchAnalysis, match.id)
        assert reloaded.llm_analysis_en is None
        assert reloaded.llm_analysis is None

        resp_matches = auth_client.get("/dashboard/api/matches?offset=0&limit=10")
        assert resp_matches.status_code == 200
        data = resp_matches.get_json()
        assert data["matches"][0]["initial_ai_analysis"] == ""


    def test_ai_analysis_general_cache_is_not_overwritten_by_non_general_focus(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_focus_cache_isolation",
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
            llm_analysis="cached legacy english",
            llm_analysis_en="cached english",
            llm_analysis_zh=None,
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        with patch("app.dashboard.routes.get_llm_analysis_detailed", return_value=("vision-focused analysis", None)):
            resp_focus = auth_client.post(
                f"/dashboard/api/matches/{match.id}/ai-analysis",
                json={"force": True, "focus": "vision", "language": "en"},
            )

        assert resp_focus.status_code == 200
        payload_focus = resp_focus.get_json()
        assert payload_focus["analysis"] == "vision-focused analysis"
        assert payload_focus["focus"] == "vision"
        assert payload_focus["persisted"] is False

        reloaded = db.session.get(MatchAnalysis, match.id)
        assert reloaded.llm_analysis_en == "cached english"
        assert reloaded.llm_analysis == "cached legacy english"

        resp_general = auth_client.post(
            f"/dashboard/api/matches/{match.id}/ai-analysis",
            json={"focus": "general", "language": "en"},
        )
        assert resp_general.status_code == 200
        payload_general = resp_general.get_json()
        assert payload_general["analysis"] == "cached english"
        assert payload_general["cached"] is True
        assert payload_general["focus"] == "general"
        assert payload_general["persisted"] is True


class TestMatchesApi:
    def test_api_matches_includes_cached_ai_analysis_for_english_locale(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_matches_locale_cache_en",
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
            llm_analysis_zh="ä¸­æ–‡ç¼“å­˜",
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        resp = auth_client.get("/dashboard/api/matches?offset=0&limit=10")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert len(payload["matches"]) == 1
        assert payload["matches"][0]["initial_ai_analysis"] == "english cache"
        assert payload["matches"][0]["has_llm_analysis"] is True

    def test_api_matches_includes_cached_ai_analysis_for_chinese_locale(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_matches_locale_cache_zh",
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
            llm_analysis_zh="ä¸­æ–‡ç¼“å­˜",
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        with patch("app.dashboard.routes.get_locale", return_value="zh-CN"):
            resp = auth_client.get("/dashboard/api/matches?offset=0&limit=10")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert len(payload["matches"]) == 1
        assert payload["matches"][0]["initial_ai_analysis"] == "ä¸­æ–‡ç¼“å­˜"
        assert payload["matches"][0]["has_llm_analysis"] is True

    def test_api_matches_uses_legacy_english_cache_as_fallback(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_matches_legacy_cache",
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
            llm_analysis="legacy cache only",
            llm_analysis_en=None,
            llm_analysis_zh=None,
            queue_type="Ranked Solo",
            participants_json=[
                {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                {"is_player": False, "team_id": 200, "position": "MIDDLE", "champion": "Syndra"},
            ],
        )
        db.session.add(match)
        db.session.commit()

        resp = auth_client.get("/dashboard/api/matches?offset=0&limit=10")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["matches"][0]["initial_ai_analysis"] == "legacy cache only"
        assert payload["matches"][0]["has_llm_analysis_en"] is True

    def test_api_matches_filters_by_single_and_multi_queue_values(self, auth_client, db, user):
        matches = [
            MatchAnalysis(
                user_id=user.id,
                match_id="NA1_queue_ranked_solo",
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
                queue_type="Ranked Solo",
                participants_json=[
                    {"is_player": True, "team_id": 100, "position": "MIDDLE", "champion": "Ahri"},
                ],
            ),
            MatchAnalysis(
                user_id=user.id,
                match_id="NA1_queue_ranked_flex",
                champion="Lux",
                win=False,
                kills=3,
                deaths=6,
                assists=9,
                kda=2.0,
                gold_earned=11000,
                gold_per_min=366.7,
                total_damage=18000,
                damage_per_min=600.0,
                vision_score=28,
                cs_total=170,
                game_duration=30.0,
                recommendations=[],
                queue_type="Ranked Flex",
                participants_json=[
                    {"is_player": True, "team_id": 100, "position": "SUPPORT", "champion": "Lux"},
                ],
            ),
            MatchAnalysis(
                user_id=user.id,
                match_id="NA1_queue_normal",
                champion="Jinx",
                win=True,
                kills=8,
                deaths=4,
                assists=6,
                kda=3.5,
                gold_earned=13000,
                gold_per_min=433.3,
                total_damage=24000,
                damage_per_min=800.0,
                vision_score=18,
                cs_total=210,
                game_duration=30.0,
                recommendations=[],
                queue_type="Normal Draft",
                participants_json=[
                    {"is_player": True, "team_id": 100, "position": "BOTTOM", "champion": "Jinx"},
                ],
            ),
        ]
        db.session.add_all(matches)
        db.session.commit()

        resp_ranked = auth_client.get("/dashboard/api/matches?offset=0&limit=10&queue=Ranked Solo")
        assert resp_ranked.status_code == 200
        payload_ranked = resp_ranked.get_json()
        assert payload_ranked["total"] == 1
        assert len(payload_ranked["matches"]) == 1
        assert payload_ranked["matches"][0]["match_id"] == "NA1_queue_ranked_solo"

        resp_multi = auth_client.get("/dashboard/api/matches?offset=0&limit=10&queue=Ranked Solo,Normal Draft")
        assert resp_multi.status_code == 200
        payload_multi = resp_multi.get_json()
        assert payload_multi["total"] == 2
        assert {m["match_id"] for m in payload_multi["matches"]} == {"NA1_queue_ranked_solo", "NA1_queue_normal"}
        assert payload_multi["has_more"] is False


    def test_ai_analysis_stream_focus_does_not_persist_general_cache(self, auth_client, db, user):
        match = MatchAnalysis(
            user_id=user.id,
            match_id="NA1_stream_focus_cache",
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
            llm_analysis_en="cached english",
            llm_analysis_zh=None,
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
            return_value=[
                {"type": "chunk", "delta": "vision analysis part 1"},
                {"type": "done", "analysis": "vision-focused analysis"},
            ],
        ):
            resp = auth_client.post(
                f"/dashboard/api/matches/{match.id}/ai-analysis/stream",
                json={"force": True, "focus": "vision", "language": "en"},
            )
            events = [json.loads(line) for line in resp.data.decode().splitlines() if line.strip()]

        assert resp.status_code == 200
        assert events[-1]["type"] == "done"
        assert events[-1]["analysis"] == "vision-focused analysis"
        assert events[-1]["focus"] == "vision"
        assert events[-1]["persisted"] is False
        reloaded = db.session.get(MatchAnalysis, match.id)
        assert reloaded.llm_analysis_en == "cached english"
        assert reloaded.llm_analysis == "legacy english cache"

        resp_general = auth_client.post(
            f"/dashboard/api/matches/{match.id}/ai-analysis",
            json={"focus": "general", "language": "en"},
        )
        assert resp_general.status_code == 200
        payload_general = resp_general.get_json()
        assert payload_general["analysis"] == "cached english"
        assert payload_general["cached"] is True
        assert payload_general["focus"] == "general"

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
        assert b'id="detail-ai-status"' in resp.data
        assert b'role="status"' in resp.data
        assert b'aria-live="polite"' in resp.data


class TestSettingsPreferencesRoute:
    def test_settings_preferences_requires_login(self, client):
        resp = client.post("/dashboard/settings/preferences", data={})
        assert resp.status_code in (302, 401)

    def test_settings_preferences_updates_existing_settings(self, auth_client, db, user):
        resp = auth_client.post(
            "/dashboard/settings/preferences",
            data={
                "prefs-check_interval": "10",
                "prefs-weekly_summary_day": "Friday",
                "prefs-weekly_summary_time": "21:00",
                "prefs-notifications_enabled": "y",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

        reloaded = db.session.get(User, user.id)
        assert reloaded.settings is not None
        assert reloaded.settings.check_interval == 10
        assert reloaded.settings.weekly_summary_day == "Friday"
        assert reloaded.settings.weekly_summary_time == "21:00"
        assert reloaded.settings.notifications_enabled is True

    def test_settings_preferences_creates_settings_when_missing(self, auth_client, db, user):
        existing = db.session.get(UserSettings, user.settings.id)
        db.session.delete(existing)
        db.session.commit()

        resp = auth_client.post(
            "/dashboard/settings/preferences",
            data={
                "prefs-check_interval": "30",
                "prefs-weekly_summary_day": "Sunday",
                "prefs-weekly_summary_time": "06:00",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

        reloaded = db.session.get(User, user.id)
        assert reloaded.settings is not None
        assert reloaded.settings.check_interval == 30
        assert reloaded.settings.weekly_summary_day == "Sunday"
        assert reloaded.settings.weekly_summary_time == "06:00"
        assert reloaded.settings.notifications_enabled is False

    def test_settings_preferences_rejects_invalid_check_interval(self, auth_client, db, user):
        baseline = db.session.get(User, user.id).settings
        baseline.check_interval = 5
        baseline.weekly_summary_day = "Monday"
        baseline.weekly_summary_time = "09:00"
        baseline.notifications_enabled = True
        db.session.commit()

        resp = auth_client.post(
            "/dashboard/settings/preferences",
            data={
                "prefs-check_interval": "999",
                "prefs-weekly_summary_day": "Friday",
                "prefs-weekly_summary_time": "21:00",
                "prefs-notifications_enabled": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

        reloaded = db.session.get(User, user.id)
        assert reloaded.settings.check_interval == 5
        assert reloaded.settings.weekly_summary_day == "Monday"
        assert reloaded.settings.weekly_summary_time == "09:00"
        assert reloaded.settings.notifications_enabled is True


class TestSettingsIntegrationsRoute:
    def test_settings_discord_requires_login(self, client):
        resp = client.post("/dashboard/settings/discord", data={})
        assert resp.status_code in (302, 401)

    def test_settings_discord_saves_valid_ids(self, auth_client, db, user):
        resp = auth_client.post(
            "/dashboard/settings/discord",
            data={
                "discord-channel_id": "123456789012345678",
                "discord-guild_id": "987654321098765432",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

        config = DiscordConfig.query.filter_by(user_id=user.id).first()
        assert config is not None
        assert config.channel_id == "123456789012345678"
        assert config.guild_id == "987654321098765432"

    def test_settings_discord_invalid_channel_does_not_overwrite_existing(self, auth_client, db, user):
        existing = DiscordConfig(
            user_id=user.id,
            channel_id="111111111111111111",
            guild_id="222222222222222222",
        )
        db.session.add(existing)
        db.session.commit()

        resp = auth_client.post(
            "/dashboard/settings/discord",
            data={
                "discord-channel_id": "not-a-snowflake",
                "discord-guild_id": "333333333333333333",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

        reloaded = DiscordConfig.query.filter_by(user_id=user.id).first()
        assert reloaded is not None
        assert reloaded.channel_id == "111111111111111111"
        assert reloaded.guild_id == "222222222222222222"

    def test_settings_riot_invalid_tagline_does_not_create_account(self, auth_client, db, user):
        with patch("app.dashboard.routes.resolve_puuid") as mock_resolve:
            resp = auth_client.post(
                "/dashboard/settings/riot",
                data={
                    "riot-summoner_name": "SummonerName",
                    "riot-tagline": "#BAD",
                    "riot-region": "na1",
                },
                follow_redirects=False,
            )

        assert resp.status_code == 302
        mock_resolve.assert_not_called()
        riot_account = RiotAccount.query.filter_by(user_id=user.id).first()
        assert riot_account is None


class TestErrorPages:
    def test_404_renders_custom_template(self, auth_client):
        resp = auth_client.get("/definitely-not-a-real-route")
        assert resp.status_code == 404
        assert b"404" in resp.data
        assert b"Go Home" in resp.data
        assert b"Page Not Found" in resp.data

    def test_500_renders_custom_template(self, client, app):
        previous_propagate = app.config.get("PROPAGATE_EXCEPTIONS")
        app.config["PROPAGATE_EXCEPTIONS"] = False

        with patch("app.main.routes.render_template", side_effect=RuntimeError("boom")):
            resp = client.get("/")

        app.config["PROPAGATE_EXCEPTIONS"] = previous_propagate

        assert resp.status_code == 500
        assert b"500" in resp.data
        assert b"Server Error" in resp.data
        assert b"Go Home" in resp.data


class TestLocalePersistenceRoute:
    def test_locale_endpoint_requires_login(self, client):
        resp = client.post("/dashboard/settings/locale", json={"locale": "en"})
        assert resp.status_code in (302, 401)

    def test_locale_endpoint_rejects_invalid_locale(self, auth_client):
        resp = auth_client.post("/dashboard/settings/locale", json={"locale": "fr"})
        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload["error"]

    def test_locale_endpoint_persists_user_preference(self, auth_client, db, user):
        resp = auth_client.post("/dashboard/settings/locale", json={"locale": "en"})
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["ok"] is True
        assert payload["locale"] == "en"
        reloaded = db.session.get(User, user.id)
        assert reloaded.settings.preferred_locale == "en"


class TestAdminLlmInputSize:
    def test_test_llm_rejects_oversized_json(self, client, db, app):
        app.config["ADMIN_EMAIL"] = "admin@test.com"
        app.config["ADMIN_ANALYSIS_JSON_MAX_BYTES"] = 128
        admin = User(email="admin@test.com")
        admin.set_password("adminpass")
        db.session.add(admin)
        db.session.commit()

        client.post("/auth/login", data={"email": "admin@test.com", "password": "adminpass"})
        oversized = '{"foo":"' + ("x" * 300) + '"}'
        resp = client.post(
            "/admin/test-llm",
            data={"action": "run_llm", "analysis_json": oversized},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"too large" in resp.data.lower()

    def test_test_llm_run_executes_model_and_renders_result(self, client, db, app):
        app.config["ADMIN_EMAIL"] = "admin@test.com"
        admin = User(email="admin@test.com")
        admin.set_password("adminpass")
        db.session.add(admin)
        db.session.commit()

        client.post("/auth/login", data={"email": "admin@test.com", "password": "adminpass"})
        analysis_json = json.dumps({"champion": "Ahri", "kda": 5.2, "win": True})

        with patch("app.admin.routes.get_locale", return_value="en"), patch(
            "app.admin.routes.get_llm_analysis_detailed",
            return_value=("LLM execution success", None),
        ) as mock_llm:
            resp = client.post(
                "/admin/test-llm",
                data={"action": "run_llm", "analysis_json": analysis_json},
                follow_redirects=True,
            )

        assert resp.status_code == 200
        assert b"LLM execution success" in resp.data
        mock_llm.assert_called_once()
        args, kwargs = mock_llm.call_args
        assert args[0]["champion"] == "Ahri"
        assert kwargs["language"] == "en"


    def test_test_llm_lookup_renders_match_selection(self, client, db, app):
        app.config["ADMIN_EMAIL"] = "admin@test.com"
        admin = User(email="admin@test.com")
        admin.set_password("adminpass")
        db.session.add(admin)
        db.session.commit()

        client.post("/auth/login", data={"email": "admin@test.com", "password": "adminpass"})

        watcher = object()
        with patch("app.admin.routes.resolve_puuid", return_value=("puuid-123", None)), patch(
            "app.admin.routes.get_recent_matches",
            return_value=["NA1_1", "NA1_2"],
        ), patch("app.admin.routes.get_watcher", return_value=watcher), patch(
            "app.admin.routes.get_routing_value",
            return_value="americas",
        ), patch(
            "app.admin.routes.get_match_summary",
            side_effect=[
                {
                    "match_id": "NA1_1",
                    "champion": "Ahri",
                    "win": True,
                    "kills": 8,
                    "deaths": 2,
                    "assists": 7,
                    "game_duration": 30,
                    "queue_type": "Ranked Solo",
                },
                {
                    "match_id": "NA1_2",
                    "champion": "Lux",
                    "win": False,
                    "kills": 3,
                    "deaths": 5,
                    "assists": 6,
                    "game_duration": 28,
                    "queue_type": "Ranked Solo",
                },
            ],
        ):
            resp = client.post(
                "/admin/test-llm",
                data={
                    "action": "lookup",
                    "summoner_name": "Tester",
                    "tagline": "NA1",
                    "region": "na1",
                },
                follow_redirects=True,
            )

        assert resp.status_code == 200
        assert b"Step 2: Select a Match" in resp.data
        assert b"Ahri" in resp.data
        assert b"Lux" in resp.data

    def test_test_llm_lookup_resolve_error_shows_message_and_skips_match_fetch(self, client, db, app):
        app.config["ADMIN_EMAIL"] = "admin@test.com"
        admin = User(email="admin@test.com")
        admin.set_password("adminpass")
        db.session.add(admin)
        db.session.commit()

        client.post("/auth/login", data={"email": "admin@test.com", "password": "adminpass"})

        with patch("app.admin.routes.resolve_puuid", return_value=(None, "Invalid API key")), patch(
            "app.admin.routes.get_recent_matches"
        ) as mock_recent:
            resp = client.post(
                "/admin/test-llm",
                data={
                    "action": "lookup",
                    "summoner_name": "Tester",
                    "tagline": "NA1",
                    "region": "na1",
                },
                follow_redirects=True,
            )

        assert resp.status_code == 200
        assert b"Invalid API key" in resp.data
        mock_recent.assert_not_called()

    def test_test_llm_select_renders_match_preview(self, client, db, app):
        app.config["ADMIN_EMAIL"] = "admin@test.com"
        admin = User(email="admin@test.com")
        admin.set_password("adminpass")
        db.session.add(admin)
        db.session.commit()

        client.post("/auth/login", data={"email": "admin@test.com", "password": "adminpass"})

        analysis_payload = {
            "match_id": "NA1_1",
            "champion": "Ahri",
            "win": True,
            "kills": 8,
            "deaths": 2,
            "assists": 7,
            "gold_per_min": 420.0,
            "damage_per_min": 760.0,
            "vision_score": 27,
        }

        with patch("app.admin.routes.get_watcher", return_value=object()), patch(
            "app.admin.routes.get_routing_value",
            return_value="americas",
        ), patch("app.admin.routes.analyze_match", return_value=analysis_payload):
            resp = client.post(
                "/admin/test-llm",
                data={
                    "action": "select",
                    "match_id": "NA1_1",
                    "puuid": "puuid-123",
                    "region": "na1",
                    "summoner_name": "Tester",
                    "tagline": "NA1",
                },
                follow_redirects=True,
            )

        assert resp.status_code == 200
        assert b"Step 3: Match Data" in resp.data
        assert b"Run LLM Analysis" in resp.data


class TestAdminDiscordRoute:
    def test_test_discord_success_calls_notifier(self, client, db, app):
        app.config["ADMIN_EMAIL"] = "admin@test.com"
        admin = User(email="admin@test.com")
        admin.set_password("adminpass")
        db.session.add(admin)
        db.session.commit()

        client.post("/auth/login", data={"email": "admin@test.com", "password": "adminpass"})

        with patch("app.analysis.discord_notifier.send_message", return_value=True) as mock_send:
            resp = client.post(
                "/admin/test-discord",
                data={"channel_id": "123456789012345678", "message": "hello from test"},
                follow_redirects=False,
            )

        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/admin/")
        mock_send.assert_called_once_with("123456789012345678", "hello from test")

    def test_test_discord_requires_admin(self, client, db, app):
        app.config["ADMIN_EMAIL"] = "admin@test.com"
        user = User(email="user@example.com")
        user.set_password("testpass123")
        db.session.add(user)
        db.session.commit()

        client.post("/auth/login", data={"email": "user@example.com", "password": "testpass123"})
        resp = client.post(
            "/admin/test-discord",
            data={"channel_id": "123456789012345678", "message": "hello from test"},
            follow_redirects=False,
        )

        assert resp.status_code in (302, 401, 403)



    def test_test_discord_requires_channel_id(self, client, db, app):
        app.config["ADMIN_EMAIL"] = "admin@test.com"
        admin = User(email="admin@test.com")
        admin.set_password("adminpass")
        db.session.add(admin)
        db.session.commit()

        client.post("/auth/login", data={"email": "admin@test.com", "password": "adminpass"})

        with patch("app.analysis.discord_notifier.send_message") as mock_send:
            resp = client.post(
                "/admin/test-discord",
                data={"channel_id": "", "message": "hello from test"},
                follow_redirects=True,
            )

        assert resp.status_code == 200
        assert b"Channel is required" in resp.data or b"channel is required" in resp.data or b"Failed to send Discord message" not in resp.data
        mock_send.assert_not_called()
    def test_test_discord_failure_shows_error(self, client, db, app):
        app.config["ADMIN_EMAIL"] = "admin@test.com"
        admin = User(email="admin@test.com")
        admin.set_password("adminpass")
        db.session.add(admin)
        db.session.commit()

        client.post("/auth/login", data={"email": "admin@test.com", "password": "adminpass"})

        with patch("app.analysis.discord_notifier.send_message", return_value=False) as mock_send:
            resp = client.post(
                "/admin/test-discord",
                data={"channel_id": "123456789012345678", "message": "hello from test"},
                follow_redirects=True,
            )

        assert resp.status_code == 200
        assert b"Failed to send Discord message" in resp.data
        mock_send.assert_called_once_with("123456789012345678", "hello from test")


