"""Netflix "My List" scraper.

IMPORTANT — selectors below are a best-effort starting point based on
publicly documented Netflix DOM patterns (the `.title-card` class and
`data-uia` attributes are widely referenced in existing scraping
write-ups), NOT verified against a live, authenticated my-list page from
this environment. Netflix redesigns their frontend periodically and selectors
drift. On first run:
  1. Run `python -m nowplay.cli login netflix` and log in.
  2. Run `python -m nowplay.cli scrape netflix` and see if it finds items.
  3. If it returns nothing, open netflix.com/browse/my-list, open DevTools,
     inspect a title card, and update SELECTORS below to match what you
     actually see.
"""
from __future__ import annotations

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from nowplay.db import WatchlistItem
from nowplay.scrapers.base import PlatformScraper, STATE_DIR

DEBUG_DIR = STATE_DIR / "netflix_debug"


class NetflixScraper(PlatformScraper):
    platform = "netflix"

    # Netflix's my-list grid renders each title as an anchor with an
    # aria-label containing the title text, inside a `.title-card` container.
    TITLE_CARD_SELECTOR = ".title-card a[aria-label]"

    def watchlist_url(self) -> str:
        return "https://www.netflix.com/browse/my-list"

    def run(self) -> list[WatchlistItem]:
        self.require_saved_session()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.firefox.launch(headless=False)
            context = browser.new_context(storage_state=str(self.state_path))
            page = context.new_page()
            page.goto(self.watchlist_url(), wait_until="networkidle")

            items = self.extract(page)

            if not items:
                # 0 items is ambiguous on its own — could be stale selectors
                # (right page, DOM changed), a stale/expired session (silently
                # redirected to login instead of my-list), a profile not being
                # selected (account-level auth is separate from profile-level
                # auth on Netflix — confirmed 2026-08-04: a session saved right
                # after login but before clicking a profile redirects
                # /browse/my-list to the "Who's watching?" screen instead),
                # or a genuinely empty watchlist. Dump enough to tell those
                # apart without needing a monitor on the box this runs on.
                print(f"netflix: page.url after navigation was {page.url}")
                if "Who's watching" in page.content():
                    print(
                        "netflix: landed on the profile-select screen, not "
                        "my-list. The saved session is authenticated at the "
                        "account level but no profile is selected — redo "
                        "`scripts/login.py netflix` and click your profile "
                        "before pressing Enter to save the session, then "
                        "recopy data/netflix_state.json to wherever this runs."
                    )
                self._dump_debug_artifacts(page)
                print(
                    f"netflix: dumped page HTML and a screenshot to {DEBUG_DIR}/ "
                    f"before closing the browser — check page.url above first "
                    f"(login page vs. my-list means a stale session, not stale "
                    f"selectors), then inspect page.png/page.html if it's the latter."
                )

            browser.close()
        return items

    def _dump_debug_artifacts(self, page) -> None:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / "page.html").write_text(page.content())
        page.screenshot(path=str(DEBUG_DIR / "page.png"), full_page=True)

    def extract(self, page) -> list[WatchlistItem]:
        # Netflix's grid lazy-loads as you scroll; my-list is usually small
        # enough to render fully, but scroll a bit to be safe.
        page.mouse.wheel(0, 3000)

        # Confirmed 2026-08-04: a fixed sleep here isn't reliable. A debug
        # dump showed the *correct* page — right profile (Paul, active),
        # right URL, "My List" tab highlighted — but zero title-cards in the
        # DOM, meaning the client-side fetch/render for list content was
        # still in flight when the old fixed 1.5s wait ran out. Waiting for
        # the actual selector is far more robust than guessing a delay.
        try:
            page.wait_for_selector(self.TITLE_CARD_SELECTOR, timeout=15000)
        except PlaywrightTimeoutError:
            # Never showed up within 15s — could be a genuinely empty list,
            # could be something else. Don't raise; let the 0-items path in
            # run() diagnose it (page.url check, debug dump) instead.
            pass

        cards = page.query_selector_all(self.TITLE_CARD_SELECTOR)
        items: list[WatchlistItem] = []
        seen_titles: set[str] = set()

        for card in cards:
            label = card.get_attribute("aria-label")
            href = card.get_attribute("href") or ""
            if not label:
                continue
            title = label.strip()
            if title in seen_titles:
                continue
            seen_titles.add(title)

            # href is typically /watch/<id> or /title/<id>
            external_id = None
            for part in href.strip("/").split("/"):
                if part.isdigit():
                    external_id = part
                    break

            items.append(
                WatchlistItem(
                    platform=self.platform,
                    title=title,
                    external_id=external_id,
                    media_type=None,  # not reliably exposed on the grid view
                    date_added=None,  # my-list doesn't expose date added in the DOM
                    raw={"href": href, "aria_label": label},
                )
            )

        return items
