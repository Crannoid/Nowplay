"""Manual TMDB enrichment run with a CSV confidence report.

The core matching/DB-write logic now lives in src/nowplay/enrich.py (moved
2026-08-06 so it's available inside the scraper container, where it's called
automatically at the end of `python -m nowplay.cli scrape all` — see
cmd_scrape_all in cli.py and Hosting & Architecture in Notion). This script
is a thin wrapper around that same code for a manual, human-watched run: same
skip-already-checked / --recheck behaviour, plus writes a CSV so a confidence
spot-check is always possible after the fact, same as when this started as a
read-only prototype.

Setup:
  1. Free TMDB account -> Settings -> API -> request a (v3) API key:
     https://www.themoviedb.org/settings/api
  2. export TMDB_API_KEY=xxxxxxxx        (Windows: set TMDB_API_KEY=xxxxxxxx)
  3. python scripts/tmdb_match_prototype.py
     python scripts/tmdb_match_prototype.py --platform netflix   # optional filter
     python scripts/tmdb_match_prototype.py --limit 20           # optional cap, for a quick spot-check
     python scripts/tmdb_match_prototype.py --recheck             # re-query already-checked items too

Output: data/tmdb_match_prototype.csv

Equivalent automatic behaviour without a CSV: `python -m nowplay.cli enrich`.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

from nowplay import db, enrich

OUTPUT_PATH = db.DEFAULT_DB_PATH.parent / "tmdb_match_prototype.csv"

FIELDNAMES = [
    "platform", "scraped_title", "scraped_media_type", "tmdb_media_type_searched",
    "confidence", "matched_title", "matched_year", "tmdb_matched_media_type",
    "tmdb_id", "poster_url", "overview", "top_candidates",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", help="Only check items for this platform")
    parser.add_argument("--limit", type=int, help="Only check the first N items (spot-check)")
    parser.add_argument(
        "--recheck",
        action="store_true",
        help="Re-query TMDB for items already checked (metadata_checked_at IS NOT NULL), "
        "e.g. to retry old no_match items",
    )
    args = parser.parse_args()

    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        print(
            "TMDB_API_KEY not set. Get a free key at "
            "https://www.themoviedb.org/settings/api then "
            "`export TMDB_API_KEY=...` before running this."
        )
        sys.exit(1)

    conn = db.connect()
    db.init_db(conn)

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        counts = enrich.enrich_active_items(
            conn,
            api_key,
            platform=args.platform,
            recheck=args.recheck,
            limit=args.limit,
            on_row=writer.writerow,
        )

    conn.close()

    if counts["checked"] == 0 and counts["failed"] == 0:
        print(
            "Nothing to check — no active watchlist items, or all are already "
            "enriched (pass --recheck to force a re-check)."
        )
        return

    print(f"\nDone. Wrote {counts['checked']} row(s) to {OUTPUT_PATH} and to nowplay.db.")
    print(
        f"exact: {counts['exact']}  fuzzy: {counts['fuzzy']}  no_match: {counts['no_match']}  "
        f"failed (left for next run): {counts['failed']}"
    )
    if counts["fuzzy"]:
        print(
            "Review the 'fuzzy' rows in the CSV — those matches were written to the DB "
            "but TMDB's top result didn't match the scraped title exactly, so it's worth "
            "a spot-check that the right film/show was picked."
        )


if __name__ == "__main__":
    main()
