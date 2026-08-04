"""BBC iPlayer watchlist scraper.

Selectors confirmed 2026-08-04 from a real debug dump (page.html/page.png,
captured from Paul's actual watchlist — 11 real items, page.url was the
watchlist page itself, not a login redirect). BBC's automated-access/
scraping terms weren't directly confirmed (see Requirements & Platform Notes
in Notion — treat as prohibited by default, same trade-off already accepted
for Netflix/Disney+).

The watchlist page (https://www.bbc.co.uk/iplayer/watchlist) renders each
item as an `<a data-bbc-content-label="content-item">` inside a
`.actionable-container`, with the title also available cleanly in a child
`.content-item-root__meta--with-label` div (cleaner than parsing the anchor's
aria-label, which glues the synopsis onto the title: "Title. Description:
..."). The programme ID is recoverable from the href
(`/iplayer/episodes/<id>/<slug>`).

If this stops finding items, BBC has likely changed the DOM. Fall back to
DISCOVERY mode by setting TITLE_CARD_SELECTOR = None below — that navigates
to WATCHLIST_URL and dumps a fresh page HTML + screenshot to
data/bbc_iplayer_debug/ instead of extracting, so selectors can be
re-confirmed against real output rather than re-guessed.

Usage:
    python -m nowplay.cli scrape bbc_iplayer
"""
from __future__ import annotations

from nowplay.db import WatchlistItem
from nowplay.scrapers.base import PlatformScraper, STATE_DIR

DEBUG_DIR = STATE_DIR / "bbc_iplayer_debug"

WATCHLIST_URL = "https://www.bbc.co.uk/iplayer/watchlist"

TITLE_CARD_SELECTOR: str | None = 'a[data-bbc-content-label="content-item"]'


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
            # Prefer the clean title element over aria-label, which glues the
            # synopsis on: "Title. Description: ...".
            title_el = card.query_selector(".content-item-root__meta--with-label")
            title = title_el.inner_text().strip() if title_el else None
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)

            href = card.get_attribute("href") or ""
            # href looks like /iplayer/episodes/<id>/<slug>
            external_id = None
            parts = href.strip("/").split("/")
            if "episodes" in parts:
                idx = parts.index("episodes")
                if idx + 1 < len(parts):
                    external_id = parts[idx + 1]

            items.append(
                WatchlistItem(
                    platform=self.platform,
                    title=title,
                    external_id=external_id,
                    raw={"href": href},
                )
            )

        return items
