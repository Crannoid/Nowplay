"""HBO Max watchlist scraper.

Selectors confirmed 2026-08-04 from a real debug dump (page.html/page.png,
captured from Paul's actual "My Stuff" page — 2 real items in My List,
page.url was the my-stuff page itself, not a login redirect). HBO Max's
UK/EMEA Terms of Use (checked 2026-08-04) explicitly prohibit scraping/data
mining/extracting content and reverse engineering — treat that risk the same
way it's already accepted for Netflix/Disney+ (contract risk, not legal, per
Requirements & Platform Notes).

The my-stuff page renders My List as one rail — a
`<section data-sonic-id="my-stuff-page-rail-my-list">` — followed by a
separate "Recommended for You" rail using the *same* tile component. The
selector below is deliberately scoped to the My List rail's `data-sonic-id`,
not a bare tile selector, so recommendations don't get pulled in as if they
were on the watchlist. Each tile is an `<a data-tile-grid="true">`; the
title renders as the only visible text inside it (a styled-components class
holds it, but those hashes aren't stable enough to depend on — inner_text()
sidesteps that entirely).

If this stops finding items, HBO Max has likely changed the DOM. Fall back to
DISCOVERY mode by setting TITLE_CARD_SELECTOR = None below — that navigates
to WATCHLIST_URL and dumps a fresh page HTML + screenshot to
data/hbo_max_debug/ instead of extracting, so selectors can be re-confirmed
against real output rather than re-guessed.

Usage:
    python -m nowplay.cli scrape hbo_max
"""
from __future__ import annotations

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from nowplay.db import WatchlistItem
from nowplay.scrapers.base import PlatformScraper, STATE_DIR

DEBUG_DIR = STATE_DIR / "hbo_max_debug"

WATCHLIST_URL = "https://play.hbomax.com/my-stuff"

TITLE_CARD_SELECTOR: str | None = (
    'section[data-sonic-id="my-stuff-page-rail-my-list"] a[data-tile-grid="true"]'
)


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

        # See netflix.py's extract() for why this replaced a fixed sleep
        # (2026-08-04): a correct-looking page can still have 0 title-cards
        # if the client-side render hasn't caught up yet.
        try:
            page.wait_for_selector(TITLE_CARD_SELECTOR, timeout=15000)
        except PlaywrightTimeoutError:
            pass

        cards = page.query_selector_all(TITLE_CARD_SELECTOR)
        items: list[WatchlistItem] = []
        seen_titles: set[str] = set()

        for card in cards:
            # aria-label is wrapped in bidi-isolate unicode marks and glues on
            # grid position ("Row 1 of 1, Column 1 of 4") — inner_text() is
            # just the title, since that's the only visible text in the tile.
            title = card.inner_text().strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)

            href = card.get_attribute("href") or ""
            external_id = card.get_attribute("data-sonic-id")

            items.append(
                WatchlistItem(
                    platform=self.platform,
                    title=title,
                    external_id=external_id,
                    raw={"href": href},
                )
            )

        return items
