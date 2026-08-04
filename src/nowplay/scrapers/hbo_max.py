"""HBO Max watchlist scraper — discovery mode.

Added to scope 2026-08-04. No discovery pass has been done yet: no confirmed
"My List" selectors. HBO Max's UK/EMEA Terms of Use (checked 2026-08-04)
explicitly prohibit scraping/data mining/extracting content and reverse
engineering — treat that risk the same way it's already accepted for
Netflix/Disney+ (contract risk, not legal, per Requirements & Platform
Notes).

Rather than guess at HBO Max's DOM, this dumps a real page HTML + screenshot
to data/hbo_max_debug/ for inspection first — same discovery-before-
extraction approach already used for Disney+ before its selectors were
confirmed.

Usage:
    python -m nowplay.cli scrape hbo_max

Then inspect data/hbo_max_debug/page.html (search for a title you have on
your list to see how it's marked up) and page.png, and fill in
TITLE_CARD_SELECTOR below accordingly.
"""
from __future__ import annotations

from nowplay.db import WatchlistItem
from nowplay.scrapers.base import PlatformScraper, STATE_DIR

DEBUG_DIR = STATE_DIR / "hbo_max_debug"

WATCHLIST_URL = "https://play.hbomax.com/my-stuff"

# Not yet confirmed — see module docstring. Set this once a real selector has
# been identified from a debug dump, following the Disney+ precedent.
TITLE_CARD_SELECTOR: str | None = None


class HBOMaxScraper(PlatformScraper):
    platform = "hbo_max"

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
                    f"hbo_max: page.url after navigation was {page.url}\n"
                    f"hbo_max: no confirmed selector yet — dumped page HTML "
                    f"and a screenshot to {DEBUG_DIR}/. Check page.url above "
                    f"first — a sign-in or profile-select page instead of "
                    f"my-stuff means the saved session isn't valid or isn't "
                    f"scoped to a profile (see the Netflix profile-selection "
                    f"finding in nowplay-project-instructions.md — worth "
                    f"checking for here too), not that discovery mode itself "
                    f"has a problem. If it's genuinely the watchlist page, "
                    f"inspect the dump to identify the real title-card "
                    f"selector, then set TITLE_CARD_SELECTOR in "
                    f"scrapers/hbo_max.py."
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
