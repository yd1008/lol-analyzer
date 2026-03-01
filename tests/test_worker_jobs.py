"""Tests for background match worker behavior."""

from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import IntegrityError

from app.models import DiscordConfig, MatchAnalysis, RiotAccount, User, UserSettings, WeeklySummary
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


def test_send_weekly_summaries_saves_summary_and_notifies_discord(app, db):
    fixed_now = datetime(2026, 2, 23, 12, 0, tzinfo=timezone.utc)  # Monday 12:00 UTC

    user = User(email="weekly-summary@test.com")
    user.set_password("pass12345")
    db.session.add(user)
    db.session.flush()

    db.session.add(
        UserSettings(
            user_id=user.id,
            weekly_summary_day="Monday",
            weekly_summary_time="12:00",
            notifications_enabled=True,
        )
    )
    db.session.add(
        DiscordConfig(
            user_id=user.id,
            channel_id="123456789012345678",
            guild_id="987654321098765432",
            is_active=True,
        )
    )
    db.session.add(
        MatchAnalysis(
            user_id=user.id,
            match_id="NA1_weekly_1",
            champion="Ahri",
            win=True,
            kills=8,
            deaths=2,
            assists=9,
            kda=8.5,
            gold_earned=13000,
            gold_per_min=420.0,
            total_damage=25000,
            damage_per_min=760.0,
            vision_score=27,
            cs_total=195,
            game_duration=30.0,
            recommendations=[],
            analyzed_at=fixed_now - timedelta(days=1),
        )
    )
    db.session.commit()

    summary_payload = {
        "total_games": 1,
        "wins": 1,
        "avg_kda": 8.5,
        "avg_gold_per_min": 420.0,
        "avg_damage_per_min": 760.0,
        "summary_text": "Weekly summary text",
    }

    with patch("worker.jobs.datetime") as mock_datetime, patch(
        "app.analysis.engine.generate_weekly_summary",
        return_value=summary_payload,
    ) as mock_generate, patch("app.analysis.discord_notifier.send_message") as mock_send:
        mock_datetime.now.return_value = fixed_now
        jobs.send_weekly_summaries(app)

    summary = WeeklySummary.query.filter_by(user_id=user.id).one()
    assert summary.total_games == 1
    assert summary.wins == 1
    assert summary.avg_kda == 8.5
    assert summary.avg_gold_per_min == 420.0
    assert summary.avg_damage_per_min == 760.0
    assert summary.summary_text == "Weekly summary text"

    called_payload = mock_generate.call_args[0][0]
    assert len(called_payload) == 1
    assert called_payload[0]["win"] is True
    assert called_payload[0]["kda"] == 8.5

    mock_send.assert_called_once_with("123456789012345678", "Weekly summary text")
