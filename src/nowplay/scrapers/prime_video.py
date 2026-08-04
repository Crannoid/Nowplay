"""Amazon Prime Video watchlist scraper — discovery mode.

No discovery pass has been done yet: no confirmed "Watchlist" selectors.
Amazon Prime Video runs its own bot detection (see Requirements & Platform
Notes) — moderate difficulty, between Netflix and Disney+ per the original
assessment.

Rather than guess at Prime Video's DOM, this dumps a real page HTML +
screenshot to data/prime_video_debug/ for inspection first — same
discovery-before-extraction approach already used for Disney+ before its
selectors were confirmed.

WATCHLIST_URL note: Paul's own watchlist URL had a trailing `ref_=...` query
parameter (e.g. `?ref_=atv_hm_hom_c_9zZ8D2_mys`), which he flagged as likely
unstable — Amazon `ref_` params are tracking/attribution tags, not required
for the page itself to load, so it's dropped here in favour of the bare
`gp/video/mystuff` path.

Usage:
    python -m nowplay.cli scrape prime_video

Then inspect data/prime_video_debug/page.html (search for a title you have on
your watchlist to see how it's marked up) and page.png, and fill in
TITLE_CARD_SELECTOR below accordingly.
"""
from __future__ import annotations

from nowplay.db import WatchlistItem
from nowplay.scrapers.base import PlatformScraper, STATE_DIR

DEBUG_DIR = STATE_DIR / "prime_video_debug"

WATCHLIST_URL = "https://www.amazon.co.uk/gp/video/mystuff"

# Not yet confirmed — see module docstring. Set this once a real selector has
# been identified from a debug dump, following the Disney+ precedent.
TITLE_CARD_SELECTOR: str | None = None


class PrimeVideoScraper(PlatformScraper):
    platform = "prime_video"

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
                    f"prime_video: page.url after navigation was {page.url}\n"
                    f"prime_video: no confirmed selector yet — dumped page "
                    f"HTML and a screenshot to {DEBUG_DIR}/. Check page.url "
                    f"above first — a sign-in page (amazon.co.uk/ap/signin) "
                    f"instead of the watchlist means the saved session isn't "
                    f"valid, not that discovery mode itself has a problem. If "
                    f"it's genuinely the watchlist page, inspect the dump to "
                    f"identify the real title-card selector, then set "
                    f"TITLE_CARD_SELECTOR in scrapers/prime_video.py."
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
