"""Regression guards for two real bugs the VM migration's live testing found
(spec.md §17, 2026-07-24 entry): the Linux launcher scripts lost their git
executable bit somewhere along the way (cron -> "Permission denied"), and
claude.bin = "auto" can't find a --user pip/npm install of `claude` under
cron's minimal PATH."""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAUNCHER_SCRIPTS = ("launchers/linux/run.sh", "launchers/linux/install-cron.sh")


def test_linux_launcher_scripts_are_executable_in_git():
    out = subprocess.run(
        ["git", "ls-files", "-s", *_LAUNCHER_SCRIPTS],
        cwd=_REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == len(_LAUNCHER_SCRIPTS)
    for line in lines:
        mode = line.split()[0]
        assert mode == "100755", f"expected mode 100755, got {mode!r} in {line!r}"


def test_run_sh_puts_local_bin_on_path_for_cron():
    text = (_REPO_ROOT / "launchers" / "linux" / "run.sh").read_text(encoding="utf-8")
    assert '.local/bin' in text
    assert 'export PATH=' in text
