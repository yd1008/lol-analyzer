"""Tests for background match worker behavior."""

from concurrent.futures import Future
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import IntegrityError

from app.models import MatchAnalysis, RiotAccount, User, UserSettings
from worker import jobs


def _sample_analysis(match_id: str) -> dict:
    return {
        "match_id": match_id,
        "champion": "Ahri",
        "win": True,
        "kills": 8,
        "deaths": 2,
        "assists": 7,
        "kda": 7.5,
        "gold_earned": 12345,
        "gold_per_min": 410.0,
        "total_damage": 22000,
        "damage_per_min": 730.0,
        "vision_score": 28,
        "cs_total": 190,
        "game_duration": 30.0,
        "recommendations": ["good game"],
        "queue_type": "Ranked Solo",
        "participants": [],
        "game_start_timestamp": 1700000000000,
    }


def test_worker_writes_preferred_locale_column(app, db):
    user = User(email="worker-locale@test.com")
    user.set_password("pass12345")
    db.session.add(user)
    db.session.flush()
    db.session.add(UserSettings(user_id=user.id, preferred_locale="zh-CN", notifications_enabled=False))
    db.session.add(
        RiotAccount(
            user_id=user.id,
            summoner_name="WorkerLocale",
            tagline="NA1",
            region="na1",
            puuid="worker-locale-puuid",
            is_verified=True,
        )
    )
    db.session.commit()

    watcher = MagicMock()
    watcher.match.matchlist_by_puuid.return_value = ["NA1_worker_locale_1"]

    with patch("app.analysis.riot_api.get_watcher", return_value=watcher), patch(
        "app.analysis.engine.analyze_match",
        return_value=_sample_analysis("NA1_worker_locale_1"),
    ), patch("app.analysis.llm.get_llm_analysis", return_value="中文分析"):
        analyzed = jobs._process_user_matches(app, user.id)

    assert analyzed == 1
    row = MatchAnalysis.query.filter_by(user_id=user.id, match_id="NA1_worker_locale_1").one()
    assert row.llm_analysis_zh == "中文分析"
    assert row.llm_analysis_en is None
    assert row.llm_analysis is None


def test_worker_handles_integrity_error_without_crashing(app, db):
    user = User(email="worker-dup@test.com")
    user.set_password("pass12345")
    db.session.add(user)
    db.session.flush()
    db.session.add(UserSettings(user_id=user.id, preferred_locale="en", notifications_enabled=False))
    db.session.add(
        RiotAccount(
            user_id=user.id,
            summoner_name="WorkerDup",
            tagline="NA1",
            region="na1",
            puuid="worker-dup-puuid",
            is_verified=True,
        )
    )
    db.session.commit()

    watcher = MagicMock()
    watcher.match.matchlist_by_puuid.return_value = ["NA1_worker_dup_1"]

    with patch("app.analysis.riot_api.get_watcher", return_value=watcher), patch(
        "app.analysis.engine.analyze_match",
        return_value=_sample_analysis("NA1_worker_dup_1"),
    ), patch("app.analysis.llm.get_llm_analysis", return_value="english analysis"), patch(
        "app.extensions.db.session.commit",
        side_effect=IntegrityError("insert", {}, Exception("duplicate key")),
    ):
        analyzed = jobs._process_user_matches(app, user.id)

    assert analyzed == 0


def test_check_all_users_matches_respects_worker_max_workers(app, db):
    app.config["WORKER_MAX_WORKERS"] = 4
    user1 = User(email="worker-thread-1@test.com")
    user1.set_password("pass12345")
    user2 = User(email="worker-thread-2@test.com")
    user2.set_password("pass12345")
    db.session.add_all([user1, user2])
    db.session.commit()

    captured = {"max_workers": None}

    class DummyExecutor:
        def __init__(self, max_workers, thread_name_prefix=None):
            captured["max_workers"] = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def submit(self, fn, *args, **kwargs):
            future = Future()
            future.set_result(fn(*args, **kwargs))
            return future

    with patch("worker.jobs.ThreadPoolExecutor", DummyExecutor), patch(
        "worker.jobs._process_user_matches",
        return_value=1,
    ) as process_mock:
        jobs.check_all_users_matches(app)

    assert captured["max_workers"] == 2
    assert process_mock.call_count == 2
