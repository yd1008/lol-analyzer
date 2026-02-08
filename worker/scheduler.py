"""APScheduler configuration for background job scheduling."""

import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from worker.jobs import check_all_users_matches, send_weekly_summaries

logger = logging.getLogger(__name__)


def create_scheduler(app):
    """Create and configure the APScheduler instance."""
    scheduler = BlockingScheduler()

    check_interval = app.config.get('CHECK_INTERVAL_MINUTES', 5)

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

    return scheduler
