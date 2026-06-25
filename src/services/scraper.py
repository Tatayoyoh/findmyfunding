"""Scraping + structured extraction — lightweight in-process pipeline.

No external service (replaces the self-hosted Firecrawl stack). Per program:
  1. Fetch each source URL (Scrapling stealthy HTTP, httpx fallback).
  2. HTML -> clean text via trafilatura ; PDF -> markdown via pymupdf4llm.
  3. Concatenate sources and extract structured FundingExtraction via DeepSeek
     (OpenAI-compatible API) wrapped by Instructor (schema validation + retry).

Footprint: ~tens of MB, no browser, no Redis/RabbitMQ/Postgres. Suits a 1 GB VPS.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
import instructor
import pymupdf
import pymupdf4llm
import trafilatura
from openai import AsyncOpenAI

from src.config import settings
from src.database import get_db
from src.models import FundingExtraction
from src.services.funding_repo import get_all

logger = logging.getLogger(__name__)

# Per-source character cap, so a single huge page can't blow the LLM context.
MAX_CHARS_PER_SOURCE = 15000
FETCH_TIMEOUT = 30.0
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


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


DEFAULT_EXTRACTION_PROMPT = """Tu analyses des pages web décrivant des programmes de financement
pour des structures (associations, ONG, coopératives, entreprises sociales).

Ton objectif : remplir TOUS les champs du schéma demandé à partir des informations
présentes dans les pages. Exploite la moindre information utile ; ne laisse un champ
vide que si l'information est réellement absente. Renseigne chaque champ :

- name : le titre officiel du programme (pas le nom de l'organisme financeur seul).
- summary : 2-3 phrases claires décrivant l'objet du financement, pour qui et pourquoi.
- project_types : domaine d'application et types de projets éligibles, formulés de façon
  synthétique (un paragraphe court).
- eligibility_criteria : conditions formelles d'accès, un critère par item (statut juridique,
  ancienneté, territoire, secteur, taille de structure, situation, etc.).
- eligible_structures : types de structures pouvant candidater (association, ONG, coopérative,
  SCOP, entreprise sociale, collectivité…). Déduis-les des critères si non listés explicitement.
- eligible_themes : thèmes/domaines couverts (environnement, social, énergie, jeunesse…).
- min_amount_eur / max_amount_eur : montants en euros entiers (convertis k€/M€, retire les
  séparateurs). Si un seul montant ou un forfait est donné, renseigne le champ pertinent.
- cofinancing_pct : taux de co-financement ou de prise en charge exigé, en pourcentage entier.
- application_type : "appel_a_projets" si campagne avec dates, "fil_de_leau" si dépôt continu
  avec instruction au fil de l'eau, "permanent" si dispositif sans échéance. Déduis-le du texte.
- permanent : true s'il n'y a aucune date limite (dépôt permanent / fil de l'eau).
- start_submission_date / end_submission_date : période d'ouverture des candidatures (YYYY-MM-DD).
- next_deadline : prochaine date limite connue (YYYY-MM-DD), même si une seule date est donnée.
- fundable_axes : actions ou postes de dépenses effectivement couverts par le financement.
- relevant_links : URLs utiles citées (FAQ, formulaire en ligne, page contact, guide).
- pdf_documents : uniquement les URLs se terminant par .pdf ou pointant vers des documents
  téléchargeables (règlement, dossier de candidature, annexes).
- tags : 3 à 8 mots-clés courts caractérisant le programme (domaine, public cible, type d'action).

Règles :
- Tu PEUX raisonner et déduire un champ à partir d'indices cohérents du texte
  (ex : déduire eligible_structures des critères, application_type de la présence de dates).
- En revanche n'INVENTE jamais un fait absent : pas de montant, date ou URL imaginaire.
  En cas de doute réel sur une donnée factuelle, laisse null / liste vide.
- Normalise les dates au format YYYY-MM-DD et les montants en euros entiers.
"""


def _prompt_file() -> Path:
    return Path(settings.database_path).parent / "scraping_prompt.txt"


def get_extraction_prompt() -> str:
    """Read the persisted prompt from disk, fallback to default."""
    path = _prompt_file()
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return DEFAULT_EXTRACTION_PROMPT


def set_extraction_prompt(text: str) -> None:
    """Persist prompt to disk. Empty input = revert to default (delete file)."""
    path = _prompt_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = (text or "").strip()
    if not cleaned:
        if path.exists():
            path.unlink()
        return
    path.write_text(cleaned, encoding="utf-8")


def _looks_like_pdf(url: str, content_type: str | None) -> bool:
    return url.lower().split("?")[0].endswith(".pdf") or (
        content_type is not None and "application/pdf" in content_type.lower()
    )


def _html_to_text(html: str) -> str:
    """Main-content extraction (boilerplate stripped) via trafilatura."""
    text = trafilatura.extract(
        html,
        include_links=True,
        include_tables=True,
        favor_recall=True,
    )
    return text or ""


def _pdf_bytes_to_markdown(data: bytes) -> str:
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        return pymupdf4llm.to_markdown(doc, show_progress=False)
    finally:
        doc.close()


def _http_get(url: str):
    """GET a URL impersonating a real browser (curl_cffi TLS fingerprint) for
    anti-bot resilience, falling back to httpx on ANY curl_cffi failure (missing
    lib, blocked fingerprint, reset, timeout...). Returns (content_bytes, text,
    content_type) or raises if both transports fail."""
    try:
        from curl_cffi import requests as creq

        resp = creq.get(
            url, impersonate="chrome", timeout=FETCH_TIMEOUT, allow_redirects=True
        )
        resp.raise_for_status()
        return resp.content, resp.text, resp.headers.get("content-type")
    except Exception as exc:
        logger.debug(f"curl_cffi fetch failed for {url}, falling back to httpx: {exc}")

    resp = httpx.get(
        url, timeout=FETCH_TIMEOUT, follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    return resp.content, resp.text, resp.headers.get("content-type")


def _fetch_one_blocking(url: str) -> str:
    """Fetch a single URL and return cleaned text/markdown. Runs in a thread."""
    try:
        content, text, content_type = _http_get(url)
    except Exception as exc:
        logger.warning(f"Fetch failed for {url}: {exc}")
        return ""

    # PDF (by extension or content-type, including PDFs behind non-.pdf URLs).
    if _looks_like_pdf(url, content_type):
        try:
            return _pdf_bytes_to_markdown(content)[:MAX_CHARS_PER_SOURCE]
        except Exception as exc:
            logger.warning(f"PDF parse failed for {url}: {exc}")
            return ""

    return _html_to_text(text)[:MAX_CHARS_PER_SOURCE]


async def _fetch_sources(urls: list[str]) -> str:
    """Fetch all URLs concurrently (threads) and concatenate labelled blocks."""
    texts = await asyncio.gather(*(asyncio.to_thread(_fetch_one_blocking, u) for u in urls))
    blocks = [f"### Source: {url}\n\n{text}" for url, text in zip(urls, texts) if text.strip()]
    return "\n\n---\n\n".join(blocks)


def _extractor():
    """Instructor-wrapped DeepSeek client (JSON mode for OpenAI-compatible API)."""
    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
    return instructor.from_openai(client, mode=instructor.Mode.JSON)


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
        from src.services.version_repo import snapshot_program
        await snapshot_program(prog.id, "scrape")
        return True, None
    except Exception as exc:
        logger.warning(f"Extraction failed for program {prog.id}: {exc}")
        await _mark_failed(prog.id, now, touched_urls, str(exc))
        return False, str(exc)


async def scrape_program(program_id: int, urls: list[str]) -> FundingExtraction | None:
    """Fetch a program's URLs, then extract structured data via DeepSeek."""
    if not urls:
        return None

    content = await _fetch_sources(urls)
    if not content.strip():
        logger.warning(f"No content fetched for program {program_id} ({urls})")
        return None

    user_message = (
        f"{get_extraction_prompt()}\n\n"
        "Voici le contenu des pages sources à analyser :\n\n"
        f"{content}"
    )
    client = _extractor()
    extraction = await client.chat.completions.create(
        model=settings.deepseek_model,
        response_model=FundingExtraction,
        messages=[{"role": "user", "content": user_message}],
        max_retries=2,
        reasoning_effort=settings.deepseek_reasoning_effort,
        extra_body=settings.deepseek_thinking_extra_body,
    )
    return extraction


async def scrape_all() -> list[dict]:
    """Iterate every program, fetch its URLs, extract via DeepSeek, persist."""
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
