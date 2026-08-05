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
  screen (e.g. the Windows PC), in a native venv as the README already documents, not
  in a container. Copy the resulting `data/<platform>_state.json` onto Unraid for the
  scheduled scraper to use. Neither Unraid nor the Pi has a monitor attached, so this
  can't move into the container path.

Not yet built: the website's write API. Currently there's no front end at all (see
README) — this needs designing before the scraper can be pointed at Unraid for real.

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

## Working style for this project
- Conclusions-first, structured responses.
- Honest, balanced technical assessment — flag risk and uncertainty rather than
  smoothing it over.
- Don't state anything as fact without a basis (search/verify current platform
  behaviour where it may have changed rather than assuming from general knowledge).
