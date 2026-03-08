"""Repository for funding programs CRUD operations."""

import json

from findmyfundings.database import get_db
from findmyfundings.models import FundingProgram, SourceLink


def _row_to_program(row) -> FundingProgram:
    """Convert a database row to a FundingProgram model."""
    source_urls_raw = json.loads(row["source_urls"] or "[]")
    source_urls = [SourceLink(**s) if isinstance(s, dict) else SourceLink(url=s) for s in source_urls_raw]

    eligible_structures = json.loads(row["eligible_structures"] or "[]")
    eligible_themes = json.loads(row["eligible_themes"] or "[]")

    return FundingProgram(
        id=row["id"],
        category=row["category"],
        name=row["name"],
        project_types=row["project_types"] or "",
        selection_criteria=row["selection_criteria"] or "",
        submission_dates=row["submission_dates"] or "",
        pdp_axes=row["pdp_axes"] or "",
        comments=row["comments"] or "",
        source_urls=source_urls,
        min_amount_eur=row["min_amount_eur"],
        max_amount_eur=row["max_amount_eur"],
        cofinancing_pct=row["cofinancing_pct"],
        eligible_structures=eligible_structures,
        eligible_themes=eligible_themes,
        application_type=row["application_type"],
        next_deadline=row["next_deadline"],
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


async def count() -> int:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT COUNT(*) as c FROM funding_programs")
        row = await cursor.fetchone()
        return row["c"]
    finally:
        await db.close()
