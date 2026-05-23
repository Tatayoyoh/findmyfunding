"""Scraping + structured extraction via self-hosted Firecrawl.

Each program is scraped by passing all its source URLs to Firecrawl's /extract
endpoint with a Pydantic schema. The LLM (DeepSeek via OpenAI-compatible API,
configured in the Firecrawl container) returns structured FundingExtraction
data which we persist back to funding_programs.
"""

import json
import logging
from datetime import datetime, timezone

from firecrawl import AsyncFirecrawl

from findmyfundings.config import settings
from findmyfundings.database import get_db
from findmyfundings.models import FundingExtraction
from findmyfundings.services.funding_repo import get_all

logger = logging.getLogger(__name__)


# In-memory state of the current scrape run. Reset at each scrape_all() call.
_state: dict = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "total": 0,
    "done": 0,
    "ok": 0,
    "errors": 0,
    "last_error": None,
    "current_program": None,
}


def get_scrape_state() -> dict:
    return dict(_state)


_running_program_ids: set[int] = set()


def is_program_scraping(program_id: int) -> bool:
    return program_id in _running_program_ids


def start_program_scrape(program_id: int):
    _running_program_ids.add(program_id)


def end_program_scrape(program_id: int):
    _running_program_ids.discard(program_id)


def mark_scrape_starting():
    """Flag a scrape as starting before the background task actually begins,
    so the UI shows the loader immediately on POST response."""
    _state.update({
        "running": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "total": 0,
        "done": 0,
        "ok": 0,
        "errors": 0,
        "last_error": None,
        "current_program": "Initialisation…",
    })


def _reset_state(total: int):
    _state.update({
        "running": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "total": total,
        "done": 0,
        "ok": 0,
        "errors": 0,
        "last_error": None,
        "current_program": None,
    })


def _mark_done(running: bool = False):
    _state["running"] = running
    if not running:
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        _state["current_program"] = None


EXTRACTION_PROMPT = """Tu analyses des pages web décrivant des programmes de financement
pour des structures (associations, ONG, coopératives, entreprises sociales).

Extrais les informations selon le schéma demandé. Sois rigoureux :
- Pour les critères d'éligibilité, liste les conditions formelles d'accès
  (statut, ancienneté, territoire, secteur, taille de structure).
- Pour les axes finançables, liste les actions ou postes de dépenses
  effectivement couverts par le financement.
- Pour les tags, choisis 3 à 8 mots-clés courts qui caractérisent
  le programme (domaine, public cible, type d'action).
- Pour les montants, convertis tout en euros entiers.
- Pour les PDFs, ne liste que les URLs se terminant par .pdf ou pointant
  vers des documents téléchargeables (règlement, dossier de candidature).
- Si une information n'est pas trouvée, laisse null/liste vide. Ne devine pas.
"""


def _client() -> AsyncFirecrawl:
    return AsyncFirecrawl(
        api_url=settings.firecrawl_api_url,
        api_key=settings.firecrawl_api_key or "noauth",
    )


async def _persist_extraction(
    program_id: int,
    extraction: FundingExtraction,
    scraped_at: str,
    source_urls: list[dict],
):
    """Save extraction fields + per-URL last_checked_at back to DB."""
    db = await get_db()
    try:
        await db.execute(
            """UPDATE funding_programs SET
                summary = ?,
                project_types = COALESCE(NULLIF(?, ''), project_types),
                eligibility_criteria = ?,
                eligible_structures = ?,
                eligible_themes = ?,
                fundable_axes = ?,
                relevant_links = ?,
                pdf_documents = ?,
                tags = ?,
                min_amount_eur = ?,
                max_amount_eur = ?,
                cofinancing_pct = ?,
                application_type = ?,
                permanent = ?,
                start_submission_date = ?,
                end_submission_date = ?,
                next_deadline = ?,
                source_urls = ?,
                last_scraped_at = ?,
                last_updated_at = CURRENT_TIMESTAMP,
                scrape_status = 'ok'
            WHERE id = ?""",
            (
                extraction.summary,
                extraction.project_types,
                json.dumps(extraction.eligibility_criteria, ensure_ascii=False),
                json.dumps(extraction.eligible_structures, ensure_ascii=False),
                json.dumps(extraction.eligible_themes, ensure_ascii=False),
                json.dumps(extraction.fundable_axes, ensure_ascii=False),
                json.dumps(extraction.relevant_links, ensure_ascii=False),
                json.dumps(extraction.pdf_documents, ensure_ascii=False),
                json.dumps(extraction.tags, ensure_ascii=False),
                extraction.min_amount_eur,
                extraction.max_amount_eur,
                extraction.cofinancing_pct,
                extraction.application_type,
                extraction.permanent,
                str(extraction.start_submission_date) if extraction.start_submission_date else None,
                str(extraction.end_submission_date) if extraction.end_submission_date else None,
                str(extraction.next_deadline) if extraction.next_deadline else None,
                json.dumps(source_urls, ensure_ascii=False),
                scraped_at,
                program_id,
            ),
        )
        await db.commit()
    finally:
        await db.close()


async def _mark_failed(program_id: int, scraped_at: str, source_urls: list[dict], reason: str):
    db = await get_db()
    try:
        await db.execute(
            """UPDATE funding_programs SET
                source_urls = ?,
                last_scraped_at = ?,
                scrape_status = ?
            WHERE id = ?""",
            (
                json.dumps(source_urls, ensure_ascii=False),
                scraped_at,
                f"error: {reason[:200]}",
                program_id,
            ),
        )
        await db.commit()
    finally:
        await db.close()


async def scrape_one(prog) -> tuple[bool, str | None]:
    """Scrape + persist a single program. Returns (ok, error_message).
    Reusable by scrape_all() and the per-program admin endpoint."""
    urls = [s.url for s in prog.source_urls if s.url.startswith("http")]
    if not urls:
        return False, "Aucune URL exploitable"

    now = datetime.now(timezone.utc).isoformat()
    touched_urls = [
        {**s.model_dump(mode="json"), "last_checked_at": now}
        for s in prog.source_urls
    ]

    try:
        extraction = await scrape_program(prog.id, urls)
        if extraction is None:
            await _mark_failed(prog.id, now, touched_urls, "empty extraction")
            return False, "Extraction vide"
        await _persist_extraction(prog.id, extraction, now, touched_urls)
        return True, None
    except Exception as exc:
        logger.warning(f"Firecrawl extract failed for program {prog.id}: {exc}")
        await _mark_failed(prog.id, now, touched_urls, str(exc))
        return False, str(exc)


async def scrape_program(program_id: int, urls: list[str]) -> FundingExtraction | None:
    """Extract structured data for one program via Firecrawl."""
    if not urls:
        return None
    fc = _client()
    response = await fc.extract(
        urls=urls,
        schema=FundingExtraction.model_json_schema(),
        prompt=EXTRACTION_PROMPT,
    )
    data = getattr(response, "data", None) or getattr(response, "json", None) or {}
    if not data:
        return None
    return FundingExtraction(**data)


async def scrape_all() -> list[dict]:
    """Iterate every program, scrape its URLs via Firecrawl, persist extraction."""
    programs = await get_all()
    scrapeable = [p for p in programs if p.source_urls and any(s.url.startswith("http") for s in p.source_urls)]

    _reset_state(total=len(scrapeable))
    results: list[dict] = []

    try:
        for prog in scrapeable:
            _state["current_program"] = prog.name
            ok, error = await scrape_one(prog)
            if ok:
                _state["ok"] += 1
                results.append({"program_id": prog.id, "status": "ok"})
            else:
                _state["errors"] += 1
                _state["last_error"] = f"{prog.name} : {error}"
                results.append({"program_id": prog.id, "status": "error", "error": error})
            _state["done"] += 1
    finally:
        _mark_done(running=False)

    return results
