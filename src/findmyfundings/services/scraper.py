"""Web scraper for monitoring funding source URLs."""

import hashlib
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from findmyfundings.database import get_db


async def fetch_page_content(url: str) -> str | None:
    """Fetch a URL and extract its main text content."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=30.0
        ) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; FindMyFundings/1.0)"
            }
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "pdf" in content_type:
                return None  # Skip PDFs for now
            if "html" not in content_type and "text" not in content_type:
                return None

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove non-content elements
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            # Limit to reasonable size for AI processing
            return text[:15000] if text else None

    except (httpx.HTTPError, Exception):
        return None


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def scrape_source(source_id: int) -> dict:
    """Scrape a single monitored source. Returns status info."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM monitored_sources WHERE id = ?", (source_id,)
        )
        source = await cursor.fetchone()
        if not source:
            return {"status": "error", "message": "Source not found"}

        text = await fetch_page_content(source["url"])
        now = datetime.now(timezone.utc).isoformat()

        if text is None:
            await db.execute(
                "UPDATE monitored_sources SET last_checked_at = ? WHERE id = ?",
                (now, source_id),
            )
            await db.commit()
            return {"status": "skipped", "message": "Could not fetch content"}

        new_hash = content_hash(text)
        has_changed = source["last_content_hash"] != new_hash

        await db.execute(
            """UPDATE monitored_sources
               SET last_content_hash = ?, last_checked_at = ?, has_changed = ?
               WHERE id = ?""",
            (new_hash, now, has_changed, source_id),
        )
        await db.commit()

        return {
            "status": "ok",
            "has_changed": has_changed,
            "content": text if has_changed else None,
            "funding_program_id": source["funding_program_id"],
        }
    finally:
        await db.close()


async def scrape_all() -> list[dict]:
    """Scrape all monitored sources."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id FROM monitored_sources")
        sources = await cursor.fetchall()
    finally:
        await db.close()

    results = []
    for source in sources:
        result = await scrape_source(source["id"])
        results.append(result)
    return results
