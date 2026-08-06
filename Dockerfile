# Scraper image for containerHost (the Pi, arm64) — see "Scraper moved to
# containerHost..." in nowplay-project-instructions.md. Originally built and
# proven on Tower (Unraid, x86); Tower is no longer part of Nowplay's plan.
#
# Base image changed 2026-08-06: mcr.microsoft.com/playwright/python ->
# python:3.12-bookworm + `playwright install --with-deps`, Playwright's own
# documented "build your own image" recipe (playwright.dev/python/docs/docker).
# Reason: mcr.microsoft.com/playwright/python's arm64/multi-arch support is
# genuinely unclear, not just unconfirmed-and-probably-fine — a GitHub feature
# request asking Microsoft to publish multi-arch Playwright Docker images (so
# a plain `docker pull` picks the right architecture automatically) was closed
# "not planned" (github.com/microsoft/playwright/issues/29819), and its Docker
# Hub tag listing is empty. Rather than gamble on that image pulling/running
# correctly on the Pi, this uses the same `playwright install --with-deps`
# approach already confirmed working natively (via venv) on the Pi itself —
# see Hosting & Architecture in Notion.
#
# CONFIRMED (2026-08-06): `docker build` succeeded on real Pi hardware, and a
# full `scrape all` run (including TMDB enrichment) worked end-to-end in the
# resulting container. The arm64 risk this section originally flagged is
# resolved, not just theoretically mitigated.
#
# Bonus: this also removes the old version-pinning trap. Previously the pip
# `playwright` version had to exactly match the browser binaries baked into
# the prebuilt image, or launches failed with "Executable doesn't exist".
# Here, `playwright install` always fetches the browser build matching
# whatever version pip just installed (still pinned in pyproject.toml /
# requirements.txt for reproducibility) — nothing to keep in sync by hand.
#
# Full (not slim) bookworm is deliberate, matching Playwright's own example
# exactly rather than optimizing image size preemptively — `--with-deps`
# still auto-detects and installs whatever system packages Firefox needs
# regardless of base, but the slim variant isn't what's documented/proven.
FROM python:3.12-bookworm

WORKDIR /app

COPY pyproject.toml requirements.txt ./
COPY src ./src
RUN pip install --no-cache-dir -e .

# Installs Firefox plus its own OS-level dependencies (fonts, codecs, etc.),
# matching whichever playwright version pip just installed above.
RUN playwright install --with-deps firefox

# xvfb-run's own startup handoff polls with `xdpyinfo` to detect when Xvfb is
# ready before launching the wrapped command — without it, that check fails
# every iteration and xvfb-run hangs forever (confirmed 2026-08-04 on Tower:
# Xvfb started fine, but xvfb-run never handed off to python because
# xdpyinfo was missing). xdpyinfo ships in x11-utils, not with Xvfb. This
# repo's docker/entrypoint.sh doesn't actually use xvfb-run (see its own
# comments for why — it manages Xvfb directly instead), but x11-utils is
# cheap and kept for parity/debugging. Unlike the old
# mcr.microsoft.com/playwright/python base, xvfb isn't preinstalled here, so
# both packages are installed explicitly.
RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb x11-utils \
    && rm -rf /var/lib/apt/lists/*

# Xvfb gives Playwright's headed Firefox (deliberately not headless — see
# nowplay-project-instructions.md, "Technical approach") a virtual display to
# render into, since this container runs unattended — see docker/entrypoint.sh.
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# data/ (auth session state + nowplay.db) is deliberately NOT copied into
# the image — see .dockerignore. It must be bind-mounted at run time to the
# volume shared with the website container (decided 2026-08-06 — see
# nowplay-project-instructions.md — the scraper is the DB's sole writer, no
# write API). TMDB_API_KEY should also be set for the metadata-enrichment
# step folded into `scrape all` (see cmd_scrape_all/cmd_enrich in cli.py) —
# it's skipped (not fatal) if the key is missing:
#   docker run --rm \
#     -v /path/on/pi/data:/app/data \
#     -e TMDB_API_KEY=xxxxxxxx \
#     nowplay-scraper:latest
#
# Default command scrapes every registered platform in turn, with per-
# platform error isolation (one failing doesn't stop the rest), then runs
# TMDB metadata enrichment over newly-scraped items — see cmd_scrape_all in
# cli.py. Override for a single platform when debugging:
#   docker run ... nowplay-scraper:latest python -m nowplay.cli scrape netflix
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "nowplay.cli", "scrape", "all"]
