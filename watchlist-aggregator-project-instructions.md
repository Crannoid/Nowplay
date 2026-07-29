# Project: Streaming Watchlist Aggregator

## Goal
Build a personal tool that consolidates "watchlist" (My List / Watchlist) data from
Netflix, Disney+, and Amazon Prime Video into one central app, so Paul can see
everything he's queued up across services in one place.

## Context / constraints established
- None of the three platforms offer a public, official API for watchlist data.
- Scraping (via browser automation) is the only realistic route to automating this.
- All three platforms' Terms of Service prohibit automated/scripted access. This is
  a contract risk (possible account suspension if detected), not a legal one — but
  it's a real consideration, not to be waved away.
- Difficulty varies significantly by platform:
  - **Netflix** — easiest. Has a dedicated watchlist page (`netflix.com/browse/my-list`)
    that's straightforward to scrape via the DOM. Working community tools (browser
    extensions) already do this successfully.
  - **Disney+** — harder. Heavily client-rendered (GraphQL calls behind the scenes),
    stronger bot-detection tier. Expect more brittle selectors and more maintenance.
  - **Amazon Prime Video** — has a Watchlist page, scrapeable, but also runs its own
    bot detection. Moderate difficulty, between the other two.
- Netflix's official "Download your personal information" bulk export exists but is
  request-based (can take hours to 30 days), oriented around viewing history rather
  than a live watchlist, and it's unconfirmed whether it reliably includes "My List"
  as a discrete field — needs verifying directly rather than assumed.
- Third-party aggregators (e.g. Simkl) only auto-sync Netflix among these three,
  because Disney+ and Prime don't expose an accessible watch-history/watchlist
  surface their tooling can reliably use. This is a useful sanity check that we're
  not missing an easier existing path.

## Technical approach (agreed direction so far)
- **Framework**: Playwright (over Selenium) — better handling of modern JS-heavy
  SPAs, network interception, generally less flaky.
- **Browser engine**: Firefox rather than default headless Chromium. Most
  documented anti-bot detection vectors (navigator.webdriver flag, missing plugins,
  CDP protocol artifacts) specifically target the very common default headless
  Chromium fingerprint. Firefox isn't invisible, but it avoids that specific,
  heavily-targeted signature.
- **Mode**: run headed (not headless) rather than headless — closes a distinct
  class of detection signals independent of the engine choice.
- **Auth**: log in once manually, persist the session (Playwright `storageState`),
  and reuse it across runs rather than automating login each time. Repeated
  automated logins are far more likely to trigger MFA challenges or bot flags than
  a reused, already-authenticated session.
- **Unattended execution**: if run on a home lab box with no monitor attached, use
  a virtual display (Xvfb) so the browser still runs "headed" from the site's
  perspective without needing a physical screen.
- **Cadence**: scheduled job (cron / systemd timer), a few times a week rather than
  continuous polling — plenty for a watchlist, and lower-profile.
- **Data pipeline**: per-platform scraper → normalize into a common schema (title,
  type, platform, date added if available) → store in SQLite/Postgres → simple
  front end on top.
- **Maintenance expectation**: selectors will break when these sites redesign.
  Netflix has been relatively stable; Disney+ and Amazon Prime will need more
  ongoing upkeep.

## Open questions / not yet decided
- Final choice of storage (SQLite vs Postgres) and front end.
- Whether to attempt Disney+/Amazon Prime scraping at all initially, or start with
  Netflix only and evaluate from there given the higher difficulty/maintenance cost
  of the other two.
- Whether Netflix's bulk personal-data export is worth using as a supplementary or
  fallback data source alongside live scraping.

## Working style for this project
- Conclusions-first, structured responses.
- Honest, balanced technical assessment — flag risk and uncertainty rather than
  smoothing it over.
- Don't state anything as fact without a basis (search/verify current platform
  behaviour where it may have changed rather than assuming from general knowledge).
