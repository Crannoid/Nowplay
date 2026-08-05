# Scraper image, now targeting containerHost (the Pi) — see "Scraper moved to
# containerHost..." in nowplay-project-instructions.md. Originally built and
# proven on Tower (Unraid, x86); Tower is no longer part of Nowplay's plan.
#
# UNCONFIRMED (2026-08-06): this image's base has only been validated on x86
# (Tower). containerHost is a Pi 4 (arm64). Playwright's Firefox has been
# confirmed to launch natively via a venv on the Pi, but that's a different
# code path (no Docker) — this image itself has NOT yet been built/run on the
# Pi. Microsoft's mcr.microsoft.com/playwright/python tags aren't confirmed
# multi-arch (amd64+arm64) here; check before trusting this on the Pi. If it
# doesn't support arm64, this Dockerfile needs a different base (e.g. a plain
# python image + `playwright install --with-deps firefox`).
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
# docker/entrypoint.sh, which wraps the scrape command so Playwright's headed
# Firefox has a virtual display to render into, since containerHost (the Pi)
# runs this unattended/headless-host, same reason Tower needed it before.
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# data/ (auth session state + nowplay.db) is deliberately NOT copied into
# the image — see .dockerignore. It must be bind-mounted at run time to the
# shared volume also mounted into the website container (decided 2026-08-06 —
# see nowplay-project-instructions.md — the scraper is the DB's sole writer,
# no write API):
#   docker run --rm -v /path/on/pi/data:/app/data nowplay-scraper:proof
#
# Default command scrapes every registered platform in turn, with per-
# platform error isolation (one failing doesn't stop the rest) — see
# cmd_scrape_all in cli.py. Override for a single platform when debugging:
#   docker run ... nowplay-scraper:proof python -m nowplay.cli scrape netflix
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "nowplay.cli", "scrape", "all"]
