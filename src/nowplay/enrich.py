"""TMDB metadata enrichment — shared core logic.

Moved out of scripts/tmdb_match_prototype.py on 2026-08-06 so this logic is
part of the installed `nowplay` package and available inside the scraper
container — only src/ is copied into the Docker image, not scripts/ (see
Dockerfile) — which is what's needed now that enrichment is folded into
`python -m nowplay.cli scrape all` (cli.py's cmd_scrape_all) rather than run
as a separate manual step. See Hosting & Architecture in Notion, "DB access:
direct write, no write API" (decided 2026-08-06): folding enrichment into the
scraper's own process is what keeps the scraper the DB's only writer, which
is why a write API isn't needed even though the scraper and website are
separate containers.

scripts/tmdb_match_prototype.py still exists as a thin wrapper around
enrich_active_items() below, for manual runs with CSV output (a confidence
spot-check, same as before) — the core matching/DB-write logic isn't
duplicated between the two.

No new dependency: uses stdlib urllib rather than adding `requests`, per this
project's existing minimal-dependencies stance (see db.py's module docstring).
"""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

from nowplay import db

TMDB_API_BASE = "https://api.themoviedb.org/3"
# w342 is a reasonable thumbnail size for a watchlist grid; TMDB also serves
# w92/w154/w185/w500/w780/original from the same poster_path if a different
# size is wanted later — see https://developer.themoviedb.org/docs/image-basics
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"

# Politeness delay between requests. TMDB's currently documented ceiling is
# roughly 50 req/sec (the old hard per-key rate limit was removed) — nowhere
# near a real constraint for a watchlist of a few hundred titles, but a small
# delay avoids hammering their API. The 429 handling in tmdb_search() below
# is the actual backstop if this isn't enough.
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


def tmdb_search(api_key: str, title: str, media_type: str) -> Optional[list[dict]]:
    """Call TMDB's search endpoint, return the raw `results` list.

    Returns `None` (not `[]`) on a request failure (HTTP error after retries,
    or a network error) — distinct from a genuinely empty results list — so
    the caller can tell "TMDB said no matches" apart from "we couldn't ask
    TMDB" and avoid treating a transient outage as a permanent no_match (see
    enrich_active_items' docstring for why this distinction matters now that
    this runs unattended).

    /search/multi returns movies, TV shows, AND people in one list, each
    tagged with its own 'media_type' field ('movie' | 'tv' | 'person') —
    /search/movie and /search/tv don't need this since the endpoint itself
    already scopes the type. Person results are filtered out here so a title
    that happens to match an actor/director's name doesn't get treated as a
    movie/show match.
    """
    endpoint = {"movie": "search/movie", "tv": "search/tv", "multi": "search/multi"}[media_type]
    params = urllib.parse.urlencode({"api_key": api_key, "query": title, "include_adult": "false"})
    url = f"{TMDB_API_BASE}/{endpoint}?{params}"

    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                results = json.loads(resp.read()).get("results", [])
                if media_type == "multi":
                    results = [r for r in results if r.get("media_type") in ("movie", "tv")]
                return results
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                retry_after = int(exc.headers.get("Retry-After", "2"))
                print(f"  ...rate-limited, waiting {retry_after}s")
                time.sleep(retry_after)
                continue
            print(f"  TMDB error for '{title}': HTTP {exc.code} {exc.reason}")
            return None
        except urllib.error.URLError as exc:
            print(f"  Network error for '{title}': {exc.reason}")
            return None
    print(f"  TMDB rate-limited '{title}' after 3 attempts, giving up for this run")
    return None


def result_title(r: dict) -> str:
    return r.get("title") or r.get("name") or ""


def result_year(r: dict) -> str:
    date = r.get("release_date") or r.get("first_air_date") or ""
    return date[:4] if date else ""


def result_media_type(r: dict, searched_as: str) -> str:
    """TMDB's own movie-vs-series classification for a matched result.

    For /search/movie and /search/tv, the endpoint itself already tells you
    the type (that's what `searched_as` is). For /search/multi, TMDB tags
    each result with its own 'media_type' — useful for titles where our own
    scrapers didn't capture a reliable media_type in the first place
    (Netflix doesn't set one at all; see netflix.py).
    """
    if searched_as in ("movie", "tv"):
        return searched_as
    return r.get("media_type", "")


def best_match(scraped_title: str, results: list[dict]) -> tuple[str, dict | None, list[dict]]:
    """Classify TMDB's results against the scraped title.

    Returns (confidence, chosen_result_or_None, top_candidates_for_review).
    confidence is one of: 'no_match', 'exact', 'fuzzy'. Caller must only pass
    a genuine (possibly empty) results list here, not a `None` from a failed
    tmdb_search() call — see enrich_active_items.

    'exact' means TMDB's top-ranked result's title/name matches the scraped
    title case-insensitively (surrounding whitespace ignored). TMDB already
    ranks by relevance/popularity, so the top result is used as "the pick" in
    both the exact and fuzzy cases below — 'fuzzy' just flags that the label
    doesn't line up exactly, so it should be eyeballed rather than trusted
    automatically. This is deliberately a simple heuristic, not a real
    fuzzy-matching library — good enough to sort matches into "trust this"
    vs. "look at this" for a first pass.
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


def enrich_active_items(
    conn: sqlite3.Connection,
    api_key: str,
    platform: Optional[str] = None,
    recheck: bool = False,
    limit: Optional[int] = None,
    on_row: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Run TMDB enrichment over active watchlist items, writing matches into the DB.

    Returns counts: {"checked", "exact", "fuzzy", "no_match", "failed"}.
    "failed" is a request-level failure (network/HTTP), NOT a genuine
    TMDB no_match — those items are left untouched (metadata_checked_at stays
    NULL) so a future run retries them automatically, without needing
    --recheck. This matters more now than it did as a manually-run,
    human-watched prototype: folded into `scrape all` (see cli.py) and run
    unattended on a schedule, a transient TMDB outage must not silently and
    permanently mark every newly-scraped item as "no match" — see
    tmdb_search()'s docstring for the None-vs-[] distinction this relies on.

    Skips items already checked (metadata_checked_at IS NOT NULL) unless
    recheck=True. Safe to call with zero eligible rows (returns checked=0).
    `on_row`, if given, is called with a dict per processed row (same shape
    scripts/tmdb_match_prototype.py writes to its CSV) — lets a caller build
    a CSV or other report without this function needing to know about CSVs.
    """
    rows = db.list_active(conn, platform)
    if not recheck:
        rows = [r for r in rows if r["metadata_checked_at"] is None]
    if limit:
        rows = rows[:limit]

    counts = {"checked": 0, "exact": 0, "fuzzy": 0, "no_match": 0, "failed": 0}

    for row in rows:
        title = row["title"]
        media_type = normalize_media_type(row["media_type"])

        results = tmdb_search(api_key, title, media_type)
        if results is None:
            # Request failed — leave metadata_checked_at untouched so this
            # item is retried on the next run, not treated as a real no_match.
            counts["failed"] += 1
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        confidence, match, candidates = best_match(title, results)
        counts["checked"] += 1
        counts[confidence] += 1

        poster_path = match.get("poster_path") if match else None
        poster_url = f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None
        overview = (match.get("overview") or None) if match else None

        if match:
            title_metadata_id = db.get_or_create_title_metadata(
                conn,
                tmdb_id=match["id"],
                media_type=result_media_type(match, media_type),
                title=result_title(match),
                release_year=result_year(match) or None,
                poster_url=poster_url,
                overview=overview,
                match_confidence=confidence,
            )
        else:
            title_metadata_id = None
        db.update_item_metadata(conn, row["id"], title_metadata_id)

        if on_row:
            on_row({
                "platform": row["platform"],
                "scraped_title": title,
                "scraped_media_type": row["media_type"] or "",
                "tmdb_media_type_searched": media_type,
                "confidence": confidence,
                "matched_title": result_title(match) if match else "",
                "matched_year": result_year(match) if match else "",
                "tmdb_matched_media_type": result_media_type(match, media_type) if match else "",
                "tmdb_id": match.get("id") if match else "",
                "poster_url": poster_url or "",
                "overview": (overview or "")[:200],
                "top_candidates": format_candidates(candidates),
            })

        time.sleep(REQUEST_DELAY_SECONDS)

    return counts
