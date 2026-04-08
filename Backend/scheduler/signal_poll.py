from __future__ import annotations

import asyncio
import os

from apscheduler.schedulers.background import BackgroundScheduler

from agents.signal_agent import fetch_gdelt, fetch_gnews, fetch_nasa_eonet, fetch_newsapi
from services.local_store import add_audit, purge_archived_signals, replace_active_signals
from services.secret_manager import get_secret

_scheduler: BackgroundScheduler | None = None


async def _poll_sources() -> None:
    news_api_key = get_secret("NEWSAPI_API_KEY")
    gnews_api_key = get_secret("GNEWS_API_KEY")

    batches = []
    for fn in (
        fetch_nasa_eonet,
        fetch_gdelt,
        lambda: fetch_newsapi(news_api_key),
        lambda: fetch_gnews(gnews_api_key),
    ):
        try:
            items = await fn()
            batches.extend(items)
        except Exception as exc:
            add_audit("signal_poll_error", str(exc))

    dedup: dict[str, dict] = {}
    for item in batches:
        sid = str(item.get("id") or "").strip()
        if not sid:
            sid = f"sig_{abs(hash((item.get('source'), item.get('title'), item.get('location'))))}"
            item["id"] = sid
        dedup[sid] = item

    replace_active_signals(list(dedup.values()))
    purged = purge_archived_signals(days=7)
    add_audit("signal_poll_complete", f"active={len(dedup)} purged={purged}")


def _job_wrapper() -> None:
    asyncio.run(_poll_sources())


def start_signal_scheduler() -> None:
    global _scheduler
    if os.getenv("ENABLE_SIGNAL_SCHEDULER", "true").lower() != "true":
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_job_wrapper, "interval", minutes=15, id="signal_poll_15m", replace_existing=True)
    _scheduler.start()
    add_audit("signal_scheduler_started", "15m")
