#!/usr/bin/env bash
# Render the SVG sources in this directory to the PNGs the docs embed.
# Needs Google Chrome (headless). Usage: bash assets/src/render.sh
set -euo pipefail
cd "$(dirname "$0")"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
render() {  # render <svg> <png> <width> <height>
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --force-device-scale-factor=2 --window-size="$3,$4" \
    --screenshot="$PWD/../$2" "file://$PWD/$1" >/dev/null 2>&1
  echo "  $2"
}
render held-out-gate.svg     evaloop-held-out-gate.png     1280 900
render architecture.svg      evaloop-architecture.png      1280 920
render noise-at-the-gate.svg evaloop-noise-at-the-gate.png 1280 620
