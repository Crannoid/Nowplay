#!/usr/bin/env bash
# Syncs source to containerHost (the Pi, 192.168.68.101) and builds the
# scraper image there natively, rather than building on this (x86) machine
# and shipping a tarball the way scripts/build_and_deploy_tower.sh did.
#
# DEFAULT CHOICE, NOT CONFIRMED WITH PAUL: building natively on the Pi avoids
# cross-architecture emulation entirely — this build machine is x86, the Pi
# is arm64, and a plain `docker build` here produces an amd64 image that
# won't run natively there. The alternative is cross-compiling with
# `docker buildx build --platform linux/arm64` and shipping the result via
# save/scp/load (the pattern build_and_deploy_tower.sh used, which only
# worked because Tower was also x86) — that needs buildx + QEMU binfmt set
# up on this machine and is slower. Native build was picked because
# Playwright's own native-venv install already proved the Pi has the
# resources for this workload (see Hosting & Architecture in Notion) and it
# sidesteps the emulation question entirely, but this hasn't been run for
# real yet (no SSH access to the Pi from this session) — first real run is
# the actual confirmation. If Portainer's own image-build-from-Compose flow
# is preferred instead of this script, that's a reasonable alternative not
# implemented here.
#
# Usage:
#   PI_HOST=192.168.68.101 PI_USER=pi ./scripts/build_and_deploy_pi.sh
#
# Requires: rsync and SSH access to the Pi (key-based, so rsync/ssh don't
# prompt), Docker installed on the Pi, and enough free space there for the
# build (python:3.12-bookworm plus Firefox and its dependencies — expect at
# least 1-2GB).
set -euo pipefail

IMAGE_NAME="nowplay-scraper:latest"
PI_HOST="${PI_HOST:-192.168.68.101}"
PI_USER="${PI_USER:-pi}"
REMOTE_DIR="/home/${PI_USER}/nowplay-build"
# Shared with the website container once it exists — see "DB access: direct
# write, no write API" in Hosting & Architecture. Confirm this matches
# wherever the website container's compose/run config points, or both
# containers won't actually see the same nowplay.db.
DATA_DIR="${DATA_DIR:-/home/${PI_USER}/nowplay-data}"

cd "$(dirname "$0")/.."

echo "==> Syncing source to ${PI_USER}@${PI_HOST}:${REMOTE_DIR}"
# Excludes mirror .dockerignore: data/ (auth session state + nowplay.db) must
# never be part of the build context, and .git/.venv/__pycache__ are just
# noise to ship over the network.
rsync -az --delete \
    --exclude 'data/' \
    --exclude '.git/' \
    --exclude '.venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude 'src/nowplay.egg-info/' \
    ./ "${PI_USER}@${PI_HOST}:${REMOTE_DIR}/"

echo "==> Building ${IMAGE_NAME} on the Pi"
ssh "${PI_USER}@${PI_HOST}" "cd '${REMOTE_DIR}' && docker build -t '${IMAGE_NAME}' ."

echo "==> Ensuring the shared data directory exists on the Pi"
ssh "${PI_USER}@${PI_HOST}" "mkdir -p '${DATA_DIR}'"

cat <<EOF

==> Done. ${IMAGE_NAME} is built on the Pi.

Before running it, copy your saved auth session state onto the Pi's shared
data directory (or run scripts/login.py directly on the Pi — it has a real
display attached, see Hosting & Architecture in Notion, so this copy step
may not be needed going forward):
  scp data/netflix_state.json ${PI_USER}@${PI_HOST}:${DATA_DIR}/

Then, on the Pi, run a one-off test:
  docker run --rm \\
    -v ${DATA_DIR}:/app/data \\
    -e TMDB_API_KEY=\${TMDB_API_KEY} \\
    ${IMAGE_NAME}

Check the output for "netflix: upserted N items" (and an Enrichment summary
if TMDB_API_KEY was set), and inspect ${DATA_DIR}/nowplay.db against a
known-good local run to confirm the item count/titles match — same
verification build_and_deploy_tower.sh's proof-of-concept originally called
for, not yet repeated here for this native-on-Pi build.
EOF
