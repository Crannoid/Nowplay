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
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "nowplay.cli", "scrape", "netflix"]
