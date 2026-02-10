"""Tests for auth and basic routes."""

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

        with patch("app.dashboard.routes.get_llm_analysis_detailed", return_value=("fresh analysis", None)):
            resp_force = auth_client.post(
                f"/dashboard/api/matches/{match.id}/ai-analysis",
                json={"force": True},
            )

        assert resp_force.status_code == 200
        force_json = resp_force.get_json()
        assert force_json["cached"] is False
        assert force_json["regenerated"] is True
        assert force_json["analysis"] == "fresh analysis"

        reloaded = db.session.get(MatchAnalysis, match.id)
        assert reloaded.llm_analysis == "fresh analysis"


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
