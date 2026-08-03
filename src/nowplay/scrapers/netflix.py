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

from nowplay.db import WatchlistItem
from nowplay.scrapers.base import PlatformScraper


class NetflixScraper(PlatformScraper):
    platform = "netflix"

    # Netflix's my-list grid renders each title as an anchor with an
    # aria-label containing the title text, inside a `.title-card` container.
    TITLE_CARD_SELECTOR = ".title-card a[aria-label]"

    def watchlist_url(self) -> str:
        return "https://www.netflix.com/browse/my-list"

    def extract(self, page) -> list[WatchlistItem]:
        # Netflix's grid lazy-loads as you scroll; my-list is usually small
        # enough to render fully, but scroll a bit to be safe.
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1500)

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
