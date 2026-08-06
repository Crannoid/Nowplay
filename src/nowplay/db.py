"""SQLite access layer for the normalized watchlist table.

Deliberately thin: no ORM. This is a single-user personal tool with a handful
of tables and low write volume — raw sqlite3 + hand-written SQL is easier to
reason about than adding a dependency.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "nowplay.db"


@dataclass
class WatchlistItem:
    platform: str
    title: str
    external_id: Optional[str] = None
    media_type: Optional[str] = None
    date_added: Optional[str] = None
    raw: dict = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL lets the website's read path (browsing UI) and write path (the
    # scraper's POST via the write API) run without one blocking the other.
    # Not needed for the current single-process CLI usage, but this is the
    # same connect() the eventual website process will use once the DB moves
    # to the Pi (see Hosting & Architecture in Notion) — set it now so
    # there's no separate migration step for it later.
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())
    _migrate_add_metadata_columns(conn)
    # Deliberately created here rather than in schema.sql — see the comment
    # next to idx_watchlist_platform/idx_watchlist_removed in schema.sql for
    # why this one index has to come after the migration step above.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_watchlist_metadata ON watchlist_items (title_metadata_id)"
    )
    # Must run after the metadata-columns migration above (it rebuilds the
    # table and needs those columns to already exist to carry them over) —
    # see the function's own docstring for what it fixes and why.
    _migrate_dedupe_and_fix_watchlist_unique(conn)
    conn.commit()


def _migrate_add_metadata_columns(conn: sqlite3.Connection) -> None:
    """Add title_metadata_id/metadata_checked_at to pre-2026-08-05 databases.

    schema.sql's CREATE TABLE IF NOT EXISTS only creates watchlist_items with
    these columns on a brand-new DB — it can't add columns to a table that
    already exists (e.g. the DB already running on Tower/Unraid). SQLite has
    no "ADD COLUMN IF NOT EXISTS", so check PRAGMA table_info first; this
    runs on every init_db() call, so it must stay a no-op once applied.
    """
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(watchlist_items)")}
    if "title_metadata_id" not in existing_columns:
        conn.execute(
            "ALTER TABLE watchlist_items ADD COLUMN title_metadata_id "
            "INTEGER REFERENCES title_metadata(id) ON DELETE SET NULL"
        )
    if "metadata_checked_at" not in existing_columns:
        conn.execute("ALTER TABLE watchlist_items ADD COLUMN metadata_checked_at TEXT")


def _migrate_dedupe_and_fix_watchlist_unique(conn: sqlite3.Connection) -> None:
    """Fix the UNIQUE(platform, title, external_id) bug on an already-deployed DB.

    Found 2026-08-06 against Paul's real containerHost DB: SQL treats two
    NULLs as non-equal for uniqueness, so a re-scrape never conflicted for
    any platform whose external_id came back NULL (Netflix intermittently,
    Prime Video always — see schema.sql's comment on the corrected
    constraint) — every run inserted a fresh duplicate row instead of
    updating the existing one. Confirmed: every Netflix title had exactly
    two rows, both external_id NULL, ~76s apart (two scrapes in the same
    session).

    SQLite can't ALTER a table-level UNIQUE constraint in place — the
    standard fix is rename-recreate-copy-drop, same shape as any other
    SQLite schema migration that changes more than a column. Detects
    whether it's needed by reading the table's own stored CREATE TABLE
    text (PRAGMA table_info doesn't expose table-level UNIQUE constraints,
    only columns), so this is a no-op once applied — safe to run on every
    init_db() call, same as _migrate_add_metadata_columns above.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'watchlist_items'"
    ).fetchone()
    if row is None or "UNIQUE (platform, title, external_id)" not in (row["sql"] or ""):
        return  # already migrated, or a brand-new DB that never had the bug

    # 1. Merge duplicate (platform, title) rows BEFORE rebuilding with the
    #    stricter constraint — otherwise the copy-over INSERT below would
    #    itself violate the new UNIQUE(platform, title).
    dupes = conn.execute(
        """
        SELECT platform, title FROM watchlist_items
        GROUP BY platform, title HAVING COUNT(*) > 1
        """
    ).fetchall()

    for d in dupes:
        rows = conn.execute(
            "SELECT * FROM watchlist_items WHERE platform = ? AND title = ? ORDER BY first_seen_at",
            (d["platform"], d["title"]),
        ).fetchall()
        keep_id = rows[0]["id"]

        # Any duplicate still active (removed_at IS NULL) means the title is
        # genuinely still on the watchlist — prefer that over a stale
        # removed_at from a copy that happened to get marked removed by a
        # different scrape run. Keep whichever enrichment work already
        # exists rather than discarding it by picking an unenriched copy.
        removed_ats = [r["removed_at"] for r in rows]
        merged_removed_at = None if any(r is None for r in removed_ats) else min(
            r for r in removed_ats if r is not None
        )
        merged_metadata_id = next((r["title_metadata_id"] for r in rows if r["title_metadata_id"] is not None), None)
        merged_checked_at = next((r["metadata_checked_at"] for r in rows if r["metadata_checked_at"] is not None), None)
        merged_external_id = next((r["external_id"] for r in rows if r["external_id"]), None)
        merged_date_added = next((r["date_added"] for r in rows if r["date_added"]), None)

        conn.execute(
            """
            UPDATE watchlist_items
            SET first_seen_at = (SELECT MIN(first_seen_at) FROM watchlist_items WHERE platform = ? AND title = ?),
                last_seen_at  = (SELECT MAX(last_seen_at)  FROM watchlist_items WHERE platform = ? AND title = ?),
                removed_at = ?, title_metadata_id = ?, metadata_checked_at = ?,
                external_id = ?, date_added = ?
            WHERE id = ?
            """,
            (
                d["platform"], d["title"], d["platform"], d["title"],
                merged_removed_at, merged_metadata_id, merged_checked_at,
                merged_external_id, merged_date_added, keep_id,
            ),
        )
        other_ids = [r["id"] for r in rows if r["id"] != keep_id]
        conn.executemany("DELETE FROM watchlist_items WHERE id = ?", [(i,) for i in other_ids])

    # 2. Rebuild the table itself with the corrected constraint.
    conn.execute("ALTER TABLE watchlist_items RENAME TO watchlist_items_old")
    conn.execute(
        """
        CREATE TABLE watchlist_items (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            platform            TEXT NOT NULL,
            external_id         TEXT,
            title               TEXT NOT NULL,
            media_type          TEXT,
            date_added          TEXT,
            raw_json            TEXT,
            first_seen_at       TEXT NOT NULL,
            last_seen_at        TEXT NOT NULL,
            removed_at          TEXT,
            title_metadata_id   INTEGER REFERENCES title_metadata(id) ON DELETE SET NULL,
            metadata_checked_at TEXT,
            UNIQUE (platform, title)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO watchlist_items
            (id, platform, external_id, title, media_type, date_added,
             raw_json, first_seen_at, last_seen_at, removed_at,
             title_metadata_id, metadata_checked_at)
        SELECT id, platform, external_id, title, media_type, date_added,
               raw_json, first_seen_at, last_seen_at, removed_at,
               title_metadata_id, metadata_checked_at
        FROM watchlist_items_old
        """
    )
    conn.execute("DROP TABLE watchlist_items_old")

    # Dropping watchlist_items_old also drops every index that was still
    # attached to it (idx_watchlist_platform/idx_watchlist_removed/
    # idx_watchlist_metadata all followed the RENAME, then died with the
    # DROP) — recreate them on the new table. IF NOT EXISTS makes this safe
    # regardless of what init_db() already tried to create before this
    # function ran.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_platform ON watchlist_items (platform)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_removed ON watchlist_items (removed_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_metadata ON watchlist_items (title_metadata_id)")
    conn.commit()


def upsert_items(conn: sqlite3.Connection, items: list[WatchlistItem]) -> None:
    """Insert new items, refresh last_seen_at on existing ones.

    Does NOT mark anything as removed — call mark_removed_for_platform
    separately once a full scrape of a platform completes, so a partial/failed
    scrape can't wipe out items that are still genuinely on the watchlist.

    Conflict target is (platform, title) only — NOT external_id (fixed
    2026-08-06, see schema.sql's comment on the UNIQUE constraint). It used
    to include external_id, but SQL never treats two NULLs as equal for
    uniqueness, so any platform whose external_id came back NULL (Netflix
    sometimes, Prime Video always) never actually conflicted on a re-scrape —
    every run inserted a fresh duplicate row instead of updating the
    existing one. external_id is still stored and refreshed below; it's just
    no longer part of the identity a row is matched on.
    """
    now = _now()
    for item in items:
        conn.execute(
            """
            INSERT INTO watchlist_items
                (platform, external_id, title, media_type, date_added,
                 raw_json, first_seen_at, last_seen_at, removed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT (platform, title) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                media_type   = excluded.media_type,
                date_added   = excluded.date_added,
                raw_json     = excluded.raw_json,
                -- COALESCE, not a flat overwrite: once a real external_id is
                -- captured, don't let a later scrape's NULL (e.g. a
                -- transient DOM miss) clobber it back to unknown.
                external_id  = COALESCE(excluded.external_id, external_id),
                removed_at   = NULL
            """,
            (
                item.platform,
                item.external_id,
                item.title,
                item.media_type,
                item.date_added,
                json.dumps(item.raw),
                now,
                now,
            ),
        )
    conn.commit()


def mark_removed_for_platform(conn: sqlite3.Connection, platform: str, seen_titles: set[str]) -> int:
    """Mark items for `platform` not present in this scrape's `seen_titles` as removed.

    Returns the number of rows marked. Call this after upsert_items, once per
    completed full scrape of a platform.
    """
    now = _now()
    rows = conn.execute(
        "SELECT id, title FROM watchlist_items WHERE platform = ? AND removed_at IS NULL",
        (platform,),
    ).fetchall()
    to_remove = [r["id"] for r in rows if r["title"] not in seen_titles]
    conn.executemany(
        "UPDATE watchlist_items SET removed_at = ? WHERE id = ?",
        [(now, rid) for rid in to_remove],
    )
    conn.commit()
    return len(to_remove)


def get_or_create_title_metadata(
    conn: sqlite3.Connection,
    tmdb_id: int,
    media_type: str,
    title: str,
    release_year: Optional[str],
    poster_url: Optional[str],
    overview: Optional[str],
    match_confidence: str,
) -> int:
    """Return the id of the title_metadata row for this tmdb_id, creating it if needed.

    This is the dedup point: if another platform's watchlist item already
    matched the same TMDB title, its row is reused rather than duplicated —
    the whole reason metadata lives in its own table (see schema.sql). Does
    NOT update an existing row's fields on a repeat match — first fetch wins;
    call this again with fresher data deliberately (e.g. a periodic
    re-enrichment pass) if stale posters/overviews become a real problem.
    """
    conn.execute(
        """
        INSERT INTO title_metadata
            (tmdb_id, media_type, title, release_year, poster_url, overview,
             match_confidence, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (tmdb_id) DO NOTHING
        """,
        (tmdb_id, media_type, title, release_year, poster_url, overview, match_confidence, _now()),
    )
    row = conn.execute(
        "SELECT id FROM title_metadata WHERE tmdb_id = ?", (tmdb_id,)
    ).fetchone()
    conn.commit()
    return row["id"]


def update_item_metadata(
    conn: sqlite3.Connection,
    item_id: int,
    title_metadata_id: Optional[int],
) -> None:
    """Link a watchlist_items row to a title_metadata row (or to none, for a no_match).

    Always stamps metadata_checked_at, including on a no_match (title_metadata_id
    is None) — that's what stops the enrichment step re-querying TMDB for the
    same confirmed-unmatched title on every future scrape.
    """
    conn.execute(
        "UPDATE watchlist_items SET title_metadata_id = ?, metadata_checked_at = ? WHERE id = ?",
        (title_metadata_id, _now(), item_id),
    )
    conn.commit()


def list_active(conn: sqlite3.Connection, platform: Optional[str] = None) -> list[sqlite3.Row]:
    if platform:
        return conn.execute(
            "SELECT * FROM watchlist_items WHERE removed_at IS NULL AND platform = ? ORDER BY title",
            (platform,),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM watchlist_items WHERE removed_at IS NULL ORDER BY platform, title"
    ).fetchall()


# Website read (added 2026-08-06, building Phase 3). Deliberately lives here
# rather than as raw SQL in website/app.py — db.py is already this project's
# one place that knows the schema (see module docstring: "no ORM... easier
# to reason about"), and the website is a second reader of the same tables
# that should share that single source of truth rather than duplicate the
# join logic. Read-only, like every other function in this module used by
# the website — see Hosting & Architecture in Notion ("website is read-only,
# enforced by code discipline") for why nothing here writes.
def list_active_with_metadata(conn: sqlite3.Connection, platform: Optional[str] = None) -> list[sqlite3.Row]:
    """Like list_active(), but LEFT JOINs title_metadata for poster/overview/year.

    LEFT JOIN (not INNER) because enrichment is best-effort — items with no
    TMDB match yet (title_metadata_id IS NULL) or not checked at all should
    still show up, just without a poster/overview. tm.media_type is aliased
    to tmdb_media_type so callers can tell it apart from watchlist_items' own
    (less reliable — see enrich.py's normalize_media_type) media_type column.
    """
    query = """
        SELECT wi.*,
               tm.media_type   AS tmdb_media_type,
               tm.title        AS tmdb_title,
               tm.release_year AS release_year,
               tm.poster_url   AS poster_url,
               tm.overview     AS overview
        FROM watchlist_items wi
        LEFT JOIN title_metadata tm ON wi.title_metadata_id = tm.id
        WHERE wi.removed_at IS NULL
    """
    if platform:
        return conn.execute(
            query + " AND wi.platform = ? ORDER BY wi.title", (platform,)
        ).fetchall()
    return conn.execute(query + " ORDER BY wi.platform, wi.title").fetchall()
