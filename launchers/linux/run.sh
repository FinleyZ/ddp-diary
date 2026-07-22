#!/bin/bash
# Thin launcher only: locate python3 and forward to the ddp_diary core. No
# business logic lives here — see spec.md §3 ("thin launchers").
#
# Usage: run.sh <daily|weekly|monthly>   (cron calls this with "daily" — the VM
# never runs weekly/monthly jobs, spec.md §5).
set -euo pipefail

JOB="${1:-daily}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG_PATH="$REPO_ROOT/config/vm.toml"

# Make the core importable even without an editable `pip install -e .`.
export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

exec python3 -m ddp_diary run --job "$JOB" --config "$CONFIG_PATH" --role vm
