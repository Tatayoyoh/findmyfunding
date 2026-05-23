"""APScheduler setup for periodic scraping jobs."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from findmyfundings.services.scraper import scrape_all

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def monthly_scrape_job():
    """Scrape every program via Firecrawl (which also handles LLM extraction)."""
    logger.info("Starting monthly scrape job")
    results = await scrape_all()
    ok = sum(1 for r in results if r["status"] == "ok")
    errors = sum(1 for r in results if r["status"] == "error")
    logger.info(f"Scraped {len(results)} programs: {ok} ok, {errors} errors")


def start_scheduler():
    """Start the scheduler with a monthly job (1st of each month at 3am)."""
    scheduler.add_job(
        monthly_scrape_job,
        trigger=CronTrigger(day=1, hour=3, minute=0),
        id="monthly_scrape",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started: monthly scrape on the 1st at 03:00")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
