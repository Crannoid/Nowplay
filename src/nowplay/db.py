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
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()


def upsert_items(conn: sqlite3.Connection, items: list[WatchlistItem]) -> None:
    """Insert new items, refresh last_seen_at on existing ones.

    Does NOT mark anything as removed — call mark_removed_for_platform
    separately once a full scrape of a platform completes, so a partial/failed
    scrape can't wipe out items that are still genuinely on the watchlist.
    """
    now = _now()
    for item in items:
        conn.execute(
            """
            INSERT INTO watchlist_items
                (platform, external_id, title, media_type, date_added,
                 raw_json, first_seen_at, last_seen_at, removed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT (platform, title, external_id) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                media_type   = excluded.media_type,
                date_added   = excluded.date_added,
                raw_json     = excluded.raw_json,
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


def list_active(conn: sqlite3.Connection, platform: Optional[str] = None) -> list[sqlite3.Row]:
    if platform:
        return conn.execute(
            "SELECT * FROM watchlist_items WHERE removed_at IS NULL AND platform = ? ORDER BY title",
            (platform,),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM watchlist_items WHERE removed_at IS NULL ORDER BY platform, title"
    ).fetchall()
