import aiosqlite

from src.config import settings

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


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(settings.db_path))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
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
    finally:
        await db.close()


async def _migrate_firecrawl_columns(db: aiosqlite.Connection):
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


async def _migrate_monitored_sources(db: aiosqlite.Connection):
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


async def _migrate_submission_dates(db: aiosqlite.Connection):
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
