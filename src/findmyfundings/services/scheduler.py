"""APScheduler setup for periodic scraping jobs."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from findmyfundings.services.scraper import scrape_all
from findmyfundings.services.ai_extractor import (
    extract_funding_info,
    update_program_with_extraction,
)

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def monthly_scrape_job():
    """Scrape all sources and run AI extraction on changed ones."""
    logger.info("Starting monthly scrape job")
    results = await scrape_all()

    changed = [r for r in results if r.get("has_changed") and r.get("content")]
    logger.info(f"Scraped {len(results)} sources, {len(changed)} changed")

    for result in changed:
        extraction = await extract_funding_info(result["content"])
        if extraction and result.get("funding_program_id"):
            await update_program_with_extraction(
                result["funding_program_id"], extraction
            )
            logger.info(
                f"Updated program {result['funding_program_id']} with AI extraction"
            )


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
