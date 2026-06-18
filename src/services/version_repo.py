"""Repository for program version history snapshots.

Each edit or scrape produces one snapshot row (full FundingProgram state as JSON).
Snapshots are taken AFTER the change, so the latest version reflects current DB state.
"""

import json

from src.database import get_db
from src.services.funding_repo import get_by_id


async def snapshot_program(
    program_id: int, change_type: str = "edit", created_at: str | None = None
) -> None:
    """Save a full snapshot of the program's current state.

    `created_at` lets callers backfill a baseline version with the program's own
    timestamp; when None the DB default (CURRENT_TIMESTAMP) is used.
    """
    program = await get_by_id(program_id)
    if not program:
        return
    payload = json.dumps(program.model_dump(mode="json"), ensure_ascii=False)
    db = await get_db()
    try:
        if created_at:
            await db.execute(
                "INSERT INTO program_versions "
                "(program_id, change_type, snapshot, created_at) "
                "VALUES (?, ?, ?, ?)",
                (program_id, change_type, payload, created_at),
            )
        else:
            await db.execute(
                "INSERT INTO program_versions (program_id, change_type, snapshot) "
                "VALUES (?, ?, ?)",
                (program_id, change_type, payload),
            )
        await db.commit()
    finally:
        await db.close()


async def delete_version(program_id: int, version_id: int) -> bool:
    """Delete a single version. Returns True if a row was removed."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM program_versions WHERE id = ? AND program_id = ?",
            (version_id, program_id),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def get_versions(program_id: int) -> list[dict]:
    """List versions (most recent first), without the full snapshot payload."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, change_type, created_at FROM program_versions "
            "WHERE program_id = ? ORDER BY created_at DESC, id DESC",
            (program_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_version(program_id: int, version_id: int) -> dict | None:
    """Return the snapshot dict for a single version, or None."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT snapshot FROM program_versions WHERE id = ? AND program_id = ?",
            (version_id, program_id),
        )
        row = await cursor.fetchone()
        return json.loads(row["snapshot"]) if row else None
    finally:
        await db.close()
