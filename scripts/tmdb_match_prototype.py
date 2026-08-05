"""Throwaway TMDB title-matching prototype — read-only, no schema changes.

Purpose: validate match quality before committing to an enrichment schema
(see the 2026-08-05 metadata/UI discussion). This mirrors the project's
existing "discovery mode before extraction mode" pattern already used for
every scraper (see disney_plus.py, bbc_iplayer.py, etc.) — see real output
first, decide the real design once you've seen how well title matching
actually performs against your real watchlist, rather than guessing the
schema shape upfront.

What this does:
  1. Reads every active item out of the existing nowplay.db (read-only — no
     changes to that DB or its schema).
  2. Looks each title up against TMDB's search API (movie/tv/multi endpoint
     depending on the scraped media_type), using a free TMDB API key.
  3. Writes one row per item to a CSV — the scraped title next to what TMDB
     thinks it matched, a confidence label, poster URL, and a short
     description — for you to eyeball.

What this does NOT do: write anything back to nowplay.db, or get wired into
cli.py. It's disposable — once match quality has been reviewed, a real
schema + a real enrichment step (called from cli.py, writing back to the DB)
should replace it.

Setup:
  1. Free TMDB account -> Settings -> API -> request a (v3) API key:
     https://www.themoviedb.org/settings/api
  2. export TMDB_API_KEY=xxxxxxxx        (Windows: set TMDB_API_KEY=xxxxxxxx)
  3. python scripts/tmdb_match_prototype.py
     python scripts/tmdb_match_prototype.py --platform netflix   # optional filter
     python scripts/tmdb_match_prototype.py --limit 20           # optional cap, for a quick spot-check

Output: data/tmdb_match_prototype.csv

No new dependency: uses stdlib urllib rather than adding `requests`, per this
project's existing minimal-dependencies stance (see db.py's module docstring
— "no ORM... easier to reason about than adding a dependency").
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from nowplay import db

TMDB_API_BASE = "https://api.themoviedb.org/3"
# w342 is a reasonable thumbnail size for a watchlist grid; TMDB also serves
# w92/w154/w185/w500/w780/original from the same poster_path if a different
# size is wanted later — see https://developer.themoviedb.org/docs/image-basics
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"

OUTPUT_PATH = db.DEFAULT_DB_PATH.parent / "tmdb_match_prototype.csv"

# Politeness delay between requests. TMDB's currently documented ceiling is
# roughly 50 req/sec (the old hard per-key rate limit was removed) — nowhere
# near a real constraint for a watchlist of a few hundred titles, but a small
# delay avoids hammering their API from a throwaway script. The 429 handling
# in tmdb_search() below is the actual backstop if this isn't enough.
REQUEST_DELAY_SECONDS = 0.25


def normalize_media_type(raw: str | None) -> str:
    """Map this project's scraped media_type values onto a TMDB search endpoint.

    Scraped values are inconsistent across platforms: schema.sql documents
    'movie' | 'series' | 'unknown', but e.g. Prime Video's scraper actually
    stores whatever Amazon's own data-card-entity-type attribute contains
    (seen as 'Movie' in one real dump — not confirmed to always be exactly
    that casing/string for TV). Rather than trust any single raw value
    exactly, normalize loosely and fall back to TMDB's /search/multi (movies
    + TV together) whenever it's ambiguous, rather than guessing wrong and
    searching the wrong endpoint entirely.
    """
    if not raw:
        return "multi"
    value = raw.strip().lower()
    if "movie" in value or "film" in value:
        return "movie"
    if "series" in value or "tv" in value or "show" in value:
        return "tv"
    return "multi"


def tmdb_search(api_key: str, title: str, media_type: str) -> list[dict]:
    """Call TMDB's search endpoint, return the raw `results` list (possibly empty)."""
    endpoint = {"movie": "search/movie", "tv": "search/tv", "multi": "search/multi"}[media_type]
    params = urllib.parse.urlencode({"api_key": api_key, "query": title, "include_adult": "false"})
    url = f"{TMDB_API_BASE}/{endpoint}?{params}"

    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                return json.loads(resp.read()).get("results", [])
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                retry_after = int(exc.headers.get("Retry-After", "2"))
                print(f"  ...rate-limited, waiting {retry_after}s")
                time.sleep(retry_after)
                continue
            print(f"  TMDB error for '{title}': HTTP {exc.code} {exc.reason}")
            return []
        except urllib.error.URLError as exc:
            print(f"  Network error for '{title}': {exc.reason}")
            return []
    return []


def result_title(r: dict) -> str:
    return r.get("title") or r.get("name") or ""


def result_year(r: dict) -> str:
    date = r.get("release_date") or r.get("first_air_date") or ""
    return date[:4] if date else ""


def best_match(scraped_title: str, results: list[dict]) -> tuple[str, dict | None, list[dict]]:
    """Classify TMDB's results against the scraped title.

    Returns (confidence, chosen_result_or_None, top_candidates_for_review).
    confidence is one of: 'no_match', 'exact', 'fuzzy'.

    'exact' means TMDB's top-ranked result's title/name matches the scraped
    title case-insensitively (surrounding whitespace ignored). TMDB already
    ranks by relevance/popularity, so the top result is used as "the pick" in
    both the exact and fuzzy cases below — 'fuzzy' just flags that the label
    doesn't line up exactly, so it should be eyeballed in the CSV rather than
    trusted automatically. This is deliberately a simple heuristic, not a
    real fuzzy-matching library — good enough to sort matches into "trust
    this" vs. "look at this" for a first pass.
    """
    if not results:
        return "no_match", None, []

    top = results[0]
    normalized_scraped = scraped_title.strip().casefold()
    normalized_top = result_title(top).strip().casefold()

    confidence = "exact" if normalized_scraped == normalized_top else "fuzzy"
    return confidence, top, results[:3]


def format_candidates(results: list[dict]) -> str:
    return "; ".join(f"{result_title(r) or '?'} ({result_year(r) or '?'})" for r in results)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", help="Only check items for this platform")
    parser.add_argument("--limit", type=int, help="Only check the first N items (spot-check)")
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
    rows = db.list_active(conn, args.platform)
    conn.close()

    if not rows:
        print("No active watchlist items found. Run a scrape first.")
        return

    if args.limit:
        rows = rows[: args.limit]

    print(f"Checking {len(rows)} item(s) against TMDB...")

    fieldnames = [
        "platform", "scraped_title", "scraped_media_type", "tmdb_media_type_searched",
        "confidence", "matched_title", "matched_year", "tmdb_id", "poster_url",
        "overview", "top_candidates",
    ]
    counts = {"exact": 0, "fuzzy": 0, "no_match": 0}

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i, row in enumerate(rows, start=1):
            title = row["title"]
            media_type = normalize_media_type(row["media_type"])
            print(f"[{i}/{len(rows)}] {row['platform']}: {title} (searching as '{media_type}')")

            results = tmdb_search(api_key, title, media_type)
            confidence, match, candidates = best_match(title, results)
            counts[confidence] += 1

            poster_path = match.get("poster_path") if match else None
            writer.writerow({
                "platform": row["platform"],
                "scraped_title": title,
                "scraped_media_type": row["media_type"] or "",
                "tmdb_media_type_searched": media_type,
                "confidence": confidence,
                "matched_title": result_title(match) if match else "",
                "matched_year": result_year(match) if match else "",
                "tmdb_id": match.get("id") if match else "",
                "poster_url": f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else "",
                "overview": (match.get("overview") or "")[:200] if match else "",
                "top_candidates": format_candidates(candidates),
            })

            time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\nDone. Wrote {len(rows)} row(s) to {OUTPUT_PATH}")
    print(f"exact: {counts['exact']}  fuzzy: {counts['fuzzy']}  no_match: {counts['no_match']}")
    if counts["fuzzy"] or counts["no_match"]:
        print(
            "Review the 'fuzzy' and 'no_match' rows in the CSV before deciding "
            "the enrichment schema — that's the whole point of this prototype."
        )


if __name__ == "__main__":
    main()
