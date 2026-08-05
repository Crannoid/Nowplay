# Project: Streaming Watchlist Aggregator

## Second brain — Notion

Status, decisions, and platform research for this project are tracked in Notion
(Technical Notes → Nowplay), not only here — treat it as the second brain for
Nowplay, not this file alone.

- **Read first.** Before starting work in a session, check Notion for current
  status and anything logged there since this file was last touched — start
  with Project Plan (order of operations, current phase, next steps). This
  file can and does drift out of date between sessions; Notion is where
  changes should be checked for, not assumed absent.
- **Write back.** At the end of a session, log anything worth persisting — new
  decisions, confirmed platform findings, status changes — to the relevant
  Notion page, not just here.

Structure:
- [Nowplay](https://app.notion.com/p/3b292a0f6496819e97c5dffd25389ef3) — top-level page
- [Project Plan](https://app.notion.com/p/3b292a0f6496814b8a30fc818636a3dd) — order of operations, current phase, next steps
- [Requirements & Platform Notes](https://app.notion.com/p/3b292a0f649681368b19fc5ad62dd884) — purpose, platform-by-platform assessment, key decisions
- [Data Model](https://app.notion.com/p/3b292a0f6496813e8067c8c90b066515) — SQLite schema and design decisions
- [Automation & Scheduling](https://app.notion.com/p/3b292a0f64968162b610fd0a18d2c420) — design for moving from manual testing scripts to a scheduled, automated process

This file remains the in-repo working log; Notion is the canonical, browsable
record. Keep both in sync — don't let one drift ahead of the other without
updating the other.

## Goal
Build a personal tool that consolidates "watchlist" (My List / Watchlist) data from
Netflix, Disney+, and Amazon Prime Video into one central app, so Paul can see
everything he's queued up across services in one place.

**The end product is a website, not a database.** (Clarified 2026-08-04 — see "UI
priority correction" below.) The scraping/SQLite pipeline is the means, not the
point: the goal is a website on the local network — no remote access needed yet —
browsable from Paul's phone, showing all shows and films across every streaming
service's watchlist in scope.

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

## Hosting & architecture (decided 2026-08-04)

Home lab hosts in play: `containerHost` (Raspberry Pi, 192.168.68.101, Docker host) and
`Unraid` (custom PC under stairs, 192.168.68.113 / `tower.cr`, x86). Both run Docker
containers; a Windows 11 PC (daily driver) was considered and ruled out as the scraper's
home — not always-on, and the goal is to keep it lightly installed.

- **DB + website → containerHost (Pi), in containers.** SQLite stays local to the
  website process. The website *owns* the DB and exposes a small write API for the
  scraper to POST scraped results to — it does not accept direct file/network-share
  access to `nowplay.db`. This is a hard requirement, not a preference: SQLite's own
  docs warn that locking is unreliable over network filesystems (NFS/SMB) and can
  corrupt the DB, so the scraper must never write to the .db file directly if it's
  running on a different host than the DB (sqlite.org/useovernet.html,
  sqlite.org/lockingv3.html).
- **Scraper → Unraid, in a container**, not the Pi and not the Windows PC.
  - Playwright is officially supported on arm64 Debian 12/13 / Ubuntu 22.04+, so the
    Pi wasn't ruled out for lack of official support — Unraid was preferred because
    it's x86 (Playwright's best-tested lane), has more headroom for a real headed
    Firefox than the Pi, and keeps the Pi's footprint small. An unconfirmed,
    flagged-not-fact concern: an ARM-built Firefox might produce an unusual
    GPU/WebGL fingerprint versus a typical desktop session — no evidence found
    either way for Netflix/Disney+ specifically.
  - Unraid's Community Applications store is not a blocker: containers can be added
    directly via the Docker tab by specifying an image, no CA submission required.
    If Compose files are wanted, the existing "Docker Compose Manager" CA plugin can
    be installed once — that's installing a tool, not publishing an app.
- **Auth (`login.py`) stays a local, manual step** — run it wherever there's a real
  screen (e.g. the Windows PC), in a native venv as the Login & Session Setup page in
  Notion already documents, not in a container. Copy the resulting
  `data/<platform>_state.json` onto Unraid for the scheduled scraper to use. Neither
  Unraid nor the Pi has a monitor attached, so this can't move into the container path.

Not yet built: the website's write API. Currently there's no front end at all (see
Requirements & Platform Notes / Project Plan in Notion) — this needs designing before
the scraper can be pointed at Unraid for real.

## Scraper-on-Tower proof of concept (started 2026-08-04)

Scoped narrowly: prove headed Firefox + Xvfb work correctly inside a Docker
container on Tower's x86 hardware, decoupled from the not-yet-built website
write API. This is deliberately *not* the final integration — see "Hosting &
architecture" above for what still needs designing before the scraper is
pointed at Tower for real (the write API, and Tower POSTing to it instead of
touching a DB file directly).

- **Playwright pinned to `1.62.0`** (was `>=1.45`) in `pyproject.toml` /
  `requirements.txt`. Reason: the Docker base image ships exact-matched
  browser binaries per Playwright release, and a version mismatch between
  the pip package and the image fails browser launch outright. This means
  local dev environments must also reinstall to `1.62.0` — worth knowing if
  an existing `.venv` was set up before this change.
- **Base image**: `mcr.microsoft.com/playwright/python:v1.62.0-jammy` —
  ships Firefox and Xvfb preinstalled, avoiding a separate `playwright
  install --with-deps firefox` + manual Xvfb apt install. Not independently
  confirmed that this exact tag exists (network access wasn't available to
  check directly) — first `docker build` will confirm; if it 404s, check
  https://mcr.microsoft.com/en-us/artifact/mar/playwright/python/tags for
  the current tag and update it alongside the pip pin above.
- **Build/deploy workflow**: build on the Ubuntu desktop, `docker save` →
  `scp` → `docker load` on Tower — no registry, per Paul's preference.
  Scripted in `scripts/build_and_deploy_tower.sh`.
- **DB scoping for this phase**: the container writes to a local
  `data/nowplay.db` on Tower's own disk (bind-mounted, not a network
  share) — not the Pi's DB. This doesn't violate the "no direct writes from
  a different host" requirement above, since it's local to Tower, not
  accessed over NFS/SMB from elsewhere. It's a temporary stand-in until the
  write API exists, at which point this should be replaced with the
  container POSTing to the Pi instead of writing a local DB file.
- **Not yet done**: an actual build/run on Tower itself (needs Paul's
  hands — this session drafted the Dockerfile, entrypoint, and deploy
  script but doesn't have SSH access to Tower or a matching x86 Docker
  environment to fully validate against a live Netflix session).

**Update (2026-08-04, same day) — first run on Tower hung indefinitely.**
Diagnosed live via `docker exec` into the running container: `ps aux` showed
Xvfb running fine, but no `python`/`firefox` process ever started — `xvfb-run`
itself never handed off. Root cause: `xvfb-run`'s startup logic polls with
`xdpyinfo` to detect when Xvfb is ready before launching the wrapped command;
`xdpyinfo` isn't included in the `mcr.microsoft.com/playwright/python` base
image (it ships in the separate `x11-utils` package, not with Xvfb), so the
readiness check fails every iteration and loops forever rather than erroring.
Confirmed via `curl` from inside the container that outbound network/DNS was
fine throughout — this was purely an Xvfb/browser-launch handoff issue, not
a networking one. Fix: added `x11-utils` to the Dockerfile's apt install.

**Update (2026-08-04, same day) — `xdpyinfo` fix did not resolve it.**
Rebuilt with `x11-utils` installed, re-ran on Tower: identical hang,
identical process tree (Xvfb running, no python/firefox). So the missing
binary wasn't the (full) explanation — something else in `xvfb-run`'s
internal readiness-check/handoff is stuck, not root-caused further (didn't
trace into an X11 auth-cookie handshake theory with hard evidence before
deciding to stop debugging a third-party script blind).

**Fix**: replaced `xvfb-run` entirely in `docker/entrypoint.sh`. It now
starts `Xvfb :99 ... -nolisten tcp` itself, polls for the `/tmp/.X11-unix/X99`
socket file directly (no X11 auth-cookie handshake involved, unlike
`xvfb-run`'s check), then execs the wrapped command once the socket exists.

**Update (2026-08-04, same day) — Xvfb fix worked; found 0 items, cause
confirmed via screenshot.** The full pipeline ran on Tower (Xvfb, headed
Firefox, Netflix navigation) without hanging or erroring — real progress.
0 items, though. Added a debug-dump-on-0-items to `netflix.py` (mirrors the
existing `disney_plus.py` discovery-mode pattern) printing `page.url` and
saving `page.html`/`page.png` to `data/netflix_debug/`. The screenshot showed
Netflix's "Who's watching?" profile-select screen, not the login page and not
my-list. **Confirmed: Netflix separates account-level auth from profile-level
auth** — a session captured by `scripts/login.py` right after login but
before clicking into a specific profile is valid (not logged out) but not
enough to reach `/browse/my-list`, which redirects to profile-select instead.
Fix (no code, process only): redo `scripts/login.py netflix`, click the
profile before pressing Enter to save state. `netflix.py` now also detects
this specific case ("Who's watching" in page content) and prints a targeted
message rather than lumping it in with generic stale-selector guidance — this
could recur on a schedule if profile-level auth expires on a different
cadence than account-level auth, so worth being able to diagnose at a glance
next time.

**Update (2026-08-04, same day) — proof of concept achieved.** Re-ran on
Tower with a profile-scoped session: `netflix: upserted 20 items, marked 0 as
removed.` Full pipeline (Xvfb, headed Firefox, Netflix auth incl. profile
selection, DOM extraction, local SQLite upsert) confirmed working in a
container on Tower. Item count/titles not yet cross-checked against a
known-good reference (Paul's actual My List page or a prior local run) —
worth doing before treating this as fully validated, per the same "don't
assume it's right just because it ran" logic that caught the earlier two
issues. Reminder: this container run still writes to a **local**
`data/nowplay.db` on Tower — the write-API to the Pi that the real
integration depends on (see "Hosting & architecture" above) still doesn't
exist. Next phase is a choice between building that write API/website (the
stated near-term priority per "UI priority correction" above) or scheduling
this container to run unattended (cron/systemd timer) first — not decided
yet, worth a deliberate call rather than defaulting to whichever's easier.

**Update (2026-08-04, same day) — Disney+ proven too.** Validated locally on
Paul's dev PC first (confirmed selectors from 2026-08-03 still work), then
in the same Tower container used for Netflix, via a CLI command override
(`python -m nowplay.cli scrape disney_plus`) — no Dockerfile/entrypoint
changes needed, since the image was already scraper-agnostic. Also added the
same 0-items debug-dump protection to `disney_plus.py` that Netflix's Tower
testing motivated, in case of a similar stale-session/profile-selection gap
in future. Both in-scope-so-far platforms (Netflix, Disney+) are now
confirmed running end-to-end in a container on Tower. Prime Video not
started. Same open decision as above: write API/website vs. scheduling is
the next call to make.

## BBC iPlayer / HBO Max / Prime Video scaffolding (2026-08-04)

Added scraper modules for all three remaining in-scope platforms, given
Paul's own watchlist URLs directly (not searched/guessed):
- BBC iPlayer: `https://www.bbc.co.uk/iplayer/watchlist`
- HBO Max: `https://play.hbomax.com/my-stuff`
- Prime Video: given as
  `https://www.amazon.co.uk/gp/video/mystuff?ref_=atv_hm_hom_c_9zZ8D2_mys`,
  Paul flagged the trailing `ref_=` as possibly unstable — that's an Amazon
  tracking/attribution param, not required for the page to load, so it was
  dropped in favour of the bare `gp/video/mystuff` path.

**None of the three have had a discovery pass** — no confirmed DOM
selectors for any of them, unlike Disney+ where a real session was already
inspected. Built all three in discovery mode only (same pattern Disney+
used before its selectors were confirmed): `TITLE_CARD_SELECTOR = None`,
first run dumps `page.url` + page HTML + a screenshot to
`data/<platform>_debug/` rather than guessing at markup. Wired into
`cli.py`'s `SCRAPERS` dict and `scripts/login.py`'s `LOGIN_URLS`.

**Login URLs — confidence varies, flagged honestly rather than asserted as
fact:**
- HBO Max (`https://play.hbomax.com/login`) — reasonably confident, same
  domain as Paul's own watchlist URL, corroborated by a web search.
- Prime Video — **correction (2026-08-04):** the original guess,
  `https://www.amazon.co.uk/ap/signin`, was wrong — confirmed by Paul, it
  returns "not a functioning page." Bare `ap/signin` needs redirect context
  (`openid.*` query params) only present when Amazon itself bounces you
  there from another page, not when visited cold. "Long-standing, stable
  URL" was true of the pattern in general, not of visiting it directly
  without that context — a real gap in the earlier reasoning, not just an
  unlucky guess. Fixed the same way as BBC iPlayer below: `login.py` now
  opens the watchlist URL itself (`amazon.co.uk/gp/video/mystuff`) and lets
  Amazon's own redirect produce a working, correctly-parameterized sign-in
  URL.
- BBC iPlayer — **not confirmed.** Web search results for a BBC sign-in URL
  were unreliable/spam-adjacent (some looked phishing-like, not used as a
  source). Rather than guess, `scripts/login.py`'s `bbc_iplayer` entry just
  opens the watchlist URL itself, which should surface BBC's own sign-in
  prompt for an unauthenticated session — Paul logs in from there by hand.
  Worth fixing to a real dedicated login URL once one's confirmed from
  actual use.

**Next step for each (not done this session):** Paul needs to run
`scripts/login.py <platform>` somewhere with a screen, then
`python -m nowplay.cli scrape <platform>` to trigger the discovery dump, then
share (or inspect) the resulting `page.html`/`page.png` to identify and set
real `TITLE_CARD_SELECTOR` values — same process already proven for Disney+.

**Update (2026-08-04, same day) — all three confirmed from real debug
dumps, discovery mode complete.** Paul ran `scripts/login.py` and a scrape
for all three; all landed on the correct page (`page.url` confirmed, not a
login redirect), and the resulting `page.html`/`page.png` dumps were
inspected directly. Real selectors set, extraction logic written, and
cross-checked against the actual saved HTML with BeautifulSoup applying the
identical selectors (not just eyeballed) before calling it done:

- **BBC iPlayer** — `a[data-bbc-content-label="content-item"]`, title from a
  clean child element (not the messier aria-label), ID parsed from the href.
  11/11 real watchlist items matched correctly.
- **HBO Max** — `section[data-sonic-id="my-stuff-page-rail-my-list"]
  a[data-tile-grid="true"]`, scoped to the My List rail specifically because
  the "Recommended for You" rail below it reuses the identical tile
  component — a flat selector would've pulled in recommendations as if they
  were on the watchlist. 2/2 real items matched, 0 false positives from
  Recommended.
- **Prime Video** — the trickiest of the three: `/gp/video/mystuff` renders
  four rails (Watchlist – Movies/TV, Purchases and rentals – Movies/TV) all
  using the *identical* `<article data-testid="card">` component with a
  clean `data-card-title` attribute. extract() now filters by carousel
  heading text (must start with "Watchlist") before pulling cards, to avoid
  counting purchased/rented titles as watchlist items. Confirmed 8 real
  watchlist cards found, correctly excluding the 2 purchases. Noted but not
  used: a dedicated `/gp/video/mystuff/watchlist` URL exists in the page's
  own nav markup, which would avoid needing this section-filtering — not
  switched to since its rendered output wasn't independently confirmed.

All three platforms are now in the same state Netflix/Disney+ were before
Tower testing: selectors confirmed locally, not yet run in the Tower
container. That's the natural next step, same process already proven for
Netflix and Disney+.

## Container defaults to scraping all platforms (2026-08-04)

Per the failure-isolation principle already decided in Automation &
Scheduling ("Netflix should keep running even if Disney+ selectors drift"),
extended down to the container level: `python -m nowplay.cli scrape all` is
now a real command (added to `cli.py`, not just a design note) that runs
every registered scraper in turn, and it's the Dockerfile's default `CMD` —
was `scrape netflix` only.

- One platform's scraper throwing (stale selectors, browser launch failure,
  network error, anything) is caught, printed with a full traceback, and
  recorded in a summary — it does **not** stop the remaining platforms.
- A per-run summary (status, item/removed counts, or the error) is printed
  and also written to `data/last_scrape_summary.json`, next to `nowplay.db`
  — addresses the logging gap Automation & Scheduling already flagged
  ("currently only visible in an interactive terminal — unusable for
  diagnosing a failure after the fact").
- Exit code is non-zero only if at least one platform hard-errored — a
  genuinely empty watchlist (0 items, no exception) doesn't count as a
  failure. This is there for future cron/healthchecks.io wiring (Phase 4,
  not built yet) to be able to tell a failed run from a clean one without
  parsing log text.
- Single-platform runs still work unchanged, both via
  `python -m nowplay.cli scrape <platform>` and by overriding the
  container's command with `docker run ... nowplay-scraper:proof python -m
  nowplay.cli scrape <platform>` — useful when debugging one scraper instead
  of running the full set.

**Verification done this session:** syntax-checked, then exercised with
mocked scrapers (one succeeding, one raising, one returning 0 items) to
confirm the error-isolation actually works, not just reads correctly. It
did — worth noting the successful-looking scraper in that test also hit an
unrelated real error (a `sqlite3.OperationalError: disk I/O error` specific
to this sandbox's mounted filesystem) partway through, and the run still
correctly recorded it and continued to the remaining platforms rather than
stopping — a good, if accidental, stress test of the exact failure mode this
feature exists for.

## Netflix render race found and fixed (2026-08-04)

Paul reported the Netflix page "starts to load but items don't load." Debug
dump (`data/netflix_debug/`) confirmed this wasn't the profile-selection bug
found earlier: the embedded profile JSON showed `"profileName":"Paul"` with
`"isActive":true` — correct profile, not "Kids" (the "Kids" label visible in
the nav screenshot is a separate quick-link Netflix always shows, not an
indicator of the active profile — a plausible first read that turned out
wrong on inspection). `page.url` and the "My List" tab being highlighted
also confirmed the correct page. But 0 `.title-card` elements existed
anywhere in the dumped HTML — the page shell rendered, the list content
didn't, with no error message either.

**Root cause:** `extract()` scrolled and then did a fixed
`page.wait_for_timeout(1500)` before querying for title-cards. That's a
guess, not a guarantee — if Netflix's client-side fetch/render for list
content takes longer than 1.5s after `networkidle` fires (which only
promises no *network* activity, not that the DOM has finished updating in
response to the last response), the query runs too early and finds nothing.
Confirmed via the dump: correct page, correct profile, zero cards — that
combination only makes sense as a timing race, not a session/selector/
profile problem.

**Fix:** replaced the fixed sleep with `page.wait_for_selector(...,
timeout=15000)` in **all five scrapers** (netflix.py, disney_plus.py,
bbc_iplayer.py, hbo_max.py, prime_video.py) — they all shared the identical
copy-pasted `mouse.wheel` + `wait_for_timeout(1500)` pattern, so this was a
latent risk everywhere, not just Netflix; fixed proactively rather than only
patching the one that got reported. Waits for the real DOM signal (cards
existing) instead of guessing a delay, and still falls through cleanly to
each scraper's existing 0-items diagnostics if genuinely nothing appears
within 15s, rather than raising.

**Confirmed fixed (2026-08-04, same day).** Paul re-ran the scrape —
working. `wait_for_selector` replacing the fixed sleep resolved the render
race. This closes out the last known issue from this session's testing
across all five platforms.

**Housekeeping note:** that verification run wrote real files into this
project's actual `data/` folder — `data/nowplay.db`,
`data/nowplay.db-journal`, and `data/test_scrape_summary.json` — containing
fake test platforms ("fake_ok", "fake_error", "fake_zero"), not real
watchlist data. Attempted to delete them afterward and couldn't — this
sandbox's mount to the project folder doesn't permit file deletion
(`PermissionError: Operation not permitted`, both via `rm` and Python's
`os.remove`). **These three files need deleting by hand** before trusting
anything in `data/nowplay.db` as real; `data/` is gitignored, so nothing
here leaked into version control, but it's sitting on disk locally.

## UI priority correction (2026-08-04)

Supersedes the "Front end: none yet... revisit once the scraper is proven reliable"
line under Decisions (2026-08-03) above — that framing was wrong. Paul's own words:
**"the app is worthless without it."** The UI is not a nice-to-have bolted on after
the pipeline is proven; it is the actual deliverable. The scraper and DB exist to
feed it.

**Concrete target:** a website, local network only (no remote access needed yet),
browsable from Paul's phone, showing all shows and films currently on the watchlist
across every streaming service in scope (Netflix, Disney+, and whichever of Prime
Video / BBC iPlayer / HBO Max get built out).

**Practical implication:** building the website (DB owner + write API for the
scraper + read UI for browsing) is a near-term priority, not something deferred
until after automation is built — see Project Plan in Notion for the revised phase
ordering, and Hosting & Architecture for where it runs (containerHost/Pi).

## Metadata enrichment (thumbnails/descriptions) — investigation and prototype (2026-08-05)

Paul asked what metadata (thumbnail, brief description) could be added to
inform the DB and UI design, given `watchlist_items` currently has neither —
confirmed from the scraper code and `db.py`: only title, media_type
(inconsistently populated — Netflix never sets one), platform's own
external_id, and a handful of raw DOM attributes are captured today.

**Thumbnails from the platforms' own watchlist pages — better than
expected.** Checked the real HTML dumps in `data/*_debug/page.html`, not
just the scraper code:
- **Disney+, Prime Video, HBO Max, BBC iPlayer** all embed a poster/thumbnail
  `<img src="...">` directly on the watchlist grid card itself — confirmed
  from real CDN URLs in the dumps (BBC's `ichef.bbci.co.uk`, Disney's
  `bamgrid.com`, HBO's `discomax.com`, Amazon's `ssl-images-amazon.com`).
  Grabbing these would need one extra line per scraper, no new page visits.
- **Netflix** — not confirmed either way. `data/netflix_debug/page.html` on
  disk is stale (captured during the 0-items render-race bug, before the
  `wait_for_selector` fix), so there's no title-card markup in it to check.
  Worth checking on a fresh scrape rather than assuming.
- **None of the five** expose a synopsis/description at the watchlist grid
  level — that text lives on each title's own detail page, which would mean
  an extra page visit per item, per platform. Ruled out as a description
  source: more scraping surface, more selector maintenance, more automated-
  traffic exposure on ToS already being treated carefully (see "Context /
  constraints established" above).

**Third-party metadata source evaluated and chosen: TMDB.** Compared three
options (web-searched, not assumed, since API terms/offerings change):
- **TMDB** (The Movie Database) — free for non-commercial use with
  attribution, ~50 req/sec ceiling (nowhere near this project's volume), one
  search call returns both `poster_path` and `overview` (a short plot
  blurb) for movies or TV. Chosen.
- **IMDb** — now has an official API, but it's AWS Data Exchange, GraphQL,
  commercial-tier pricing — not a fit for a free personal tool. IMDb's own
  free non-commercial datasets (title/year/genre/rating) don't include
  images or plot text at all.
- **OMDb** (IMDb-data wrapper) — free tier includes plot (1,000 req/day,
  fine for this project's volume) but gates the Poster API behind a paid
  Patreon tier, so it alone doesn't solve the thumbnail need the way TMDB
  does in one call.

**Sequencing decision: prototype match quality before committing schema.**
Rather than guess the enrichment schema shape (columns on `watchlist_items`
vs. a separate table; whether a confidence/review-queue field is needed) and
risk rebuilding it, applied the same "discovery mode before extraction mode"
pattern this project already used for every scraper (Disney+, BBC iPlayer,
HBO Max, Prime Video were all built as discovery-first, selectors confirmed
from real dumps before extraction logic was written) — see real TMDB match
quality against Paul's actual watchlist titles first, then design the schema
around what that shows.

**Built:** `scripts/tmdb_match_prototype.py` — read-only against
`nowplay.db` (uses the existing `db.list_active()`, no schema/DB writes), no
new dependency (stdlib `urllib`, not `requests`, per this project's existing
minimal-dependencies stance — see `db.py`'s module docstring). For each
active watchlist item it searches TMDB (`/search/movie`, `/search/tv`, or
`/search/multi` depending on the scraped `media_type` — `multi` is the
fallback when the scraper didn't capture a reliable type, e.g. Netflix) and
writes a CSV (`data/tmdb_match_prototype.csv`) with the matched title/year,
a `confidence` label (`exact` / `fuzzy` / `no_match`, based on whether
TMDB's top-ranked result's title matches the scraped title exactly), poster
URL, a truncated overview, and TMDB's own `movie`/`tv` classification per
match (`tmdb_matched_media_type`) — useful for backfilling media_type gaps
in scrapers that don't set one, since TMDB tags each `/search/multi` result
with its own type.

**Bug found and fixed during setup:** `/search/multi` returns people
(actors/directors) alongside movies and TV shows in the same result list,
each tagged with its own `media_type` field. The first version of the script
didn't filter these out, so a title that happened to match a person's name
could have been picked as if it were a movie/show match. Fixed by dropping
any `multi` result whose `media_type` isn't `movie` or `tv` before scoring
it as a candidate.

**Requires a free TMDB API key** (Settings → API → request a key, personal/
non-commercial application type) set as `TMDB_API_KEY` in the environment
the script runs in. Confirmed working end-to-end by Paul (2026-08-05).

**Status: prototype run, not yet reviewed for match quality.** Next step is
Paul reviewing the `fuzzy`/`no_match` rows in `data/tmdb_match_prototype.csv`
against his real watchlist — that determines whether a couple of extra
columns on `watchlist_items` are enough, or whether a separate
`title_metadata` table is warranted (leaning toward the latter, to avoid
querying TMDB twice for the same film sitting on two platforms' watchlists,
given the current schema's one-row-per-platform-per-title shape). Schema
change and a real (DB-writing) enrichment step, wired into `cli.py`, are not
yet built — this prototype is deliberately disposable, per its own docstring.

## Metadata enrichment schema decided and implemented (2026-08-05)

Following on from the TMDB prototype above: Paul reviewed match quality
against the real watchlist and confirmed it was good enough to proceed.
Storage engine reconfirmed as SQLite too — Paul's own numbers (never more
than ~100 items, under 100 DB accesses a month) rule out Postgres as
unneeded overhead, consistent with the 2026-08-03 decision.

**Schema change** (`src/nowplay/schema.sql`): added a `title_metadata` table
rather than columns on `watchlist_items`, keyed on TMDB's `tmdb_id`
(`UNIQUE`). Reasoning: `watchlist_items` is one row per platform per title,
so the same film sitting on two platforms' watchlists would mean two
separate TMDB lookups and two copies of the same poster/overview if
enrichment lived as flat columns — a separate table lets both rows share one
fetch. Flagged honestly as a close call, not a slam dunk: at ≤100 items and
this access pattern, the API-call savings from that dedup are negligible: the
real argument for the separate table is "one canonical record per film" as a
correctness property, which costs only one extra table and a nullable FK at
this scale. `watchlist_items` gained two columns: `title_metadata_id` (FK,
nullable) and `metadata_checked_at` (stamped on every enrichment attempt,
including a `no_match`, so the enrichment step doesn't re-query TMDB for a
confirmed-unmatched title on every future scrape).

**Migration handling**: `schema.sql`'s `CREATE TABLE IF NOT EXISTS` only
covers a brand-new DB. `db.init_db()` now also runs
`_migrate_add_metadata_columns()`, which checks `PRAGMA table_info` and adds
the two new columns to an existing `watchlist_items` table if missing —
needed for the DB already running on Tower. Verified against a simulated
pre-2026-08-05 DB: existing rows preserved, migration is idempotent on
repeat `init_db()` calls. One subtlety: `idx_watchlist_metadata` (indexing
`title_metadata_id`) couldn't live in `schema.sql` itself, since
`executescript()` runs the whole file in one pass, before the Python-side
migration adds that column to an old DB — it's created separately in
`init_db()`, after the migration step. Caught by testing the migration path
directly rather than assumed; see comment in `schema.sql`.

**`connect()`** now sets `PRAGMA journal_mode = WAL`. Not needed for today's
single-process CLI usage, but this is the same `connect()` the eventual
website process will use once the DB moves to the Pi (see Hosting &
Architecture) — set now so there's no separate migration step for it later.

**`scripts/tmdb_match_prototype.py`** promoted from read-only prototype to a
real (if still standalone, not yet wired into `cli.py`) enrichment step: on
a match it calls `db.get_or_create_title_metadata()` (dedups by `tmdb_id`)
then `db.update_item_metadata()` to link the watchlist row; on `no_match` it
still calls `update_item_metadata()` with no `title_metadata_id`, purely to
stamp `metadata_checked_at`. Added `--recheck` to force re-querying
already-checked items (e.g. retrying old `no_match` rows). Still writes the
CSV too, so a confidence spot-check is always possible after the fact.
Skips items with `metadata_checked_at IS NOT NULL` by default, so re-running
it doesn't re-burn TMDB calls on items already enriched.

Not yet done: wiring enrichment into `cli.py` as a real command (still a
standalone script), and the UI itself, which is what actually consumes
`poster_url`/`overview` — see "UI priority correction" above for why that's
the actual near-term priority.

## Scraper moved to containerHost; DB access and container topology decided (2026-08-06)

Supersedes the "Hosting & architecture (decided 2026-08-04)" section above, which had
the scraper on Tower (Unraid) and the DB owned exclusively by the website process. Both
have changed — this section is the current state; the section above is kept for history,
not as instructions to follow.

**Scraper consolidated onto containerHost (the Pi), not Tower.** Tower is no longer part
of Nowplay's plan. containerHost is confirmed as a Pi 4, 4GB RAM (3.7GiB usable), with a
real GUI/display attached. Playwright's Firefox launches there via a native venv (needs
`playwright install firefox` — the pip package alone doesn't fetch browser binaries, which
tripped up the first attempt). Tower's Docker/Xvfb proof-of-concept wasn't wasted — it
validated the headed-Firefox-in-a-container mechanism itself, which is being reused as
containerHost's scraper container image.

**Container topology: two containers, not three.** Scraper and website, each their own
container on the Pi, sharing one Docker volume for `nowplay.db`. No separate DB
container — SQLite isn't a server process, so there's nothing to run as a third
container; it would only be a volume-owning no-op.

**DB access: direct write, no write API.** The original plan (website owns the DB
exclusively, scraper POSTs to a write API) was driven by the scraper and DB being on
different hosts — SQLite's own docs warn locking is unreliable over network filesystems
(NFS/SMB). That risk doesn't apply once both are on containerHost: a directory
bind-mounted into two containers on the same machine isn't a network filesystem.

The remaining argument for a write API even same-host was keeping a single writer as a
correctness property (avoiding two processes racing on the upsert-then-mark-removed
sequence). This is resolved by folding TMDB metadata enrichment (`scripts/
tmdb_match_prototype.py`, not yet wired into `cli.py`) into the scraper's own process —
planned to run automatically as the last step of `scrape all`, since enrichment only ever
has new work right after a scrape. That makes the scraper the DB's only writer
regardless, so no API is needed to enforce it.

- Scraper container: bind-mounts the shared `data/` volume, calls `db.upsert_items()` /
  `mark_removed_for_platform()` / the enrichment write functions directly.
- Website container: mounts the same volume, reads via `db.py` directly — also no API,
  just an in-process function call once the website exists.
- **Website never writes — enforced by code discipline, not a read-only mount.** SQLite's
  WAL mode (already set in `connect()`) needs write access to the directory even for
  read-only connections, to create/update the `-wal`/`-shm` sidecar files — a hard
  read-only mount on the website container risks breaking its reads too. Not
  independently verified against SQLite's own WAL docs; worth confirming if this becomes
  a live issue, not treated as certain.

**Not yet done / still open:**
- Concrete shared-volume path on the Pi — the scraper currently writes to a local
  `data/nowplay.db` inside its own container; needs defining as the actual shared path
  both containers will bind-mount.
- Wiring enrichment into `cli.py` as part of `scrape all` — decided, not yet built.
- A full `scrape all` end-to-end run on containerHost matching the validation Tower's
  proof-of-concept got.
- The website itself — no front end exists yet; tech stack not chosen.
- **This repo's deployment tooling is still written for Tower and needs updating**:
  `Dockerfile`'s comments reference Tower throughout (functionally probably still fine,
  but not re-validated on the Pi's arm64 architecture — Microsoft's
  `mcr.microsoft.com/playwright/python` base image's arm64 support isn't confirmed here,
  only that Playwright's Firefox works natively via venv on the Pi, which is a different
  code path); `scripts/build_and_deploy_tower.sh` is entirely Tower-specific (build on
  desktop → scp to `tower.cr`) and needs a Pi-equivalent deploy mechanism, not yet
  decided (Portainer? scp to the Pi directly? something else?) — flagged rather than
  guessed at.

Full reasoning trail for all of the above is in Notion (Hosting & Architecture, Data
Model, Project Plan) — this section is a condensed pointer, not a replacement for it.

## Code updated to match the above (2026-08-06, same day)

The "not yet done" items above are now mostly done in code, not just decided:

- **`src/nowplay/enrich.py`** (new) — TMDB enrichment logic moved out of
  `scripts/tmdb_match_prototype.py` so it's part of the installed package and
  available inside the scraper container (`scripts/` isn't copied into the
  image). Also fixes a real bug found while doing this: a failed TMDB
  request (network/HTTP error) was previously indistinguishable from a
  genuine "no match" and got permanently stamped as checked — fine for a
  manually-run, human-watched prototype, much riskier once automated. Failed
  requests now leave `metadata_checked_at` untouched so they're retried on
  the next run.
- **`cli.py`** — `cmd_scrape_all()` now runs enrichment automatically as a
  last, failure-isolated step (`python -m nowplay.cli enrich` also works
  standalone). Non-fatal if `TMDB_API_KEY` isn't set.
- **`scripts/tmdb_match_prototype.py`** — refactored to a thin wrapper around
  `nowplay.enrich`, kept for manual runs with a CSV confidence report.
- **`Dockerfile`** — base image switched from `mcr.microsoft.com/playwright/python`
  to `python:3.12-bookworm` + `playwright install --with-deps firefox`
  (Playwright's own documented "build your own image" recipe). Reason:
  researched rather than assumed — a GitHub feature request asking Microsoft
  to publish multi-arch Playwright Docker images was closed "not planned"
  (github.com/microsoft/playwright/issues/29819), so betting the Pi (arm64)
  would get a working image from that tag was a real risk, not a formality.
  This also removes the old browser/pip version-pinning trap, since
  `playwright install` always fetches the matching browser build.
- **`scripts/build_and_deploy_pi.sh`** (new) — replaces
  `build_and_deploy_tower.sh` (kept, marked historical) for deploys to
  containerHost. Builds natively on the Pi via rsync + remote `docker build`
  rather than cross-compiling on this x86 machine, to avoid an
  amd64-vs-arm64 mismatch. **Default choice, not confirmed with Paul** —
  Portainer's own build-from-Compose flow is a reasonable alternative.
- **`docker-compose.yml`** (new) — scraper service + a shared named volume
  (`nowplay_data`), Portainer-importable. Website service is commented out
  (doesn't exist yet).

**Not done / still needs Paul:** none of this has been build/run-tested
against real Docker or the real Pi from this session (no `docker` binary and
no SSH access in this sandbox) — the first real `docker build` + run there
is still the actual confirmation, same caveat as every prior "confirmed
locally, not yet run in the container" step in this log.

**Housekeeping incident during verification:** testing `enrich_active_items`
and `cmd_scrape_all` against a real SQLite connection in this sandbox hit the
same pre-existing issue logged earlier in this file (`sqlite3.OperationalError:
disk I/O error` specific to this sandbox's mounted filesystem, combined with
`db.connect()`'s default argument being bound at import time, not per-call —
a monkeypatched `DEFAULT_DB_PATH` in a test didn't actually redirect it).
This wrote `data/nowplay.db` (0 bytes) and `data/nowplay.db-journal` into the
**real** project data folder again. Same as last time, this sandbox's mount
doesn't permit deleting them (`Operation not permitted`) — **these need
deleting by hand.** `nowplay.db` was already correctly gitignored
(`data/*.db`); `nowplay.db-journal` was not (gitignore only covered `.db`,
not `.db-journal`/WAL sidecars) and was tracked and showing as modified —
fixed in `.gitignore` and untracked via `git rm --cached` this session. One
more thing to check on Paul's end: that `git rm --cached` left a
`.git/index.lock` file this sandbox also couldn't delete
(`Operation not permitted`); `git status`/`git add` kept working fine
afterward from inside this sandbox, so it looks benign, but it wasn't
possible to verify against a real git client outside the sandbox — worth a
quick check that `git status` still works normally on Paul's own machine.

## Working style for this project
- Conclusions-first, structured responses.
- Honest, balanced technical assessment — flag risk and uncertainty rather than
  smoothing it over.
- Don't state anything as fact without a basis (search/verify current platform
  behaviour where it may have changed rather than assuming from general knowledge).
