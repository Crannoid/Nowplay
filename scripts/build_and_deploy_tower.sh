#!/usr/bin/env bash
# HISTORICAL (2026-08-06) — Tower is no longer part of Nowplay's plan; the
# scraper moved to containerHost (the Pi). See "Scraper moved to
# containerHost..." in nowplay-project-instructions.md. Kept for reference
# (it's what validated Docker + Xvfb + headed Firefox in a container at all);
# use scripts/build_and_deploy_pi.sh for actual deploys going forward. Also
# note: this script's docker-save/scp/docker-load approach assumes the build
# machine and target share an architecture (both x86, Tower included) — it
# is NOT reused as-is for the Pi (arm64) without cross-compiling, which is
# why build_and_deploy_pi.sh builds natively on the Pi instead. See that
# script's own header comment.
#
# Build the scraper image on the Ubuntu desktop, then ship it to Tower
# (Unraid) without a registry: docker save -> scp -> docker load.
#
# This is the proof-of-concept path only — see "Hosting & architecture" in
# nowplay-project-instructions.md. It does not set up scheduling; it gets
# the image onto Tower and leaves it to be run manually for a first test.
#
# Usage:
#   TOWER_HOST=tower.cr TOWER_USER=root ./scripts/build_and_deploy_tower.sh
#
# Requires: docker on this machine, SSH access to Tower (key-based, so scp/ssh
# don't prompt), and enough free space on both ends for the image tar (the
# Playwright base image alone is a few hundred MB).
set -euo pipefail

IMAGE_NAME="nowplay-scraper:proof"
TOWER_HOST="${TOWER_HOST:-tower.cr}"
TOWER_USER="${TOWER_USER:-root}"   # Unraid's default Docker/SSH login is root
TAR_NAME="nowplay-scraper.tar"
REMOTE_TMP="/tmp/${TAR_NAME}"

cd "$(dirname "$0")/.."

echo "==> Building ${IMAGE_NAME}"
docker build -t "${IMAGE_NAME}" .

echo "==> Saving image to /tmp/${TAR_NAME}"
docker save -o "/tmp/${TAR_NAME}" "${IMAGE_NAME}"

echo "==> Copying to ${TOWER_USER}@${TOWER_HOST}:${REMOTE_TMP}"
scp "/tmp/${TAR_NAME}" "${TOWER_USER}@${TOWER_HOST}:${REMOTE_TMP}"

echo "==> Loading on Tower and cleaning up the remote tar"
ssh "${TOWER_USER}@${TOWER_HOST}" "docker load -i '${REMOTE_TMP}' && rm -f '${REMOTE_TMP}'"

rm -f "/tmp/${TAR_NAME}"

cat <<EOF

==> Done. ${IMAGE_NAME} is loaded on Tower.

Before running it there, copy your saved auth session onto Tower:
  scp data/netflix_state.json ${TOWER_USER}@${TOWER_HOST}:/mnt/user/appdata/nowplay/data/

Then, on Tower, run a one-off test (writes to a LOCAL nowplay.db on Tower's
disk only — not the Pi's DB; the write-API to POST results to the Pi hasn't
been built yet, see nowplay-project-instructions.md):
  docker run --rm \\
    -v /mnt/user/appdata/nowplay/data:/app/data \\
    ${IMAGE_NAME}

Check the output for "netflix: upserted N items" and inspect
/mnt/user/appdata/nowplay/data/nowplay.db against a known-good local run to
confirm the item count/titles match.
EOF
