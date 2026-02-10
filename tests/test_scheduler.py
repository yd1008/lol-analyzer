"""Tests for background scheduler wiring."""

from worker.scheduler import create_scheduler


def test_refresh_asset_job_next_run_time_is_timezone_aware(app):
    scheduler = create_scheduler(app)
    job = scheduler.get_job("refresh_game_assets")
    assert job is not None
    assert job.next_run_time is not None
    assert job.next_run_time.tzinfo is not None
