import asyncio
import logging
from scheduler.celery_app import celery_app
from scheduler.signal_poll import _poll_and_store

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
def poll_signals(self):
    """
    Celery task entrypoint to poll global APIs.
    Wraps the originally async gathering logic from APScheduler into a robust Celery worker.
    """
    logger.info("Executing Celery Task: Autonomous signal ingestion...")
    try:
        # Run the async extraction routines inside the sync worker execution loop
        asyncio.run(_poll_and_store())
        logger.info("Celery Task Complete: Signals processed and graph updated.")
    except Exception as exc:
        logger.error(f"Signal ingestion failed: {exc}")
        raise self.retry(exc=exc, countdown=60) # Retry in 60s if APIs rate-limit
