"""BBC iPlayer watchlist scraper — discovery mode.

Added to scope 2026-08-04. No discovery pass has been done yet: no confirmed
watchlist selectors, and BBC's automated-access/scraping terms weren't
directly confirmed either (see Requirements & Platform Notes in Notion —
treat as prohibited by default, same trade-off already accepted for
Netflix/Disney+).

Rather than guess at BBC iPlayer's DOM, this dumps a real page HTML +
screenshot to data/bbc_iplayer_debug/ for inspection first — the same
discovery-before-extraction approach already used for Disney+ before its
selectors were confirmed.

Usage:
    python -m nowplay.cli scrape bbc_iplayer

Then inspect data/bbc_iplayer_debug/page.html (search for a title you have on
your watchlist to see how it's marked up) and page.png, and fill in
TITLE_CARD_SELECTOR below accordingly.
"""
from __future__ import annotations

from nowplay.db import WatchlistItem
from nowplay.scrapers.base import PlatformScraper, STATE_DIR

DEBUG_DIR = STATE_DIR / "bbc_iplayer_debug"

WATCHLIST_URL = "https://www.bbc.co.uk/iplayer/watchlist"

# Not yet confirmed — see module docstring. Set this once a real selector has
# been identified from a debug dump, following the Disney+ precedent.
TITLE_CARD_SELECTOR: str | None = None


class BBCiPlayerScraper(PlatformScraper):
    platform = "bbc_iplayer"

    def watchlist_url(self) -> str:
        return WATCHLIST_URL

    def run(self) -> list[WatchlistItem]:
        self.require_saved_session()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.firefox.launch(headless=False)
            context = browser.new_context(storage_state=str(self.state_path))
            page = context.new_page()
            page.goto(self.watchlist_url(), wait_until="networkidle")

            if TITLE_CARD_SELECTOR is None:
                self._dump_debug_artifacts(page)
                print(
                    f"bbc_iplayer: page.url after navigation was {page.url}\n"
                    f"bbc_iplayer: no confirmed selector yet — dumped page HTML "
                    f"and a screenshot to {DEBUG_DIR}/. Check page.url above "
                    f"first — a sign-in page instead of the watchlist means the "
                    f"saved session isn't valid, not that discovery mode itself "
                    f"has a problem. If it's genuinely the watchlist page, "
                    f"inspect the dump to identify the real title-card "
                    f"selector, then set TITLE_CARD_SELECTOR in "
                    f"scrapers/bbc_iplayer.py."
                )
                browser.close()
                return []

            items = self.extract(page)
            browser.close()
        return items

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
            label = card.get_attribute("aria-label") or card.inner_text().strip()
            href = card.get_attribute("href") or ""
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
                    external_id=None,
                    raw={"href": href, "label": label},
                )
            )

        return items
