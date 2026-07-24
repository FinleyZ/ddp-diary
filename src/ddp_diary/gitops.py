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
from .models import GitConfig, GitStatus


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


def read_status(data_dir: Path) -> GitStatus:
    """Read-only git status for `status` (spec.md §9). Never raises — a
    non-repo `data_dir`, or a repo with no upstream tracked, both degrade to
    best-effort `None` fields rather than an exception, since this feeds a
    human-facing report, not a decision path (mirrors `mount.is_available`'s
    "never raise" philosophy)."""
    if not _is_git_repo(data_dir):
        return GitStatus()

    ahead, behind = _read_ahead_behind(data_dir)
    subject, commit_date = _read_last_commit(data_dir)
    return GitStatus(
        is_dirty=_read_is_dirty(data_dir),
        ahead=ahead,
        behind=behind,
        last_commit_subject=subject,
        last_commit_date=commit_date,
    )


def _is_git_repo(data_dir: Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(data_dir), capture_output=True, text=True, encoding="utf-8",
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"
    except OSError:
        return False


def _read_is_dirty(data_dir: Path) -> Optional[bool]:
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(data_dir), capture_output=True, text=True, encoding="utf-8",
        )
    except OSError:
        return None
    return bool(proc.stdout.strip()) if proc.returncode == 0 else None


def _read_ahead_behind(data_dir: Path) -> tuple[Optional[int], Optional[int]]:
    # Fails cleanly (nonzero exit) when no upstream is configured for HEAD —
    # that's a normal, expected case here, not an error to surface.
    try:
        proc = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"],
            cwd=str(data_dir), capture_output=True, text=True, encoding="utf-8",
        )
    except OSError:
        return None, None
    if proc.returncode != 0:
        return None, None
    parts = proc.stdout.strip().split()
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def _read_last_commit(data_dir: Path) -> tuple[Optional[str], Optional[str]]:
    try:
        subject_proc = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=str(data_dir), capture_output=True, text=True, encoding="utf-8",
        )
        date_proc = subprocess.run(
            ["git", "log", "-1", "--format=%ci"],
            cwd=str(data_dir), capture_output=True, text=True, encoding="utf-8",
        )
    except OSError:
        return None, None
    subject = subject_proc.stdout.strip() if subject_proc.returncode == 0 else None
    commit_date = date_proc.stdout.strip() if date_proc.returncode == 0 else None
    return (subject or None), (commit_date or None)


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
