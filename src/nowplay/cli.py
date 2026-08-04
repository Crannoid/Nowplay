"""Command-line entry point.

    python -m nowplay.cli scrape netflix   # run the scraper, upsert into sqlite
    python -m nowplay.cli list             # print all active watchlist items
    python -m nowplay.cli list netflix     # filter by platform

For logging in / capturing a session, use scripts/login.py instead — that's a
separate manual, interactive step, not part of the normal CLI flow.
"""
from __future__ import annotations

import sys

from nowplay import db
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


def cmd_scrape(platform: str) -> None:
    if platform not in SCRAPERS:
        print(f"Unknown platform '{platform}'. Available: {', '.join(SCRAPERS)}")
        sys.exit(1)

    scraper = SCRAPERS[platform]()
    items = scraper.run()

    if not items:
        print(
            f"Scraper for '{platform}' found 0 items (see any message above for why — "
            f"e.g. discovery mode, stale selectors, or a genuinely empty watchlist). "
            f"Check scrapers/{platform}.py."
        )
        return

    conn = db.connect()
    db.init_db(conn)
    db.upsert_items(conn, items)
    removed = db.mark_removed_for_platform(conn, platform, {i.title for i in items})
    conn.close()

    print(f"{platform}: upserted {len(items)} items, marked {removed} as removed.")


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
            print("Usage: python -m nowplay.cli scrape <platform>")
            sys.exit(1)
        cmd_scrape(args[0])
    elif command == "list":
        cmd_list(args[0] if args else None)
    else:
        print(f"Unknown command '{command}'.\n\n{__doc__}")
        sys.exit(1)


if __name__ == "__main__":
    main()
