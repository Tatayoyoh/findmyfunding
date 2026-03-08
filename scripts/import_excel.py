"""CLI script to import the Excel cartography into the database."""

import asyncio
import sys
from pathlib import Path

# Add src to path for direct execution
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from findmyfundings.config import settings
from findmyfundings.database import init_db
from findmyfundings.services.excel_import import parse_excel, import_to_db


async def run():
    print(f"Initializing database at {settings.database_path}...")
    await init_db()

    print(f"Parsing Excel file: {settings.excel_path}...")
    programs = parse_excel(settings.excel_path)
    print(f"Found {len(programs)} programs")

    for p in programs[:5]:
        links = len(p["source_urls"])
        print(f"  - [{p['category'][:30]}] {p['name'][:50]} ({links} links)")
    if len(programs) > 5:
        print(f"  ... and {len(programs) - 5} more")

    print("Importing to database...")
    count = await import_to_db(programs)
    print(f"Done! {count} programs imported.")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
