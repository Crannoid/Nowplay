# Proof-of-concept image for running the Netflix scraper on Tower (Unraid),
# not the Pi (containerHost) and not the Windows PC — see "Hosting &
# architecture" in nowplay-project-instructions.md for why.
#
# Base image note: the tag's version (v1.62.0-*) must match the `playwright`
# version pinned in pyproject.toml/requirements.txt exactly. Microsoft
# publishes a Docker image per Playwright release with the matching browser
# binaries preinstalled; a mismatch fails with "browserType.launch:
# Executable doesn't exist". If this exact tag 404s on `docker build` (image
# tag naming shifts sometimes, e.g. jammy -> noble), check
# https://mcr.microsoft.com/en-us/artifact/mar/playwright/python/tags for the
# current tag for 1.62.0 and update both this line and the pin in
# pyproject.toml/requirements.txt together — do not let them drift apart.
FROM mcr.microsoft.com/playwright/python:v1.62.0-jammy

# xvfb-run's own startup handoff polls with `xdpyinfo` to detect when Xvfb is
# ready before launching the wrapped command — without it, that check fails
# every iteration and xvfb-run hangs forever (confirmed 2026-08-04: Xvfb
# started fine, but xvfb-run never handed off to python because xdpyinfo was
# missing from this base image). xdpyinfo ships in x11-utils, not with Xvfb.
RUN apt-get update \
    && apt-get install -y --no-install-recommends x11-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml requirements.txt ./
COPY src ./src
RUN pip install --no-cache-dir -e .

# Firefox and its OS-level dependencies are already baked into the base
# image (that's the point of using it over a plain python:3.12-slim +
# `playwright install --with-deps`). Xvfb is also preinstalled — see
# docker/entrypoint.sh, which wraps the scrape command in xvfb-run so
# Playwright's headed Firefox has a virtual display to render into, since
# Tower has no monitor attached.
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# data/ (auth session state + nowplay.db) is deliberately NOT copied into
# the image — see .dockerignore. It must be bind-mounted at run time:
#   docker run --rm -v /path/on/tower/data:/app/data nowplay-scraper:proof
#
# Default command scrapes every registered platform in turn, with per-
# platform error isolation (one failing doesn't stop the rest) — see
# cmd_scrape_all in cli.py. Override for a single platform when debugging:
#   docker run ... nowplay-scraper:proof python -m nowplay.cli scrape netflix
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "nowplay.cli", "scrape", "all"]
