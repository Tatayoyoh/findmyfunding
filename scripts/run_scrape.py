"""CLI script to manually trigger scraping of all monitored sources."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from findmyfundings.database import init_db
from findmyfundings.services.scheduler import monthly_scrape_job


async def run():
    await init_db()
    print("Starting scrape of all monitored sources...")
    await monthly_scrape_job()
    print("Done!")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
