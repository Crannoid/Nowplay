#!/usr/bin/env bash
# Starts Xvfb directly and waits for its socket, rather than using the
# `xvfb-run` wrapper script. Headed Firefox (deliberately not headless — see
# nowplay-project-instructions.md, "Technical approach") needs a virtual X
# display since Tower has no monitor attached.
#
# Why not xvfb-run: confirmed on Tower (2026-08-04) that Xvfb itself starts
# fine, but xvfb-run's own readiness-check/handoff hung indefinitely before
# ever launching the wrapped command — reproduced twice, including after
# installing xdpyinfo (which its check relies on), so the missing-binary
# theory wasn't the full story. Rather than keep debugging a third-party
# script's internals blind, this manages Xvfb itself with a simpler,
# auth-free readiness check (poll for the X11 socket file). `-nolisten tcp`
# means nothing outside this process can connect anyway, so skipping the
# Xauthority cookie dance xvfb-run does is not a meaningful security
# reduction here.
set -euo pipefail

DISPLAY_NUM=99
export DISPLAY=":${DISPLAY_NUM}"
SOCKET="/tmp/.X11-unix/X${DISPLAY_NUM}"

Xvfb "${DISPLAY}" -screen 0 1920x1080x24 -nolisten tcp &
XVFB_PID=$!

cleanup() {
  kill "${XVFB_PID}" 2>/dev/null || true
}
trap cleanup EXIT

# Poll for the socket rather than a fixed sleep, so this is fast when Xvfb
# starts quickly and doesn't fail early if it's briefly slower.
for _ in $(seq 1 50); do
  [ -e "${SOCKET}" ] && break
  sleep 0.2
done

if [ ! -e "${SOCKET}" ]; then
  echo "entrypoint.sh: Xvfb did not create ${SOCKET} within 10s" >&2
  exit 1
fi

exec "$@"
