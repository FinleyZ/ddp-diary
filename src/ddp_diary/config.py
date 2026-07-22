"""Load, validate, and resolve a ddp-diary TOML config into a `Config` object.

This is the ONLY place that reads environment/filesystem to resolve configuration —
see spec.md §7. Every hardcoded path the old per-machine scripts had is a key here.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib  # Python >= 3.11, stdlib
except ModuleNotFoundError:  # pragma: no cover - only exercised on Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

from . import paths as _paths
from .errors import ConfigError
from .models import ClaudeConfig, Config, GitConfig, LimitsConfig, LogConfig, SyncConfig

DEFAULTS: dict[str, Any] = {
    "role": None,  # required, no sane default
    "paths": {
        "data_dir": None,  # required
        "shared_dir": None,  # required
        "claude_projects": "auto",
        "scratch_dir": "auto",
    },
    "claude": {
        "bin": "auto",
        "model": "sonnet",
        "output_format": "json",
        "allowed_tools": ["Read", "Glob", "Grep", "Write", "Edit"],
        "add_dirs": [],
    },
    "limits": {
        "max_turns": 0,
        "max_budget_usd": 0.0,
        "timeout_sec": 900,
        "skim_max_files": 5,
        "skim_max_lines": 200,
    },
    "git": {
        "remote": "origin",
        "branch": "master",
        "push": False,
        "push_even_on_failure": True,
        "commit_prefix": "journal:",
    },
    "sync": {
        "export_prefix": "vm-daily-",
        "cursor_file": ".export-state",
        "ingest_glob": "*.md",
        "mirror": False,
    },
    "log": {
        "file": "auto",
        "level": "info",
    },
}

# (section, key) or bare top-level key that must resolve to a truthy value.
_REQUIRED: list[Any] = ["role", ("paths", "data_dir"), ("paths", "shared_dir")]

# Reserved for future phases (spec.md §15) — present as commented-out stubs in
# the shipped config files. Not validated further if a user uncomments one
# early; only genuinely unrecognized keys get a warning.
_KNOWN_FUTURE_SECTIONS = {"store", "publish", "mcp"}


def load(
    config_path: Path,
    *,
    role_override: Optional[str] = None,
    tool_repo_root_dir: Optional[Path] = None,
) -> Config:
    """Load a `Config` from `config_path`.

    Precedence (highest first): `role_override` (from `--role`) > a sibling
    `local.toml` (gitignored per-machine override, if present) > the config
    file itself > `DEFAULTS`. `local.toml`'s whole purpose is to override the
    checked-in role file per-machine, so it deliberately outranks it.
    Environment-variable overrides (`DDP_DIARY_*`) are intentionally not
    implemented in v1 — see spec.md §7's precedence note; add here if that
    becomes necessary.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise ConfigError(f"config file not found: {config_path}")

    raw = _load_toml(config_path)

    local_path = config_path.parent / "local.toml"
    if local_path.exists():
        raw = _deep_merge(raw, _load_toml(local_path))

    _warn_unknown_keys(raw, DEFAULTS, config_path)

    merged = _deep_merge(copy.deepcopy(DEFAULTS), raw)

    if role_override:
        merged["role"] = role_override

    _validate_required(merged, config_path)

    role = merged["role"]
    if role not in ("host", "vm"):
        raise ConfigError(f"role must be 'host' or 'vm', got {role!r} (from {config_path})")

    repo_root = tool_repo_root_dir or _paths.tool_repo_root(config_path)
    rel_to = config_path.parent

    paths_raw = merged["paths"]
    data_dir = _paths.expand(paths_raw["data_dir"], relative_to=rel_to)
    shared_dir = _paths.expand(paths_raw["shared_dir"], relative_to=rel_to)

    claude_projects_raw = paths_raw["claude_projects"]
    claude_projects = (
        _paths.default_claude_projects()
        if claude_projects_raw == "auto"
        else _paths.expand(claude_projects_raw, relative_to=rel_to)
    )

    scratch_dir_raw = paths_raw["scratch_dir"]
    scratch_dir = (
        _paths.default_scratch_dir(repo_root)
        if scratch_dir_raw == "auto"
        else _paths.expand(scratch_dir_raw, relative_to=rel_to)
    )
    scratch_dir.mkdir(parents=True, exist_ok=True)

    claude_raw = merged["claude"]
    claude_bin = _paths.resolve_claude_bin(claude_raw["bin"])
    add_dirs = [_paths.expand(p, relative_to=rel_to) for p in claude_raw.get("add_dirs", [])]

    log_raw = merged["log"]
    log_file_raw = log_raw["file"]
    log_file = (
        scratch_dir / "ddp-diary.log"
        if log_file_raw == "auto"
        else _paths.expand(log_file_raw, relative_to=rel_to)
    )

    limits_raw = merged["limits"]
    git_raw = merged["git"]
    sync_raw = merged["sync"]

    return Config(
        role=role,
        data_dir=data_dir,
        shared_dir=shared_dir,
        claude_projects=claude_projects,
        scratch_dir=scratch_dir,
        claude=ClaudeConfig(
            bin=claude_bin,
            model=claude_raw["model"],
            output_format=claude_raw["output_format"],
            allowed_tools=list(claude_raw["allowed_tools"]),
            add_dirs=add_dirs,
        ),
        limits=LimitsConfig(
            max_turns=int(limits_raw["max_turns"]),
            max_budget_usd=float(limits_raw["max_budget_usd"]),
            timeout_sec=int(limits_raw["timeout_sec"]),
            skim_max_files=int(limits_raw["skim_max_files"]),
            skim_max_lines=int(limits_raw["skim_max_lines"]),
        ),
        git=GitConfig(
            remote=git_raw["remote"],
            branch=git_raw["branch"],
            push=bool(git_raw["push"]),
            push_even_on_failure=bool(git_raw["push_even_on_failure"]),
            commit_prefix=git_raw["commit_prefix"],
        ),
        sync=SyncConfig(
            export_prefix=sync_raw["export_prefix"],
            cursor_file=sync_raw["cursor_file"],
            ingest_glob=sync_raw["ingest_glob"],
            mirror=bool(sync_raw["mirror"]),
        ),
        log=LogConfig(file=log_file, level=log_raw["level"]),
        config_path=config_path,
    )


def _load_toml(path: Path) -> dict:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except Exception as exc:  # tomllib raises TOMLDecodeError; keep this broad but explicit
        raise ConfigError(f"failed to parse {path}: {exc}") from exc


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _warn_unknown_keys(raw: dict, defaults: dict, config_path: Path, *, _prefix: str = "") -> None:
    """Warn (stderr) on any TOML key not recognized in `DEFAULTS` — a typo'd
    or extraneous key would otherwise be silently accepted and ignored
    (spec.md §7's validation claim)."""
    for key, value in raw.items():
        full_key = f"{_prefix}.{key}" if _prefix else key
        if not _prefix and key in _KNOWN_FUTURE_SECTIONS:
            continue
        if key not in defaults:
            print(f"warning: unknown config key '{full_key}' in {config_path}", file=sys.stderr)
            continue
        if isinstance(value, dict) and isinstance(defaults.get(key), dict):
            _warn_unknown_keys(value, defaults[key], config_path, _prefix=full_key)


def _validate_required(merged: dict, config_path: Path) -> None:
    missing = []
    for key in _REQUIRED:
        if isinstance(key, tuple):
            section, name = key
            if not merged.get(section, {}).get(name):
                missing.append(f"{section}.{name}")
        else:
            if not merged.get(key):
                missing.append(key)
    if missing:
        raise ConfigError(
            f"missing required config key(s) in {config_path}: {', '.join(missing)}"
        )
