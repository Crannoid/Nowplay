"""One-off manual login capture.

Opens a real headed Firefox window against the given platform's login page,
waits for you to log in by hand (including any MFA/captcha), then saves the
authenticated session (cookies + local storage) to data/<platform>_state.json
for scrapers to reuse. Re-run this only when the saved session stops working
(e.g. Netflix logs you out) — not on a schedule.

Usage:
    python scripts/login.py netflix
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DATA_DIR = Path(__file__).parent.parent / "data"

LOGIN_URLS = {
    "netflix": "https://www.netflix.com/login",
    "disney_plus": "https://www.disneyplus.com/identity/login",
    # BBC iPlayer's dedicated sign-in URL wasn't confirmed with any
    # confidence (search results were unreliable/spam-adjacent) — this opens
    # the watchlist page itself instead, which will surface BBC's own
    # sign-in prompt if not authenticated. Log in from there by hand.
    "bbc_iplayer": "https://www.bbc.co.uk/iplayer/watchlist",
    "hbo_max": "https://play.hbomax.com/login",
    # Amazon's ap/signin is the standard sign-in gateway used across all
    # amazon.co.uk properties (not Prime-Video-specific), a long-stable URL.
    "prime_video": "https://www.amazon.co.uk/ap/signin",
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in LOGIN_URLS:
        print(f"Usage: python scripts/login.py <{'|'.join(LOGIN_URLS)}>")
        sys.exit(1)

    platform = sys.argv[1]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state_path = DATA_DIR / f"{platform}_state.json"

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URLS[platform])

        print("Log in manually in the opened browser window.")
        input("Once you're fully logged in and see your account, press Enter here to save the session...")

        context.storage_state(path=str(state_path))
        browser.close()

    print(f"Saved session to {state_path}")


if __name__ == "__main__":
    main()
