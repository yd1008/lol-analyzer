"""APScheduler configuration for background job scheduling."""

import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from worker.jobs import check_all_users_matches, send_weekly_summaries, refresh_game_assets

logger = logging.getLogger(__name__)


def create_scheduler(app):
    """Create and configure the APScheduler instance."""
    scheduler = BlockingScheduler()

    check_interval = app.config.get('CHECK_INTERVAL_MINUTES', 5)
    asset_refresh_hours = app.config.get('ASSET_REFRESH_HOURS', 6)

    scheduler.add_job(
        check_all_users_matches,
        'interval',
        minutes=check_interval,
        args=[app],
        id='check_matches',
        name='Check all users for new matches',
        replace_existing=True,
    )

    scheduler.add_job(
        send_weekly_summaries,
        'interval',
        hours=1,
        args=[app],
        id='weekly_summaries',
        name='Send weekly summaries',
        replace_existing=True,
    )

    scheduler.add_job(
        refresh_game_assets,
        'interval',
        hours=asset_refresh_hours,
        args=[app],
        id='refresh_game_assets',
        name='Refresh game assets cache',
        replace_existing=True,
        next_run_time=datetime.utcnow(),
    )

    return scheduler
