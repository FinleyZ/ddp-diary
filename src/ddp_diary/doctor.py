"""`ddp-diary doctor` — environment/health checks (spec.md §14).

Each check maps to the exit code the failure it detects would actually cause
in a real `run` (spec.md §9's table) — `WARN` is reserved for the one thing
`run` itself treats as a soft skip rather than a failure (a missing share,
spec.md §10); everything else that's checkable here gets its real code.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import mount
from .models import Config

# git-remote reachability is only a real-run concern when this role actually
# pushes — gated on `config.git.push`, not `config.role`, since that's the
# actual switch `gitops.push()` itself checks (spec.md §5's invariant is a
# policy default, not something the core hardcodes by role identity).


def run(config: Config, *, verbose: bool = False) -> int:
    if verbose:
        print_resolved_config(config)

    results: list[tuple[str, str, str, int]] = []  # (name, status, detail, fail_exit_code)

    results.append(_check("data_dir exists and is writable", _writable(config.data_dir), str(config.data_dir), fail_code=2))
    results.append(_check("scratch_dir exists and is writable", _writable(config.scratch_dir), str(config.scratch_dir), fail_code=2))
    results.append(_warn("claude_projects exists", config.claude_projects.is_dir(), str(config.claude_projects)))
    results.append(_warn("shared_dir mounted and writable", mount.is_available(config.shared_dir), str(config.shared_dir)))
    results.append(_check("claude executable resolves", _is_executable(config.claude.bin), config.claude.bin, fail_code=3))

    if config.git.push:
        results.append(_check(
            "git remote reachable",
            _git_remote_reachable(config.data_dir, config.git.remote),
            config.git.remote,
            fail_code=5,
        ))

    worst = 0
    for name, status, detail, fail_code in results:
        print(f"[{status}] {name} ({detail})")
        if status == "FAIL":
            worst = max(worst, fail_code)

    if worst == 0:
        print("doctor: all checks passed")
    else:
        print(f"doctor: one or more checks FAILED (would exit {worst} on a real run)")
    return worst


def _check(name: str, ok: bool, detail: str, *, fail_code: int) -> tuple[str, str, str, int]:
    return (name, "OK" if ok else "FAIL", detail, fail_code)


def _warn(name: str, ok: bool, detail: str) -> tuple[str, str, str, int]:
    return (name, "OK" if ok else "WARN", detail, 0)


def print_resolved_config(config: Config) -> None:
    """Print a plain-text summary of what a config file actually resolved to
    — shared by `doctor -v` and `status -v` (spec.md §9) so both stay
    identical without duplicating print lines that would drift apart."""
    print(f"role: {config.role}")
    print(f"data_dir: {config.data_dir}")
    print(f"shared_dir: {config.shared_dir}")
    print(f"claude_projects: {config.claude_projects}")
    print(f"scratch_dir: {config.scratch_dir}")
    print(f"claude.bin: {config.claude.bin}")
    print(f"claude.model: {config.claude.model}")
    print(f"git.push: {config.git.push} (remote={config.git.remote}, branch={config.git.branch})")
    print(
        f"limits: max_turns={config.limits.max_turns} max_budget_usd={config.limits.max_budget_usd} "
        f"backfill_days={config.limits.backfill_days} backfill_max_per_run={config.limits.backfill_max_per_run}"
    )
    print("---")


def _writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".ddp-diary-doctor-probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _is_executable(bin_path: str) -> bool:
    if shutil.which(bin_path):
        return True
    return Path(bin_path).is_file()


def _git_remote_reachable(data_dir: Path, remote: str) -> bool:
    try:
        proc = subprocess.run(
            ["git", "ls-remote", "--exit-code", remote],
            cwd=str(data_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
        return False
