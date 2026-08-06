# Website image (Phase 3 — see Project Plan in Notion). Built from the repo
# root as build context (see docker-compose.yml's `context: .`, not `./website`
# — needed so this can reach ../pyproject.toml and ../src, not just this
# folder), so it can install the `nowplay` package and reuse nowplay.db
# directly rather than duplicating the schema/queries here (see db.py's
# list_active_with_metadata for why — one source of truth for the schema).
#
# Deliberately NOT the scraper's base image or its `pip install -e .`
# (Dockerfile at repo root): that pulls in Playwright (pyproject.toml lists
# it as a hard dependency) plus a Firefox install, neither of which this
# process needs — it only ever imports nowplay.db, which itself only uses
# the stdlib (sqlite3, json, dataclasses, datetime, pathlib — no playwright
# import). `--no-deps` skips Playwright entirely, keeping this image small
# and avoiding an unrelated browser-automation dependency in a container
# that never launches a browser.
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps -e .

COPY website/requirements.txt ./website-requirements.txt
RUN pip install --no-cache-dir -r website-requirements.txt

COPY website/app.py ./
COPY website/templates ./templates
COPY website/static ./static

# data/ (nowplay.db) is deliberately NOT copied into the image — same
# reasoning as the scraper's Dockerfile: it's bind-mounted at run time from
# the same host directory the scraper writes to (see docker-compose.yml).
# This container only ever reads it (see app.py's module docstring).

EXPOSE 8080

# waitress, not Flask's own dev server — this is an always-on
# (restart: unless-stopped) process, not a one-shot batch job like the
# scraper, so it's worth the one extra dependency for a WSGI server actually
# meant to stay up unattended.
CMD ["waitress-serve", "--host=0.0.0.0", "--port=8080", "app:app"]
