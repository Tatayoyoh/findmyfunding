import aiosqlite

from findmyfundings.config import settings

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

    -- Structured fields (AI-extracted, nullable)
    min_amount_eur INTEGER,
    max_amount_eur INTEGER,
    cofinancing_pct INTEGER,
    eligible_structures TEXT DEFAULT '[]',
    eligible_themes TEXT DEFAULT '[]',
    application_type TEXT,
    next_deadline DATE,

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

CREATE TABLE IF NOT EXISTS monitored_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    label TEXT DEFAULT '',
    funding_program_id INTEGER REFERENCES funding_programs(id),
    last_content_hash TEXT,
    last_checked_at TIMESTAMP,
    has_changed BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
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
    finally:
        await db.close()


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
