"""Disney+ watchlist scraper.

Unlike netflix.py, this is NOT built from confirmed selectors — I have no way
to inspect Disney+'s real, authenticated watchlist DOM from this environment,
and unlike Netflix, there's no well-documented `/browse/my-list`-equivalent
URL or selector pattern to lean on. Guessing and hard-coding a selector here
would just fail silently or scrape the wrong thing with false confidence.

So this runs in two modes:

  DISCOVER (default until real selectors are confirmed): navigates to the
  watchlist by clicking the nav link with accessible name "Watchlist" (robust
  to URL changes, unlike hard-coding a guessed path), then dumps the full
  page HTML and a screenshot to data/disney_plus_debug/ instead of trying to
  extract anything. Look at those files (or send them over) so we can agree
  on real selectors together.

  EXTRACT: once TITLE_CARD_SELECTOR below is filled in from real DOM
  inspection, this behaves like netflix.py.

Usage:
    python -m nowplay.cli scrape disney_plus
"""
from __future__ import annotations

from pathlib import Path

from nowplay.db import WatchlistItem
from nowplay.scrapers.base import PlatformScraper, STATE_DIR

DEBUG_DIR = STATE_DIR / "disney_plus_debug"

# Fill this in once we've inspected data/disney_plus_debug/page.html together.
# Leave as None to stay in discovery mode.
TITLE_CARD_SELECTOR: str | None = None


class DisneyPlusScraper(PlatformScraper):
    platform = "disney_plus"

    def watchlist_url(self) -> str:
        # No confirmed direct URL — start on the homepage and navigate via
        # the nav link instead. This is only used as a fallback landing page.
        return "https://www.disneyplus.com/"

    def run(self) -> list[WatchlistItem]:
        self.require_saved_session()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.firefox.launch(headless=False)
            context = browser.new_context(storage_state=str(self.state_path))
            page = context.new_page()
            page.goto(self.watchlist_url(), wait_until="networkidle")

            self._navigate_to_watchlist(page)

            if TITLE_CARD_SELECTOR is None:
                self._dump_debug_artifacts(page)
                print(
                    f"disney_plus: no confirmed selector yet — dumped page HTML and "
                    f"a screenshot to {DEBUG_DIR}/. Inspect those (or share them) to "
                    f"identify the real title-card selector, then set "
                    f"TITLE_CARD_SELECTOR in scrapers/disney_plus.py."
                )
                browser.close()
                return []

            items = self.extract(page)
            browser.close()
        return items

    def _navigate_to_watchlist(self, page) -> None:
        """Click the nav link/button whose accessible name is 'Watchlist'.

        More robust than a hard-coded URL guess, since we don't have a
        confirmed watchlist URL for Disney+.
        """
        try:
            page.get_by_role("link", name="Watchlist", exact=False).first.click(timeout=10_000)
            page.wait_for_load_state("networkidle")
        except Exception as e:
            print(
                f"disney_plus: couldn't find/click a 'Watchlist' nav link "
                f"({e!r}). Dumping the homepage as-is so we can see what's "
                f"actually on the page."
            )

    def _dump_debug_artifacts(self, page) -> None:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / "page.html").write_text(page.content())
        page.screenshot(path=str(DEBUG_DIR / "page.png"), full_page=True)

    def extract(self, page) -> list[WatchlistItem]:
        assert TITLE_CARD_SELECTOR is not None
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1500)

        cards = page.query_selector_all(TITLE_CARD_SELECTOR)
        items: list[WatchlistItem] = []
        seen_titles: set[str] = set()

        for card in cards:
            label = card.get_attribute("aria-label") or card.inner_text()
            if not label:
                continue
            title = label.strip()
            if title in seen_titles:
                continue
            seen_titles.add(title)
            items.append(
                WatchlistItem(
                    platform=self.platform,
                    title=title,
                    raw={"selector": TITLE_CARD_SELECTOR},
                )
            )

        return items
