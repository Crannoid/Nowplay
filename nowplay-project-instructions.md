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
  request-based (can take up to 30 days) and, per Netflix's own Help Center
  (help.netflix.com/en/node/100624, checked 2026-08-03), the data it covers is
  scoped to "Content Interaction History" — viewing activity and content you've
  rated. Netflix's own description does not list "My List" / watchlist as a
  category included in the export. Treat this as a live-scraping-only project;
  the bulk export is not a reliable watchlist source and shouldn't be relied on
  as a fallback without first requesting an actual export and inspecting it.
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
- **Caveat (2026-08-03 check)**: this covers JS-level and CDP-level signals, but
  commercial anti-bot vendors (Cloudflare, DataDome, Akamai — plausible on
  Disney+/Prime) also fingerprint at the TLS layer (JA3/JA4 hash), which no
  amount of headed/Firefox JS-level tuning changes. Netflix, Disney+, and Prime's
  specific anti-bot stack isn't confirmed here — this is a real gap in the
  approach, not just a theoretical one, and is the most likely reason a scraper
  could get flagged even with everything above done correctly.
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

## Decisions (2026-08-03)
- **Scope**: Netflix only for the initial build. Prove the pipeline end-to-end
  before deciding whether Disney+/Prime are worth the added maintenance cost.
- **Storage**: SQLite. Single user, low volume (hundreds of titles, not
  millions), running on a home lab box — a Postgres server is unneeded
  operational overhead for this. Revisit only if the project grows into a
  multi-user or multi-service consumer of the data.
- **Front end**: none yet. Query the SQLite DB directly / via CLI for now;
  revisit once the scraper is proven reliable.
- **Language/tooling**: Python + Playwright (Python bindings), stdlib `sqlite3`
  — no framework, no ORM, kept minimal on purpose for a personal single-user
  tool.
- Netflix's bulk personal-data export is **not** being used as a fallback —
  see finding above; it doesn't appear to cover watchlist data.

## Disney+ attempt (started 2026-08-03)

Netflix pipeline validated end-to-end against a real account — selectors worked
first try, correct titles recovered. Extending to Disney+ next, per the
"harder" assessment already on file above.

What I could confirm before writing any code (searched, not assumed):
- Login page: `https://www.disneyplus.com/identity/login` — confirmed from
  disneyplus.com's own domain in search results.
- Web UI has a "Watchlist" entry in the top nav (per Disney's own help
  center), but **no specific watchlist URL path could be confirmed** — unlike
  Netflix's well-documented `/browse/my-list`. Disney+'s help content is
  itself JS-rendered, so it couldn't be fetched directly to check.
- **No confirmed DOM selectors.** Generic scraping write-ups reference
  `title-field`/`genre-tag` classes on Disney+'s catalog browse pages, but
  nothing specific to the watchlist page, and nothing I'd treat as reliable
  enough to hard-code blind.
- **No confirmed anti-bot vendor for Disney+ specifically.** The market
  leaders as of 2026 (Cloudflare, DataDome, Akamai, PerimeterX/HUMAN, Kasada)
  increasingly stack TLS/JA4 fingerprinting and per-site behavioral ML on top
  of the JS-level signals Firefox+headed already mitigates — if Disney+ runs
  any of these, that's a real ceiling on what this approach can evade, not
  just a theoretical one.

Given the gaps above, the Disney+ scraper was built as a **discovery tool
first, extractor second**: rather than guessing selectors, it dumped a real
page HTML + screenshot to `data/disney_plus_debug/` for inspection first.

**Update (2026-08-03, same day):** confirmed from real output —
- Watchlist selectors: `a[data-testid="set-item"]`, title parsed from
  `aria-label` (format: `"<Title>[ <badge>] Select for details on this
  title."` — badges like "Disney+ Original"/"Hulu Original Series" get
  stripped; see KNOWN_BADGES in `disney_plus.py` for the caveat that this
  list isn't exhaustive).
- Watchlist URL: `https://www.disneyplus.com/en-gb/browse/watchlist`
  (confirmed directly from Paul's session). The initial click-based nav
  approach ("find and click the Watchlist link") turned out to be
  unreliable in practice — likely SPA hydration/timing flakiness — so
  direct navigation replaced it. Note the `en-gb` locale segment is
  specific to Paul's account region.

## Working style for this project
- Conclusions-first, structured responses.
- Honest, balanced technical assessment — flag risk and uncertainty rather than
  smoothing it over.
- Don't state anything as fact without a basis (search/verify current platform
  behaviour where it may have changed rather than assuming from general knowledge).
