"""Cross-platform path resolution: generic expansion, the `claude` binary, and the
default `~/.claude/projects` root.

This is the ONLY module that should contain OS-specific path assumptions — every
other module receives already-resolved `Path` objects from `config.py`, which calls
into here.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .errors import ConfigError


def expand(value: str, *, relative_to: Path) -> Path:
    """Expand `~` and environment variables in `value`; resolve relative paths
    against `relative_to` (typically the config file's directory). Always
    calls `.resolve()` — including on already-absolute input — so every
    `Config` path is consistently normalized (no trailing `..`, consistent
    casing/short-name form), which matters since these paths are compared and
    used as subprocess `cwd` values elsewhere. `resolve()` does not require
    the path to exist."""
    p = Path(os.path.expandvars(os.path.expanduser(str(value))))
    if not p.is_absolute():
        p = relative_to / p
    return p.resolve()


def default_claude_projects() -> Path:
    """`~/.claude/projects` — `Path.home()` covers `USERPROFILE` (Windows) and
    `HOME` (Linux) uniformly, so no OS branch is needed here."""
    return (Path.home() / ".claude" / "projects").resolve()


def default_scratch_dir(tool_repo_root_dir: Path) -> Path:
    """Where run state (logs, cost records, export cursor) lives by default:
    `<tool repo>/state/`, gitignored."""
    return (tool_repo_root_dir / "state").resolve()


def resolve_claude_bin(configured: str) -> str:
    """Resolve the `claude` executable. `configured` may be `"auto"` (resolve via
    PATH — `claude.cmd` on Windows, `claude` on Linux) or an explicit path."""
    if configured and configured != "auto":
        return configured
    found = shutil.which("claude") or shutil.which("claude.cmd")
    if not found:
        raise ConfigError(
            "could not locate the 'claude' executable on PATH; "
            "set claude.bin explicitly in your config"
        )
    return found


def tool_repo_root(config_path: Path) -> Path:
    """The tool repo root, given a config file living at `<repo>/config/<role>.toml`."""
    return config_path.parent.parent
