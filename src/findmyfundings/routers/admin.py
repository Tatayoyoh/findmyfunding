"""Admin routes for managing sources and imports."""

import json

from fastapi import APIRouter, Request, Form

from findmyfundings.config import settings
from findmyfundings.database import get_db
from findmyfundings.services.excel_import import parse_excel, import_to_db
from findmyfundings.services.scraper import fetch_page_content
from findmyfundings.services.ai_extractor import (
    extract_funding_info,
    update_program_with_extraction,
)
from findmyfundings.services.scheduler import monthly_scrape_job

router = APIRouter(prefix="/admin")


@router.get("/")
async def admin_index(request: Request):
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT ms.*, fp.name as program_name
               FROM monitored_sources ms
               LEFT JOIN funding_programs fp ON ms.funding_program_id = fp.id
               ORDER BY ms.last_checked_at DESC NULLS LAST"""
        )
        sources = await cursor.fetchall()
    finally:
        await db.close()

    return request.app.state.templates.TemplateResponse(
        "admin/sources.html",
        {"request": request, "sources": sources},
    )


@router.post("/import-excel")
async def run_excel_import(request: Request):
    programs = parse_excel(settings.excel_path)
    count = await import_to_db(programs)
    return request.app.state.templates.TemplateResponse(
        "admin/sources.html",
        {
            "request": request,
            "sources": [],
            "message": f"{count} programmes importés avec succès.",
        },
    )


@router.post("/add-source")
async def add_source(
    request: Request,
    url: str = Form(...),
    label: str = Form(""),
):
    """Add a new source URL, scrape it, and extract funding info with AI."""
    # Fetch content
    content = await fetch_page_content(url)
    extraction = None
    if content:
        extraction = await extract_funding_info(content)

    if extraction:
        # Create a new funding program from extraction
        db = await get_db()
        try:
            source_urls = json.dumps(
                [{"url": url, "label": label}], ensure_ascii=False
            )
            cursor = await db.execute(
                """INSERT INTO funding_programs
                   (category, name, project_types, source_urls,
                    min_amount_eur, max_amount_eur, cofinancing_pct,
                    eligible_structures, eligible_themes,
                    application_type, next_deadline)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "Non classifié",
                    label or url[:80],
                    extraction.summary,
                    source_urls,
                    extraction.min_amount_eur,
                    extraction.max_amount_eur,
                    extraction.cofinancing_pct,
                    json.dumps(extraction.eligible_structures, ensure_ascii=False),
                    json.dumps(extraction.eligible_themes, ensure_ascii=False),
                    extraction.application_type,
                    str(extraction.next_deadline) if extraction.next_deadline else None,
                ),
            )
            program_id = cursor.lastrowid

            await db.execute(
                """INSERT OR IGNORE INTO monitored_sources
                   (url, label, funding_program_id)
                   VALUES (?, ?, ?)""",
                (url, label, program_id),
            )
            await db.commit()
        finally:
            await db.close()

        message = f"Source ajoutée et analysée : {extraction.summary[:100]}"
    else:
        message = "Source ajoutée mais impossible d'extraire les informations automatiquement."
        db = await get_db()
        try:
            await db.execute(
                "INSERT OR IGNORE INTO monitored_sources (url, label) VALUES (?, ?)",
                (url, label),
            )
            await db.commit()
        finally:
            await db.close()

    # Redirect back to admin with message
    return request.app.state.templates.TemplateResponse(
        "admin/sources.html",
        {"request": request, "sources": [], "message": message},
    )


@router.post("/run-scrape")
async def run_scrape(request: Request):
    """Trigger a manual scrape of all sources."""
    await monthly_scrape_job()
    return request.app.state.templates.TemplateResponse(
        "admin/sources.html",
        {
            "request": request,
            "sources": [],
            "message": "Scraping terminé.",
        },
    )
