"""Nowplay website — read-only watchlist browser.

Phase 3 of the project plan (see Project Plan in Notion): a LAN-only, phone-
browsable page showing everything queued across every scraped platform in
one place. Reads directly from the shared SQLite DB the scraper container
writes to (bind-mounted at the same path — see docker-compose.yml).

This process must never write to the DB. Not just a style preference: see
Hosting & Architecture in Notion, "DB access: direct write, no write API"
(decided 2026-08-06) — the scraper is the DB's sole writer (including TMDB
enrichment), which is the whole reason two containers can share one SQLite
file safely without a write API between them. A second writer here would
reintroduce exactly the race that decision avoided. There is deliberately no
POST/PUT route anywhere in this file.
"""
from __future__ import annotations

import os
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, render_template

from nowplay import db

app = Flask(__name__)

# /app/data matches the scraper's own mount point (see Dockerfile /
# docker-compose.yml) — both containers bind-mount the same host directory
# there. Overridable via env var for running this outside a container (e.g.
# testing against a local copy of the DB).
DB_PATH = Path(os.environ.get("NOWPLAY_DB_PATH", "/app/data/nowplay.db"))

# Display order + labels for platform sections. Matches both wireframes
# (New first, then platforms). A platform with zero active items simply
# doesn't render a section — no special-casing needed for BBC iPlayer/HBO
# Max/Prime Video, which per Project Plan haven't had a scheduled run yet.
PLATFORM_ORDER = ["netflix", "disney_plus", "prime_video", "hbo_max", "bbc_iplayer"]
PLATFORM_LABELS = {
    "netflix": "Netflix",
    "disney_plus": "Disney+",
    "prime_video": "Prime Video",
    "hbo_max": "HBO Max",
    "bbc_iplayer": "BBC iPlayer",
}

# Best-effort "open in <platform>" link. None of the scrapers capture a
# confirmed, working per-title deep link on every platform (Netflix's
# external_id *might* support /watch/<id>, but that pattern was never
# verified against a live session — see netflix.py's own docstring caveats).
# Rather than guess a URL shape that could 404 on Paul's phone, this links
# to each platform's watchlist page itself — confirmed working for all five,
# since it's the same URL each scraper already navigates to.
WATCHLIST_URLS = {
    "netflix": "https://www.netflix.com/browse/my-list",
    "disney_plus": "https://www.disneyplus.com/en-gb/browse/watchlist",
    "prime_video": "https://www.amazon.co.uk/gp/video/mystuff",
    "hbo_max": "https://play.hbomax.com/my-stuff",
    "bbc_iplayer": "https://www.bbc.co.uk/iplayer/watchlist",
}

# "New" bucket — not backed by an explicit schema flag (schema.sql has no
# is_new/seen column, only first_seen_at/last_seen_at). This is a heuristic
# built on first_seen_at, which does exist: anything first scraped within
# this window surfaces in New regardless of platform, matching what both
# wireframes show. Tunable, not validated against any "correct" definition —
# revisit if it feels wrong once real data flows through it.
NEW_WINDOW = timedelta(days=3)


def media_type_label(row) -> str:
    """FILM / SERIES / '' — prefers TMDB's classification over the scraped
    one, since several scrapers leave media_type unset or inconsistent (see
    enrich.py's normalize_media_type docstring; Netflix never sets one)."""
    value = (row["tmdb_media_type"] or row["media_type"] or "").lower()
    if "movie" in value or "film" in value:
        return "FILM"
    if "tv" in value or "series" in value or "show" in value:
        return "SERIES"
    return ""


# Sort order within every section: series before films before anything
# unclassified, alphabetical within each group (Paul's call, 2026-08-06 —
# was straight alphabetical before). type_label is already the FILM/SERIES/
# "" string media_type_label() computes, so this just orders those buckets.
TYPE_SORT_ORDER = {"SERIES": 0, "FILM": 1, "": 2}


def sort_key(card: dict) -> tuple:
    return (TYPE_SORT_ORDER.get(card["type_label"], 2), card["title"])


def to_card(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "platform": row["platform"],
        "platform_label": PLATFORM_LABELS.get(row["platform"], row["platform"]),
        "type_label": media_type_label(row),
        "poster_url": row["poster_url"],
        "overview": row["overview"],
        "release_year": row["release_year"],
        "watchlist_url": WATCHLIST_URLS.get(row["platform"]),
    }


@app.route("/")
def index():
    conn = db.connect(DB_PATH)
    rows = db.list_active_with_metadata(conn)
    conn.close()

    cutoff = (datetime.now(timezone.utc) - NEW_WINDOW).isoformat()

    new_items = sorted(
        (to_card(r) for r in rows if r["first_seen_at"] >= cutoff),
        key=sort_key,
    )

    by_platform: "OrderedDict[str, list[dict]]" = OrderedDict()
    for platform in PLATFORM_ORDER:
        items = sorted(
            (to_card(r) for r in rows if r["platform"] == platform),
            key=sort_key,
        )
        if items:
            by_platform[platform] = items

    # First platform section with items opens expanded by default (matches
    # the wireframe's "New + Netflix open, rest collapsed" pattern) without
    # hardcoding which platform that happens to be.
    first_open_platform = next(iter(by_platform), None)

    return render_template(
        "index.html",
        new_items=new_items,
        by_platform=by_platform,
        first_open_platform=first_open_platform,
        total=len(rows),
    )


if __name__ == "__main__":
    # Dev entrypoint only — the container runs this under waitress instead
    # (see Dockerfile). Flask's built-in server isn't meant for an
    # always-on, unattended process.
    app.run(host="0.0.0.0", port=8080, debug=True)
