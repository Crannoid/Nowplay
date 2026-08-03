# Nowplay

Personal tool to pull your streaming watchlists into a local SQLite database,
so you can see them outside each app. Netflix is working end-to-end; Disney+
is in progress. See `nowplay-project-instructions.md` for the full
background, platform-by-platform difficulty assessment, and decisions made
so far.

## Before you use this

Netflix's and Disney+'s Terms of Use both prohibit automated/scripted access
to the service. This is a contract risk, not a legal one — the realistic
downside is account suspension if detected, not legal action. That risk
doesn't go away with any of the mitigations below; it's just reduced. Use
your own judgment about whether that trade-off is acceptable for your
account.

## How it works

- Playwright drives a real, visible (headed) Firefox — not headless Chromium
  — to reduce the most common automation fingerprints.
- You log in manually once (`scripts/login.py`); the authenticated session is
  saved to `data/netflix_state.json` and reused, so the scraper never
  automates the login itself.
- Each scrape upserts into `data/nowplay.db` (SQLite) and marks any items no
  longer on the watchlist as removed (soft delete — history is kept).
- `data/` is gitignored — it holds your auth session and local DB, neither of
  which should ever be committed.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e .
playwright install firefox
```

(Only the venv-creation step needs `python3` explicitly on Debian/Ubuntu, which
doesn't symlink `python` by default — once the venv is active, `python` inside
it works fine, since venvs create that symlink themselves. If you'd rather have
`python` available system-wide, `sudo apt install python-is-python3` does that.)

If `python3 -m venv .venv` fails with "ensurepip is not available", Debian/Ubuntu
ships venv support as a separate package: `sudo apt install python3.12-venv`
(adjust the version to match `python3 --version`). Delete any partially-created
`.venv/` first (`rm -rf .venv`) before retrying.

## First-time login

```bash
python scripts/login.py netflix
python scripts/login.py disney_plus
```

A Firefox window opens to the platform's login page. Log in by hand (this
handles any MFA/captcha thrown at you), then press Enter in the terminal
once you're in. This saves your session to `data/<platform>_state.json`. You
only need to redo this if the saved session stops working (e.g. you get
logged out).

## Scraping

```bash
python -m nowplay.cli scrape netflix
python -m nowplay.cli scrape disney_plus
```

**Disney+ is currently in discovery mode**, not extraction mode — there was
no way to verify Disney+'s watchlist URL or DOM selectors without an
authenticated session, unlike Netflix where documented patterns existed. The
first run navigates to the Watchlist page and dumps the page HTML +
screenshot to `data/disney_plus_debug/` instead of guessing at selectors.
Look at `data/disney_plus_debug/page.html` (search for your watchlist titles
to see how they're marked up) and `page.png`, then fill in
`TITLE_CARD_SELECTOR` in `src/nowplay/scrapers/disney_plus.py` accordingly —
happy to help figure that out together once you've got real output to look at.

## Viewing results

```bash
python -m nowplay.cli list
```

No front end yet by design — query `data/nowplay.db` directly with any
SQLite browser, or use the `list` command above, until the pipeline's proven
reliable enough to be worth building a UI on top of.

## If the scraper finds 0 items

Netflix's DOM selectors in `src/nowplay/scrapers/netflix.py` are a
best-effort starting point, not verified against a live authenticated page —
see the module docstring for how to fix them using DevTools. This is the
expected maintenance cost flagged in the project instructions doc: Netflix
redesigns their frontend periodically and selectors will drift over time.

## Running unattended (e.g. on a home lab box with no monitor)

Headed mode needs a display. Use a virtual one:

```bash
xvfb-run -a python -m nowplay.cli scrape netflix
```

Then schedule via cron / a systemd timer, a few times a week rather than
continuously — see project instructions doc for the reasoning.
