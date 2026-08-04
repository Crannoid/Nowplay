#!/usr/bin/env bash
# Wraps the container's command in xvfb-run so Playwright's headed Firefox
# (deliberately not headless — see nowplay-project-instructions.md,
# "Technical approach") has a virtual X display to render into. Tower has
# no monitor attached, so without this, browserType.launch() fails asking
# for either headless:true or xvfb-run.
set -euo pipefail

exec xvfb-run --auto-servernum --server-args='-screen 0 1920x1080x24' "$@"
