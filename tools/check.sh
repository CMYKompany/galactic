#!/usr/bin/env bash
# Everything that must pass before a change reaches the board.
# Pushing to the update branch IS deploying: the clock installs it within minutes.
#
#   tools/check.sh          # full check (also renders preview stills/video)
#   tools/check.sh --fast   # skip the preview render
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n== %s\n' "$1"; }

step "manifest matches device/ files"
python3 tools/build_manifest.py --check

step "MicroPython compile (Pico 2 W: armv7emsp, Pico W: armv6m)"
for f in device/*.py; do
  for arch in armv7emsp armv6m; do
    python3 -m mpy_cross -march="$arch" -o /dev/null "$f"
  done
done
echo "ok"

if python3 -m pyflakes --version >/dev/null 2>&1; then
  step "pyflakes"
  python3 -m pyflakes device tools
  echo "ok"
fi

step "time zone / daylight saving"
python3 tools/test_timekeeping.py

step "over-the-air updater"
python3 tools/test_ota.py 2>&1 | grep -E "^(ok|FAIL)|passed" || true
python3 tools/test_ota.py >/dev/null 2>&1

step "launcher: apps, buttons, crash isolation, settings"
python3 tools/test_launcher.py 2>&1 | grep -E "^(ok|FAIL)|passed" || true
python3 tools/test_launcher.py >/dev/null 2>&1

if [[ "${1:-}" != "--fast" ]]; then
  step "simulated run of the whole clock"
  out="$(mktemp -d)"
  python3 tools/simulate.py "$out" | tail -2
fi

printf '\nAll checks passed.\n'
