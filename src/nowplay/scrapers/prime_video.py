"""Amazon Prime Video watchlist scraper.

Selectors confirmed 2026-08-04 from a real debug dump (page.html/page.png,
captured from Paul's actual "My Stuff" page — 10 real cards across 4 rails,
page.url was the my-stuff page itself, not a login redirect). Amazon Prime
Video runs its own bot detection (see Requirements & Platform Notes) —
moderate difficulty, between Netflix and Disney+ per the original
assessment.

**Why extraction is section-scoped, not a flat selector:** `/gp/video/
mystuff` renders four rails — "Watchlist – Movies", "Watchlist – TV",
"Purchases and rentals – Movies", "Purchases and rentals – TV" — and all
four use the *identical* `<article data-testid="card">` component. A flat
`TITLE_CARD_SELECTOR` would pull in purchased/rented titles as if they were
on the watchlist. Confirmed via the actual dump: 10 cards total, split 4/4/1/1
across those four rails. extract() below finds each
`<section data-testid="standard-carousel">`, checks its heading
(`[data-testid="carousel-title"]`) starts with "Watchlist", and only pulls
cards from matching sections. The title itself is available directly on a
semantic `data-card-title` attribute — no aria-label parsing or hashed CSS
classes needed, the cleanest of the three new platforms.

WATCHLIST_URL note: Paul's own watchlist URL had a trailing `ref_=...` query
parameter (e.g. `?ref_=atv_hm_hom_c_9zZ8D2_mys`), which he flagged as likely
unstable — Amazon `ref_` params are tracking/attribution tags, not required
for the page itself to load, so it's dropped here in favour of the bare
`gp/video/mystuff` path. (There's also a dedicated `/gp/video/mystuff/
watchlist` URL, visible in the page's own nav markup, which would avoid
needing the section-scoping above — not switched to since it hasn't been
independently confirmed to render the same card markup. Worth trying if this
ever needs revisiting.)

If this stops finding items, Amazon has likely changed the DOM. Fall back to
DISCOVERY mode by setting TITLE_CARD_SELECTOR = None below — that navigates
to WATCHLIST_URL and dumps a fresh page HTML + screenshot to
data/prime_video_debug/ instead of extracting, so selectors can be
re-confirmed against real output rather than re-guessed.

Usage:
    python -m nowplay.cli scrape prime_video
"""
from __future__ import annotations

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from nowplay.db import WatchlistItem
from nowplay.scrapers.base import PlatformScraper, STATE_DIR

DEBUG_DIR = STATE_DIR / "prime_video_debug"

WATCHLIST_URL = "https://www.amazon.co.uk/gp/video/mystuff"

CAROUSEL_SELECTOR = 'section[data-testid="standard-carousel"]'
CAROUSEL_TITLE_SELECTOR = '[data-testid="carousel-title"]'
WATCHLIST_SECTION_PREFIX = "Watchlist"

TITLE_CARD_SELECTOR: str | None = 'article[data-testid="card"]'


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

        # See netflix.py's extract() for why this replaced a fixed sleep
        # (2026-08-04): a correct-looking page can still have 0 cards
        # rendered if the client-side fetch/render hasn't caught up yet.
        # Waits for any card, not scoped to a Watchlist section specifically
        # — the section-filtering below still applies once cards exist.
        try:
            page.wait_for_selector(TITLE_CARD_SELECTOR, timeout=15000)
        except PlaywrightTimeoutError:
            pass

        items: list[WatchlistItem] = []
        seen_titles: set[str] = set()

        for section in page.query_selector_all(CAROUSEL_SELECTOR):
            heading_el = section.query_selector(CAROUSEL_TITLE_SELECTOR)
            heading = heading_el.inner_text().strip() if heading_el else ""
            if not heading.startswith(WATCHLIST_SECTION_PREFIX):
                # e.g. "Purchases and rentals – Movies" — same card markup,
                # not the watchlist. See module docstring.
                continue

            for card in section.query_selector_all(TITLE_CARD_SELECTOR):
                title = card.get_attribute("data-card-title")
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                items.append(
                    WatchlistItem(
                        platform=self.platform,
                        title=title,
                        media_type=card.get_attribute("data-card-entity-type"),
                        raw={
                            "entitlement": card.get_attribute("data-card-entitlement"),
                            "section": heading,
                        },
                    )
                )

        return items
