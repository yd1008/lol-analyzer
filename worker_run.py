"""Entry point for the background worker process."""

import logging
from app import create_app
from worker.scheduler import create_scheduler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    app = create_app()
    scheduler = create_scheduler(app)

    logger.info("Starting background worker...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped.")
