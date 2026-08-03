# Nowplay

Personal tool to pull your Netflix "My List" watchlist into a local SQLite
database, so you can see it outside the Netflix app. Scoped to Netflix only
for now — see `nowplay-project-instructions.md` for the full background,
platform-by-platform difficulty assessment, and decisions made so far.

## Before you use this

Netflix's Terms of Use prohibit automated/scripted access to the service
(section 4.3: no "robot, spider, scraper or other automated means"). This is
a contract risk, not a legal one — the realistic downside is account
suspension if Netflix detects and acts on it, not legal action. That risk
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
```

A Firefox window opens to the Netflix login page. Log in by hand (this
handles any MFA/captcha Netflix throws at you), then press Enter in the
terminal once you're in. This saves your session to
`data/netflix_state.json`. You only need to redo this if the saved session
stops working (e.g. you get logged out).

## Scraping

```bash
python -m nowplay.cli scrape netflix
```

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
