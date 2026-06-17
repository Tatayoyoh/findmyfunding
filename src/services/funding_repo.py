"""Repository for funding programs CRUD operations."""

import json

from src.database import get_db
from src.models import FundingProgram, SourceLink


def _row_to_program(row) -> FundingProgram:
    """Convert a database row to a FundingProgram model."""
    source_urls_raw = json.loads(row["source_urls"] or "[]")
    source_urls = [SourceLink(**s) if isinstance(s, dict) else SourceLink(url=s) for s in source_urls_raw]

    def _j(col: str) -> list:
        try:
            return json.loads(row[col] or "[]")
        except (KeyError, IndexError):
            return []

    return FundingProgram(
        id=row["id"],
        category=row["category"],
        name=row["name"],
        project_types=row["project_types"] or "",
        selection_criteria=row["selection_criteria"] or "",
        permanent=bool(row["permanent"]),
        start_submission_date=row["start_submission_date"],
        end_submission_date=row["end_submission_date"],
        pdp_axes=row["pdp_axes"] or "",
        comments=row["comments"] or "",
        source_urls=source_urls,
        min_amount_eur=row["min_amount_eur"],
        max_amount_eur=row["max_amount_eur"],
        cofinancing_pct=row["cofinancing_pct"],
        eligible_structures=_j("eligible_structures"),
        eligible_themes=_j("eligible_themes"),
        application_type=row["application_type"],
        next_deadline=row["next_deadline"],
        summary=(row["summary"] or "") if "summary" in row.keys() else "",
        eligibility_criteria=_j("eligibility_criteria"),
        fundable_axes=_j("fundable_axes"),
        relevant_links=_j("relevant_links"),
        pdf_documents=_j("pdf_documents"),
        tags=_j("tags"),
        last_scraped_at=row["last_scraped_at"],
        last_updated_at=row["last_updated_at"],
        created_at=row["created_at"],
    )


async def get_all() -> list[FundingProgram]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM funding_programs ORDER BY category, name"
        )
        rows = await cursor.fetchall()
        return [_row_to_program(row) for row in rows]
    finally:
        await db.close()


async def get_by_id(program_id: int) -> FundingProgram | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM funding_programs WHERE id = ?", (program_id,)
        )
        row = await cursor.fetchone()
        return _row_to_program(row) if row else None
    finally:
        await db.close()


async def get_categories() -> list[str]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT DISTINCT category FROM funding_programs ORDER BY category"
        )
        rows = await cursor.fetchall()
        return [row["category"] for row in rows]
    finally:
        await db.close()


async def get_all_suggestions() -> dict[str, list[str]]:
    """Return distinct values for eligible_structures and eligible_themes."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT eligible_structures, eligible_themes FROM funding_programs"
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    structures: set[str] = set()
    themes: set[str] = set()
    for row in rows:
        for s in json.loads(row["eligible_structures"] or "[]"):
            if s.strip():
                structures.add(s.strip())
        for t in json.loads(row["eligible_themes"] or "[]"):
            if t.strip():
                themes.add(t.strip())

    return {
        "structures": sorted(structures),
        "themes": sorted(themes),
    }


async def count() -> int:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT COUNT(*) as c FROM funding_programs")
        row = await cursor.fetchone()
        return row["c"]
    finally:
        await db.close()
