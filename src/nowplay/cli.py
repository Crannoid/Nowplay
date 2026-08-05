"""Command-line entry point.

    python -m nowplay.cli scrape netflix   # run one scraper, upsert into sqlite
    python -m nowplay.cli scrape all       # run every registered scraper in turn;
                                            # one platform erroring doesn't stop the
                                            # rest — see cmd_scrape_all's docstring.
                                            # Also runs TMDB enrichment over newly
                                            # scraped items afterward (decided
                                            # 2026-08-06 — see cmd_scrape_all).
                                            # This is the container's default command.
    python -m nowplay.cli enrich           # run TMDB enrichment on its own, e.g. to
                                            # retry without a full re-scrape
    python -m nowplay.cli list             # print all active watchlist items
    python -m nowplay.cli list netflix     # filter by platform

For logging in / capturing a session, use scripts/login.py instead — that's a
separate manual, interactive step, not part of the normal CLI flow.

For a manual enrichment run with a CSV confidence report (rather than just
the summary this prints), use scripts/tmdb_match_prototype.py instead — it
wraps the same nowplay.enrich logic used here.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone

from nowplay import db, enrich
from nowplay.scrapers.bbc_iplayer import BBCiPlayerScraper
from nowplay.scrapers.disney_plus import DisneyPlusScraper
from nowplay.scrapers.hbo_max import HBOMaxScraper
from nowplay.scrapers.netflix import NetflixScraper
from nowplay.scrapers.prime_video import PrimeVideoScraper

SCRAPERS = {
    "netflix": NetflixScraper,
    "disney_plus": DisneyPlusScraper,
    "bbc_iplayer": BBCiPlayerScraper,
    "hbo_max": HBOMaxScraper,
    "prime_video": PrimeVideoScraper,
}

# Written next to nowplay.db (the same bind-mounted data/ dir, shared with
# the website container — see Hosting & Architecture in Notion) after every
# `scrape all` run, so the outcome survives past the container's own
# ephemeral logs. Not a replacement for real alerting (healthchecks.io,
# per Automation & Scheduling — not yet built), just makes the last run's
# result inspectable without needing `docker logs` on a container that may
# already be gone.
SCRAPE_ALL_LOG_PATH = db.DEFAULT_DB_PATH.parent / "last_scrape_summary.json"


def _scrape_one(platform: str) -> dict:
    """Run one platform's scraper and DB upsert, returning a result dict.

    Deliberately lets any exception from scraper.run() or the DB layer
    propagate to the caller — this is the shared core cmd_scrape() and
    cmd_scrape_all() both build on, so the error-handling *policy* (fail
    loud vs. record-and-continue) lives with the caller, not duplicated here.
    """
    scraper = SCRAPERS[platform]()
    items = scraper.run()

    if not items:
        return {"items": 0, "removed": 0}

    conn = db.connect()
    db.init_db(conn)
    db.upsert_items(conn, items)
    removed = db.mark_removed_for_platform(conn, platform, {i.title for i in items})
    conn.close()
    return {"items": len(items), "removed": removed}


def cmd_scrape(platform: str) -> None:
    if platform not in SCRAPERS:
        print(f"Unknown platform '{platform}'. Available: {', '.join(SCRAPERS)}, all")
        sys.exit(1)

    result = _scrape_one(platform)

    if result["items"] == 0:
        print(
            f"Scraper for '{platform}' found 0 items (see any message above for why — "
            f"e.g. discovery mode, stale selectors, or a genuinely empty watchlist). "
            f"Check scrapers/{platform}.py."
        )
        return

    print(f"{platform}: upserted {result['items']} items, marked {result['removed']} as removed.")


def cmd_scrape_all() -> None:
    """Run every registered scraper in turn.

    Failure isolation is the whole point: one platform's scraper throwing
    (stale selectors erroring instead of just returning 0, a browser launch
    failure, a network blip) is caught, printed with a full traceback, and
    recorded — it does NOT stop the remaining platforms from running. This
    is the scraper container's default command on containerHost, per the
    failure-isolation decision already recorded in Automation & Scheduling:
    Netflix should keep working even if Disney+'s selectors have drifted,
    and vice versa.

    TMDB enrichment (cmd_enrich) runs once at the end, after every platform
    has had a chance to run — not per-platform, since it processes whatever's
    newly unenriched across the whole DB regardless of which platform added
    it. Also failure-isolated from the scraping results above (decided
    2026-08-06, see Hosting & Architecture in Notion).
    """
    started_at = datetime.now(timezone.utc).isoformat()
    summary: dict[str, dict] = {}

    for platform in SCRAPERS:
        print(f"\n=== {platform} ===", flush=True)
        try:
            result = _scrape_one(platform)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any one
            # platform's scraper throwing must not take the rest down.
            traceback.print_exc()
            summary[platform] = {"status": "error", "error": repr(exc)}
            print(f"{platform}: FAILED — {exc!r}")
            continue

        if result["items"] == 0:
            summary[platform] = {"status": "zero_items", "items": 0}
            print(
                f"{platform}: found 0 items (see any message above for why). "
                f"Check scrapers/{platform}.py."
            )
        else:
            summary[platform] = {
                "status": "ok",
                "items": result["items"],
                "removed": result["removed"],
            }
            print(
                f"{platform}: upserted {result['items']} items, "
                f"marked {result['removed']} as removed."
            )

    print("\n=== Enrichment ===", flush=True)
    try:
        enrich_counts = cmd_enrich()
        if enrich_counts is None:
            summary["_enrichment"] = {"status": "skipped_no_api_key"}
        else:
            summary["_enrichment"] = {"status": "ok", **enrich_counts}
    except Exception as exc:  # noqa: BLE001 - same failure-isolation policy as
        # each platform above: enrichment is a secondary step, so a bug or
        # outage here must not erase the scraping results already recorded.
        traceback.print_exc()
        summary["_enrichment"] = {"status": "error", "error": repr(exc)}
        print(f"enrichment: FAILED — {exc!r}")

    print("\n=== Summary ===")
    for platform, info in summary.items():
        print(f"{platform}: {info}")

    SCRAPE_ALL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCRAPE_ALL_LOG_PATH.write_text(
        json.dumps({"started_at": started_at, "results": summary}, indent=2)
    )
    print(f"\nSummary written to {SCRAPE_ALL_LOG_PATH}")

    if any(info["status"] == "error" for info in summary.values()):
        # Non-zero exit on any hard error (not on zero_items, which can
        # legitimately mean an empty watchlist) — lets `docker run` and,
        # later, cron/healthchecks.io tell a failed run from a clean one
        # without parsing log text.
        sys.exit(1)


def cmd_enrich(platform: str | None = None, recheck: bool = False) -> dict | None:
    """Run TMDB metadata enrichment over active watchlist items.

    Called automatically at the end of cmd_scrape_all() (decided 2026-08-06 —
    see Hosting & Architecture in Notion: folding enrichment into the
    scraper's own process is what keeps the scraper the DB's only writer,
    which is why no write API is needed even with the scraper and website as
    separate containers). Also runnable standalone via `python -m
    nowplay.cli enrich`, e.g. to retry without a full re-scrape.

    Non-fatal if TMDB_API_KEY isn't set — prints a message and returns None
    rather than raising, so a container without the key configured yet still
    scrapes successfully, just without enrichment.
    """
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        print(
            "TMDB_API_KEY not set — skipping metadata enrichment. Get a free key at "
            "https://www.themoviedb.org/settings/api and set it as an env var to enable this."
        )
        return None

    conn = db.connect()
    db.init_db(conn)
    counts = enrich.enrich_active_items(conn, api_key, platform=platform, recheck=recheck)
    conn.close()

    print(
        f"Enrichment: checked {counts['checked']} "
        f"(exact {counts['exact']}, fuzzy {counts['fuzzy']}, no_match {counts['no_match']}), "
        f"{counts['failed']} failed request(s) left for next run"
    )
    return counts


def cmd_list(platform: str | None = None) -> None:
    conn = db.connect()
    db.init_db(conn)
    rows = db.list_active(conn, platform)
    conn.close()

    if not rows:
        print("No items in the watchlist yet. Run `scrape` first.")
        return

    for row in rows:
        print(f"[{row['platform']}] {row['title']}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command, *args = sys.argv[1:]

    if command == "scrape":
        if not args:
            print(f"Usage: python -m nowplay.cli scrape <{'|'.join(SCRAPERS)}|all>")
            sys.exit(1)
        if args[0] == "all":
            cmd_scrape_all()
        else:
            cmd_scrape(args[0])
    elif command == "enrich":
        cmd_enrich(args[0] if args else None)
    elif command == "list":
        cmd_list(args[0] if args else None)
    else:
        print(f"Unknown command '{command}'.\n\n{__doc__}")
        sys.exit(1)


if __name__ == "__main__":
    main()
