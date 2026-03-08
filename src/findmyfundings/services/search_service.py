"""Full-text search service using SQLite FTS5."""

from findmyfundings.database import get_db
from findmyfundings.services.funding_repo import _row_to_program
from findmyfundings.models import FundingProgram


async def search(
    query: str = "",
    categories: list[str] | None = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
) -> list[FundingProgram]:
    """Search funding programs with text search and filters."""
    db = await get_db()
    try:
        conditions = []
        params: list = []

        if query.strip():
            # FTS5 search with French-friendly matching
            fts_query = " OR ".join(
                f'"{word}"*' for word in query.strip().split()
            )
            conditions.append(
                "fp.id IN (SELECT rowid FROM funding_fts WHERE funding_fts MATCH ?)"
            )
            params.append(fts_query)

        if categories:
            placeholders = ",".join("?" * len(categories))
            conditions.append(f"fp.category IN ({placeholders})")
            params.extend(categories)

        if min_amount is not None:
            conditions.append(
                "fp.max_amount_eur IS NOT NULL AND fp.max_amount_eur >= ?"
            )
            params.append(min_amount)

        if max_amount is not None:
            conditions.append(
                "fp.min_amount_eur IS NOT NULL AND fp.min_amount_eur <= ?"
            )
            params.append(max_amount)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
            SELECT fp.* FROM funding_programs fp
            WHERE {where_clause}
            ORDER BY fp.category, fp.name
        """

        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [_row_to_program(row) for row in rows]
    finally:
        await db.close()
