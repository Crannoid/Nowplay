"""Shared contract for per-platform scrapers.

Every scraper: loads a saved Playwright storageState (see scripts/login.py),
launches Firefox headed, navigates to the platform's watchlist page, and
returns a list of WatchlistItem. No scraper should attempt to automate login
— see project instructions doc for why (repeated automated logins are more
likely to trigger MFA/bot flags than a reused authenticated session).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from playwright.sync_api import sync_playwright

from nowplay.db import WatchlistItem

STATE_DIR = Path(__file__).parent.parent.parent.parent / "data"


class PlatformScraper(ABC):
    platform: str  # e.g. "netflix" — must match the `platform` column values used elsewhere

    @property
    def state_path(self) -> Path:
        return STATE_DIR / f"{self.platform}_state.json"

    @abstractmethod
    def watchlist_url(self) -> str:
        ...

    @abstractmethod
    def extract(self, page) -> list[WatchlistItem]:
        """Given a Playwright page already on the watchlist URL, return items."""
        ...

    def require_saved_session(self) -> None:
        if not self.state_path.exists():
            raise RuntimeError(
                f"No saved session for '{self.platform}' at {self.state_path}. "
                f"Run `python -m nowplay.cli login {self.platform}` first."
            )

    def run(self) -> list[WatchlistItem]:
        self.require_saved_session()
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=False)
            context = browser.new_context(storage_state=str(self.state_path))
            page = context.new_page()
            page.goto(self.watchlist_url(), wait_until="networkidle")
            items = self.extract(page)
            browser.close()
        return items
