"""Web scraper for monitoring funding program URLs (inline in source_urls JSON)."""

import hashlib
import json
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from findmyfundings.database import get_db
from findmyfundings.services.funding_repo import get_all


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
                return None
            if "html" not in content_type and "text" not in content_type:
                return None

            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            return text[:15000] if text else None

    except (httpx.HTTPError, Exception):
        return None


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def scrape_all() -> list[dict]:
    """Scrape every URL across every program. Updates per-URL hash + last_checked_at
    in funding_programs.source_urls. Returns one dict per program summarizing
    which had any URL change + the merged changed content."""
    programs = await get_all()
    results: list[dict] = []

    for prog in programs:
        if not prog.source_urls:
            continue

        updated_urls: list[dict] = []
        merged_content: list[str] = []
        any_changed = False
        now = datetime.now(timezone.utc).isoformat()

        for entry in prog.source_urls:
            entry_dict = entry.model_dump(mode="json")
            text = await fetch_page_content(entry.url)
            entry_dict["last_checked_at"] = now

            if text is None:
                # Keep prior hash; mark as not-changed this run
                entry_dict["has_changed"] = False
                updated_urls.append(entry_dict)
                continue

            new_hash = content_hash(text)
            changed = entry.last_hash != new_hash
            entry_dict["last_hash"] = new_hash
            entry_dict["has_changed"] = changed
            updated_urls.append(entry_dict)

            if changed:
                any_changed = True
                merged_content.append(text)

        db = await get_db()
        try:
            await db.execute(
                "UPDATE funding_programs SET source_urls=? WHERE id=?",
                (json.dumps(updated_urls, ensure_ascii=False), prog.id),
            )
            await db.commit()
        finally:
            await db.close()

        results.append({
            "program_id": prog.id,
            "has_changed": any_changed,
            "content": "\n\n".join(merged_content) if any_changed else None,
        })

    return results
