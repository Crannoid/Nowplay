"""Disney+ watchlist scraper.

Selectors below were confirmed against a real debug dump (page.html/page.png,
captured 2026-08-03 from Paul's actual watchlist) — not guessed. Disney+'s
watchlist grid uses `data-testid="set-item"` anchors, each with an
aria-label like "Tron: Ares Select for details on this title." (sometimes
with a badge like "Disney+ Original" or "Hulu Original Series" inserted
before "Select for details..." — see KNOWN_BADGES).

If this stops finding items, Disney+ has likely changed the DOM. Fall back to
DISCOVER mode by setting TITLE_CARD_SELECTOR = None below — that navigates to
WATCHLIST_URL and dumps a fresh page HTML + screenshot to
data/disney_plus_debug/ instead of extracting, so selectors can be
re-confirmed against real output rather than re-guessed.

Usage:
    python -m nowplay.cli scrape disney_plus
"""
from __future__ import annotations

from pathlib import Path

from nowplay.db import WatchlistItem
from nowplay.scrapers.base import PlatformScraper, STATE_DIR

DEBUG_DIR = STATE_DIR / "disney_plus_debug"

# Confirmed directly from Paul's session (2026-08-03) after the earlier
# click-based nav ("find and click the Watchlist link") turned out to be
# unreliable — likely SPA hydration/timing flakiness. Direct navigation is
# simpler and doesn't depend on the nav bar having finished rendering.
#
# NOTE: includes an "en-gb" locale segment, specific to Paul's account
# region. If this is ever reused on a different-region account, or Disney+
# changes locale routing, this may need updating.
WATCHLIST_URL = "https://www.disneyplus.com/en-gb/browse/watchlist"

TITLE_CARD_SELECTOR: str | None = 'a[data-testid="set-item"]'

SELECT_SUFFIX = " Select for details on this title."

# Badge text Disney+ appends to a title's aria-label before SELECT_SUFFIX,
# observed directly in Paul's watchlist debug dump. Not guaranteed
# exhaustive — other content types (ESPN, National Geographic, Star Wars
# Originals, etc.) weren't present in that watchlist and may use badges not
# listed here, which would show up as extra trailing text on the title until
# added.
KNOWN_BADGES = [
    "Hulu Original Series",
    "Disney+ Original",
]


class DisneyPlusScraper(PlatformScraper):
    platform = "disney_plus"

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
                    f"disney_plus: no confirmed selector yet — dumped page HTML and "
                    f"a screenshot to {DEBUG_DIR}/. Inspect those (or share them) to "
                    f"identify the real title-card selector, then set "
                    f"TITLE_CARD_SELECTOR in scrapers/disney_plus.py."
                )
                browser.close()
                return []

            items = self.extract(page)

            if not items:
                # Confirmed selector, but 0 items — same ambiguity we hit with
                # Netflix on Tower (2026-08-04): could be stale selectors, a
                # stale/incomplete session, or a genuinely empty watchlist.
                # Netflix's specific cause there was a session authenticated
                # at the account level but not scoped to a profile, which
                # redirected away from the watchlist page — not confirmed
                # whether Disney+ has the same profile-selection gate, but
                # worth checking page.url below for the same pattern before
                # assuming it's stale selectors.
                print(f"disney_plus: page.url after navigation was {page.url}")
                self._dump_debug_artifacts(page)
                print(
                    f"disney_plus: found 0 items with a confirmed selector — "
                    f"dumped page HTML and a screenshot to {DEBUG_DIR}/. Check "
                    f"page.url above first (a login or profile-select page "
                    f"instead of the watchlist means a stale/incomplete "
                    f"session, not stale selectors), then inspect "
                    f"page.png/page.html if it's genuinely on the watchlist page."
                )

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
            label = card.get_attribute("aria-label")
            href = card.get_attribute("href") or ""
            item_id = card.get_attribute("data-item-id")

            if not label or not label.endswith(SELECT_SUFFIX):
                continue
            title = label[: -len(SELECT_SUFFIX)].strip()

            for badge in KNOWN_BADGES:
                if title.endswith(badge):
                    title = title[: -len(badge)].strip()
                    break

            if not title or title in seen_titles:
                continue
            seen_titles.add(title)

            items.append(
                WatchlistItem(
                    platform=self.platform,
                    title=title,
                    external_id=item_id,
                    raw={"href": href, "aria_label": label},
                )
            )

        return items
