"""One-off: copy the local SQLite DB into the configured Turso (libSQL) remote.

Copies `funding_programs` and `program_versions` row-for-row (preserving ids).
`funding_fts` is intentionally not copied — the AFTER INSERT triggers rebuild it.
Only columns present in BOTH databases are copied, so legacy local columns
(e.g. `submission_dates`) are dropped silently.

Safe by default: aborts if the remote already contains programs. Pass --force to
overwrite (INSERT OR REPLACE).

Usage:
    uv run python scripts/migrate_to_turso.py [--force]
"""

import asyncio
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import libsql

from src.config import settings


def _local_columns(local: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in local.execute(f"PRAGMA table_info({table})")]


async def main(force: bool = False) -> None:
    if not settings.use_remote_db:
        sys.exit("TURSO_DATABASE_URL is not set — nothing to migrate to.")

    local = sqlite3.connect(str(settings.db_path))
    local.row_factory = sqlite3.Row

    from src.database import init_db

    await init_db()  # ensure remote schema exists

    remote = libsql.connect(
        settings.turso_database_url, auth_token=settings.turso_auth_token
    )

    existing = remote.execute("SELECT COUNT(*) FROM funding_programs").fetchone()[0]
    if existing and not force:
        sys.exit(
            f"Remote already has {existing} programs. Re-run with --force to overwrite."
        )
    verb = "INSERT OR REPLACE" if force else "INSERT"

    total = 0
    for table in ("funding_programs", "program_versions"):
        local_cols = _local_columns(local, table)
        remote_cols = {
            r[1] for r in remote.execute(f"PRAGMA table_info({table})").fetchall()
        }
        cols = [c for c in local_cols if c in remote_cols]
        skipped = [c for c in local_cols if c not in remote_cols]
        if skipped:
            print(f"  {table}: skipping local-only columns {skipped}")

        placeholders = ", ".join("?" * len(cols))
        col_list = ", ".join(cols)
        sql = f"{verb} INTO {table} ({col_list}) VALUES ({placeholders})"

        rows = local.execute(f"SELECT {col_list} FROM {table}").fetchall()
        for row in rows:
            remote.execute(sql, tuple(row[c] for c in cols))
        remote.commit()
        print(f"  {table}: copied {len(rows)} rows")
        total += len(rows)

    final = remote.execute("SELECT COUNT(*) FROM funding_programs").fetchone()[0]
    print(f"Done. {total} rows copied. Remote now has {final} programs.")


if __name__ == "__main__":
    asyncio.run(main(force="--force" in sys.argv))
