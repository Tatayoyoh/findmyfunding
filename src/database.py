"""Database access layer.

Backed by libSQL (`libsql` package) so the same code talks to a local SQLite
file in dev and to a remote Turso primary in production. `libsql` is a
synchronous, sqlite3-compatible driver; the thin async adapter below keeps the
existing `await db.execute(...)` call sites working by running every blocking
call on a dedicated single-thread executor (one thread per connection — keeps
the event loop free and satisfies libsql's same-thread requirement).

Unlike sqlite3, libsql rows are plain tuples with no name access, so the
adapter rebuilds dict-like `Row` objects from `cursor.description`.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import libsql

from src.config import settings


class Row:
    """Dict-and-index addressable row, mimicking the slice of `sqlite3.Row` /
    `aiosqlite.Row` the codebase relies on (``row["col"]``, ``row[i]``,
    ``row.keys()``, ``dict(row)``, iteration)."""

    __slots__ = ("_cols", "_idx", "_vals")

    def __init__(self, cols: list[str], vals: tuple):
        self._cols = cols
        self._idx = {c: i for i, c in enumerate(cols)}
        self._vals = vals

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._vals[self._idx[key]]
        return self._vals[key]

    def keys(self) -> list[str]:
        return list(self._cols)

    def __iter__(self):
        return iter(self._vals)

    def __len__(self) -> int:
        return len(self._vals)

    def __repr__(self) -> str:
        return f"Row({dict(zip(self._cols, self._vals))!r})"


class AsyncCursor:
    """Async wrapper over a libsql cursor. ``lastrowid`` / ``rowcount`` are
    captured at execute time (synchronous attributes, no I/O)."""

    def __init__(self, cursor, run, cols, lastrowid, rowcount):
        self._cursor = cursor
        self._run = run
        self._cols = cols
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    async def fetchone(self) -> Row | None:
        row = await self._run(self._cursor.fetchone)
        return Row(self._cols, row) if row is not None else None

    async def fetchall(self) -> list[Row]:
        rows = await self._run(self._cursor.fetchall)
        return [Row(self._cols, r) for r in rows]


class AsyncConnection:
    """Async facade over a synchronous libsql connection. Every DB touch runs on
    a dedicated single-thread executor so the connection is only ever used from
    the thread that created it."""

    # Rows are always `Row`; exposed for drop-in compatibility with code that
    # used to set `db.row_factory = aiosqlite.Row`.
    row_factory = Row

    def __init__(self, conn, executor: ThreadPoolExecutor):
        self._conn = conn
        self._executor = executor

    async def _run(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, lambda: fn(*args))

    async def execute(self, sql: str, params=()) -> AsyncCursor:
        def _do():
            cur = self._conn.execute(sql, params)
            cols = [d[0] for d in cur.description] if cur.description else []
            return cur, cols, cur.lastrowid, cur.rowcount

        cur, cols, lastrowid, rowcount = await self._run(_do)
        return AsyncCursor(cur, self._run, cols, lastrowid, rowcount)

    async def executescript(self, script: str) -> None:
        await self._run(self._conn.executescript, script)

    async def commit(self) -> None:
        await self._run(self._conn.commit)

    async def close(self) -> None:
        await self._run(self._conn.close)
        self._executor.shutdown(wait=False)

SCHEMA = """
CREATE TABLE IF NOT EXISTS funding_programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    project_types TEXT DEFAULT '',
    selection_criteria TEXT DEFAULT '',
    permanent BOOLEAN DEFAULT 0,
    start_submission_date DATE,
    end_submission_date DATE,
    pdp_axes TEXT DEFAULT '',
    comments TEXT DEFAULT '',
    source_urls TEXT DEFAULT '[]',

    -- Structured fields (Firecrawl-extracted, nullable)
    min_amount_eur INTEGER,
    max_amount_eur INTEGER,
    cofinancing_pct INTEGER,
    eligible_structures TEXT DEFAULT '[]',
    eligible_themes TEXT DEFAULT '[]',
    application_type TEXT,
    next_deadline DATE,

    -- New extraction fields (JSON lists)
    summary TEXT DEFAULT '',
    eligibility_criteria TEXT DEFAULT '[]',
    fundable_axes TEXT DEFAULT '[]',
    relevant_links TEXT DEFAULT '[]',
    pdf_documents TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',

    -- Metadata
    last_scraped_at TIMESTAMP,
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    scrape_status TEXT DEFAULT 'pending'
);

-- Version history: one snapshot per edit / scrape
CREATE TABLE IF NOT EXISTS program_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id INTEGER NOT NULL,
    change_type TEXT NOT NULL DEFAULT 'edit',
    snapshot TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (program_id) REFERENCES funding_programs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_program_versions_program
    ON program_versions(program_id, created_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS funding_fts USING fts5(
    name, category, project_types, selection_criteria,
    pdp_axes, comments,
    content='funding_programs',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS funding_ai AFTER INSERT ON funding_programs BEGIN
    INSERT INTO funding_fts(rowid, name, category, project_types,
        selection_criteria, pdp_axes, comments)
    VALUES (new.id, new.name, new.category, new.project_types,
        new.selection_criteria, new.pdp_axes, new.comments);
END;

CREATE TRIGGER IF NOT EXISTS funding_au AFTER UPDATE ON funding_programs BEGIN
    INSERT INTO funding_fts(funding_fts, rowid, name, category, project_types,
        selection_criteria, pdp_axes, comments)
    VALUES ('delete', old.id, old.name, old.category, old.project_types,
        old.selection_criteria, old.pdp_axes, old.comments);
    INSERT INTO funding_fts(rowid, name, category, project_types,
        selection_criteria, pdp_axes, comments)
    VALUES (new.id, new.name, new.category, new.project_types,
        new.selection_criteria, new.pdp_axes, new.comments);
END;

CREATE TRIGGER IF NOT EXISTS funding_ad AFTER DELETE ON funding_programs BEGIN
    INSERT INTO funding_fts(funding_fts, rowid, name, category, project_types,
        selection_criteria, pdp_axes, comments)
    VALUES ('delete', old.id, old.name, old.category, old.project_types,
        old.selection_criteria, old.pdp_axes, old.comments);
END;

"""


async def get_db() -> AsyncConnection:
    executor = ThreadPoolExecutor(max_workers=1)
    loop = asyncio.get_running_loop()

    def _connect():
        if settings.use_remote_db:
            conn = libsql.connect(
                settings.turso_database_url,
                auth_token=settings.turso_auth_token,
            )
        else:
            conn = libsql.connect(str(settings.db_path))
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    conn = await loop.run_in_executor(executor, _connect)
    return AsyncConnection(conn, executor)


async def init_db():
    if not settings.use_remote_db:
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        await db.commit()

        # Migrate: submission_dates → permanent + start/end_submission_date
        cursor = await db.execute(
            "PRAGMA table_info(funding_programs)"
        )
        columns = {row[1] for row in await cursor.fetchall()}
        if "submission_dates" in columns:
            await _migrate_submission_dates(db)

        # Migrate: monitored_sources → funding_programs.source_urls JSON
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='monitored_sources'"
        )
        if await cursor.fetchone():
            await _migrate_monitored_sources(db)

        # Migrate: add Firecrawl extraction columns to existing DBs
        await _migrate_firecrawl_columns(db)

        # Backfill: every program must have a baseline version (current state)
        await _backfill_program_versions(db)
    finally:
        await db.close()


async def _backfill_program_versions(db: AsyncConnection):
    """Snapshot any program that has no version yet, using its own
    last_updated_at as the baseline timestamp."""
    cursor = await db.execute(
        "SELECT id, last_updated_at, created_at FROM funding_programs "
        "WHERE id NOT IN (SELECT DISTINCT program_id FROM program_versions)"
    )
    rows = await cursor.fetchall()
    if not rows:
        return

    from src.services.version_repo import snapshot_program

    for row in rows:
        ts = row["last_updated_at"] or row["created_at"]
        await snapshot_program(row["id"], "edit", created_at=ts)


async def _migrate_firecrawl_columns(db: AsyncConnection):
    """Add new columns introduced by the Firecrawl extraction refactor."""
    cursor = await db.execute("PRAGMA table_info(funding_programs)")
    cols = {row[1] for row in await cursor.fetchall()}

    additions = [
        ("summary", "TEXT DEFAULT ''"),
        ("eligibility_criteria", "TEXT DEFAULT '[]'"),
        ("fundable_axes", "TEXT DEFAULT '[]'"),
        ("relevant_links", "TEXT DEFAULT '[]'"),
        ("pdf_documents", "TEXT DEFAULT '[]'"),
        ("tags", "TEXT DEFAULT '[]'"),
    ]
    for name, definition in additions:
        if name not in cols:
            await db.execute(
                f"ALTER TABLE funding_programs ADD COLUMN {name} {definition}"
            )
    await db.commit()


async def _migrate_monitored_sources(db: AsyncConnection):
    """Fold monitored_sources rows into funding_programs.source_urls JSON entries,
    then drop the monitored_sources table. Orphan sources (no program) are dropped."""
    import json

    cursor = await db.execute(
        "SELECT url, label, funding_program_id, last_content_hash, "
        "last_checked_at, has_changed FROM monitored_sources "
        "WHERE funding_program_id IS NOT NULL"
    )
    rows = await cursor.fetchall()

    by_program: dict[int, list] = {}
    for r in rows:
        by_program.setdefault(r["funding_program_id"], []).append(r)

    for program_id, sources in by_program.items():
        cursor = await db.execute(
            "SELECT source_urls FROM funding_programs WHERE id=?", (program_id,)
        )
        prog_row = await cursor.fetchone()
        if not prog_row:
            continue
        urls = json.loads(prog_row["source_urls"] or "[]")
        # Normalize legacy string entries to dicts
        urls = [
            u if isinstance(u, dict) else {"url": u, "label": ""}
            for u in urls
        ]
        by_url = {u.get("url"): u for u in urls}
        for s in sources:
            existing = by_url.get(s["url"])
            payload = {
                "last_hash": s["last_content_hash"],
                "last_checked_at": s["last_checked_at"],
                "has_changed": bool(s["has_changed"]),
            }
            if existing:
                existing.update(payload)
            else:
                urls.append({
                    "url": s["url"],
                    "label": s["label"] or "",
                    **payload,
                })
        await db.execute(
            "UPDATE funding_programs SET source_urls=? WHERE id=?",
            (json.dumps(urls, ensure_ascii=False), program_id),
        )

    await db.execute("DROP TABLE monitored_sources")
    await db.commit()


async def _migrate_submission_dates(db: AsyncConnection):
    """Migrate submission_dates text to structured date fields."""
    import re

    # Ensure new columns exist
    for col, definition in [
        ("permanent", "BOOLEAN DEFAULT 0"),
        ("start_submission_date", "DATE"),
        ("end_submission_date", "DATE"),
    ]:
        try:
            await db.execute(
                f"ALTER TABLE funding_programs ADD COLUMN {col} {definition}"
            )
        except Exception:
            pass  # Column already exists

    cursor = await db.execute(
        "SELECT id, submission_dates FROM funding_programs"
    )
    rows = await cursor.fetchall()

    date_re = re.compile(r"(\d{2})/(\d{2})/(\d{4})")

    for row in rows:
        prog_id = row[0]
        text = (row[1] or "").strip()

        permanent = False
        start_date = None
        end_date = None

        lower = text.lower()
        if (
            not text
            or lower == "n/a"
            or "n'importe quand" in lower
            or "fil de l'eau" in lower
            or "dépôt de dossiers en ligne" in lower
            or "en ligne" in lower
        ):
            permanent = True
        else:
            dates = date_re.findall(text)
            if dates:
                parsed = []
                for d, m, y in dates:
                    parsed.append(f"{y}-{m}-{d}")
                parsed.sort()
                if len(parsed) >= 2:
                    start_date = parsed[0]
                    end_date = parsed[-1]
                elif len(parsed) == 1:
                    # Single date → use as end date (deadline)
                    end_date = parsed[0]

        await db.execute(
            """UPDATE funding_programs
               SET permanent=?, start_submission_date=?, end_submission_date=?
               WHERE id=?""",
            (permanent, start_date, end_date, prog_id),
        )

    # Drop old column by rebuilding table (SQLite limitation)
    # We keep submission_dates for now and just ignore it — dropping requires
    # recreating the table which is risky. The column is simply unused.
    await db.commit()
