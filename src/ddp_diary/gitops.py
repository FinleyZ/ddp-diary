"""git plumbing for the data repo: commit (skip if nothing staged) and push.

The only module that shells out to `git` for data-repo purposes. `commit()`/`push()`
never do more than their names say — the always-push-after-failure rule (spec.md
§12) is the runner's responsibility, implemented by calling `push()` unconditionally
after `commit()` regardless of what happened in between, not by anything in here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from .errors import GitCommitError
from .models import GitConfig


def commit(data_dir: Path, git_cfg: GitConfig, *, scope: str, date_str: str) -> bool:
    """`git add -A && git commit`. Returns True if a commit was made, False if
    there was nothing staged (not an error — e.g. a `--dry-run` upstream, or a
    period whose entry didn't change). Raises `GitCommitError` only on an
    unexpected git failure (exit code 4, spec.md §9)."""
    _run_git(["add", "-A"], cwd=data_dir)

    status = _run_git(["status", "--porcelain"], cwd=data_dir)
    if not status.stdout.strip():
        return False

    message = f"{git_cfg.commit_prefix} {scope} {date_str}"
    _run_git(["commit", "-m", message], cwd=data_dir)
    return True


def push(data_dir: Path, git_cfg: GitConfig) -> tuple[bool, Optional[str]]:
    """`git push <remote> <branch>`, only if `git_cfg.push` is set (false on the
    VM role — it never pushes, spec.md §5). Returns `(ok, error_message)` rather
    than raising, so the runner can log a failure and still complete its
    always-push-after-failure sequence without exception-based control flow
    inside what is effectively a `finally` block."""
    if not git_cfg.push:
        return True, None
    try:
        proc = subprocess.run(
            ["git", "push", git_cfg.remote, git_cfg.branch],
            cwd=str(data_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stderr.strip() or proc.stdout.strip())
    return True, None


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        raise GitCommitError(f"failed to run git {' '.join(args)}: {exc}") from exc
    if proc.returncode != 0:
        raise GitCommitError(f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc
