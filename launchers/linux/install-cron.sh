#!/bin/bash
# Installs (or updates) the ddp-diary cron lines without clobbering any other
# crontab entries you already have. Run manually — never invoked by ddp-diary
# itself. See spec.md §10 and the approved migration plan for when to run this.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MARKER_START="# >>> ddp-diary >>>"
MARKER_END="# <<< ddp-diary <<<"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

crontab -l 2>/dev/null | sed "/$MARKER_START/,/$MARKER_END/d" > "$TMP" || true

{
    cat "$TMP"
    echo "$MARKER_START"
    echo "@reboot sleep 120"
    echo "0 20 * * * $REPO_ROOT/launchers/linux/run.sh daily >> $REPO_ROOT/state/cron.log 2>&1"
    echo "$MARKER_END"
} | crontab -

echo "Installed ddp-diary cron lines. Verify with: crontab -l"
