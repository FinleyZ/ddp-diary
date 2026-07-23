"""Tests for config.py: TOML load / validate / resolve (spec.md §7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ddp_diary import config as config_module
from ddp_diary.errors import ConfigError


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_valid_config_applies_defaults(tmp_path):
    data_dir = tmp_path / "data"
    shared_dir = tmp_path / "share"
    data_dir.mkdir()
    shared_dir.mkdir()
    cfg_path = _write(
        tmp_path / "host.toml",
        f'role = "host"\n[paths]\ndata_dir = "{data_dir.as_posix()}"\nshared_dir = "{shared_dir.as_posix()}"\n',
    )

    cfg = config_module.load(cfg_path)

    assert cfg.role == "host"
    assert cfg.data_dir == data_dir.resolve()
    assert cfg.shared_dir == shared_dir.resolve()
    assert cfg.claude.model == "sonnet"
    assert cfg.git.branch == "master"
    assert cfg.limits.skim_max_files == 5
    assert cfg.limits.max_budget_usd == 0


def test_missing_config_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        config_module.load(tmp_path / "nope.toml")


def test_missing_required_key_raises(tmp_path):
    cfg_path = _write(tmp_path / "bad.toml", 'role = "host"\n')
    with pytest.raises(ConfigError, match="paths.data_dir"):
        config_module.load(cfg_path)


def test_invalid_role_raises(tmp_path):
    data_dir = tmp_path / "data"
    shared_dir = tmp_path / "share"
    data_dir.mkdir()
    shared_dir.mkdir()
    cfg_path = _write(
        tmp_path / "bad.toml",
        f'role = "cloud"\n[paths]\ndata_dir = "{data_dir.as_posix()}"\nshared_dir = "{shared_dir.as_posix()}"\n',
    )
    with pytest.raises(ConfigError, match="'host' or 'vm'"):
        config_module.load(cfg_path)


def test_role_override_wins_over_file(tmp_path):
    data_dir = tmp_path / "data"
    shared_dir = tmp_path / "share"
    data_dir.mkdir()
    shared_dir.mkdir()
    cfg_path = _write(
        tmp_path / "host.toml",
        f'role = "host"\n[paths]\ndata_dir = "{data_dir.as_posix()}"\nshared_dir = "{shared_dir.as_posix()}"\n',
    )
    cfg = config_module.load(cfg_path, role_override="vm")
    assert cfg.role == "vm"


def test_local_toml_overrides_without_touching_other_keys(tmp_path):
    data_dir = tmp_path / "data"
    shared_dir = tmp_path / "share"
    override_dir = tmp_path / "override-data"
    for d in (data_dir, shared_dir, override_dir):
        d.mkdir()
    cfg_path = _write(
        tmp_path / "host.toml",
        f'role = "host"\n[paths]\ndata_dir = "{data_dir.as_posix()}"\nshared_dir = "{shared_dir.as_posix()}"\n',
    )
    _write(tmp_path / "local.toml", f'[paths]\ndata_dir = "{override_dir.as_posix()}"\n')

    cfg = config_module.load(cfg_path)

    assert cfg.data_dir == override_dir.resolve()
    assert cfg.shared_dir == shared_dir.resolve()  # untouched by local.toml


def test_scratch_dir_auto_resolves_under_tool_repo(tmp_path):
    # Simulates a tool repo layout: <repo>/config/host.toml
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    data_dir = tmp_path / "data"
    shared_dir = tmp_path / "share"
    data_dir.mkdir()
    shared_dir.mkdir()
    cfg_path = _write(
        repo / "config" / "host.toml",
        f'role = "host"\n[paths]\ndata_dir = "{data_dir.as_posix()}"\nshared_dir = "{shared_dir.as_posix()}"\n',
    )

    cfg = config_module.load(cfg_path)

    assert cfg.scratch_dir == (repo / "state").resolve()
    assert cfg.scratch_dir.is_dir()  # config.load() creates it


def test_unknown_top_level_key_warns(tmp_path, capsys):
    data_dir = tmp_path / "data"
    shared_dir = tmp_path / "share"
    data_dir.mkdir()
    shared_dir.mkdir()
    cfg_path = _write(
        tmp_path / "host.toml",
        f'role = "host"\ntypo_section = "oops"\n[paths]\ndata_dir = "{data_dir.as_posix()}"\nshared_dir = "{shared_dir.as_posix()}"\n',
    )

    config_module.load(cfg_path)

    err = capsys.readouterr().err
    assert "unknown config key 'typo_section'" in err


def test_unknown_nested_key_warns_with_dotted_path(tmp_path, capsys):
    data_dir = tmp_path / "data"
    shared_dir = tmp_path / "share"
    data_dir.mkdir()
    shared_dir.mkdir()
    cfg_path = _write(
        tmp_path / "host.toml",
        f'role = "host"\n[paths]\ndata_dir = "{data_dir.as_posix()}"\nshared_dir = "{shared_dir.as_posix()}"\n[claude]\nmodle = "sonnet"\n',
    )

    config_module.load(cfg_path)

    err = capsys.readouterr().err
    assert "unknown config key 'claude.modle'" in err


def test_known_future_sections_do_not_warn(tmp_path, capsys):
    data_dir = tmp_path / "data"
    shared_dir = tmp_path / "share"
    data_dir.mkdir()
    shared_dir.mkdir()
    cfg_path = _write(
        tmp_path / "host.toml",
        f'role = "host"\n[paths]\ndata_dir = "{data_dir.as_posix()}"\nshared_dir = "{shared_dir.as_posix()}"\n[store]\nbackend = "sqlite"\n',
    )

    config_module.load(cfg_path)

    err = capsys.readouterr().err
    assert "unknown config key" not in err


def test_local_toml_wins_over_role_config_by_design(tmp_path):
    """local.toml's whole purpose is a per-machine override — it must outrank
    the checked-in role config file, matching spec.md §7's corrected precedence
    (CLI flag > local.toml > role config file > defaults)."""
    data_dir = tmp_path / "data"
    shared_dir = tmp_path / "share"
    override_dir = tmp_path / "override-data"
    for d in (data_dir, shared_dir, override_dir):
        d.mkdir()
    cfg_path = _write(
        tmp_path / "host.toml",
        f'role = "host"\n[paths]\ndata_dir = "{data_dir.as_posix()}"\nshared_dir = "{shared_dir.as_posix()}"\n',
    )
    _write(tmp_path / "local.toml", f'[paths]\ndata_dir = "{override_dir.as_posix()}"\n')

    cfg = config_module.load(cfg_path)

    assert cfg.data_dir == override_dir.resolve()


def test_config_dir_unset_defaults_to_none_and_claude_projects_uses_home(tmp_path):
    data_dir = tmp_path / "data"
    shared_dir = tmp_path / "share"
    data_dir.mkdir()
    shared_dir.mkdir()
    cfg_path = _write(
        tmp_path / "host.toml",
        f'role = "host"\n[paths]\ndata_dir = "{data_dir.as_posix()}"\nshared_dir = "{shared_dir.as_posix()}"\n',
    )

    cfg = config_module.load(cfg_path)

    assert cfg.claude.config_dir is None
    assert cfg.claude_projects == (Path.home() / ".claude" / "projects").resolve()


def test_config_dir_set_pins_it_and_derives_claude_projects(tmp_path):
    data_dir = tmp_path / "data"
    shared_dir = tmp_path / "share"
    pinned = tmp_path / ".claude-personal"
    for d in (data_dir, shared_dir, pinned):
        d.mkdir()
    cfg_path = _write(
        tmp_path / "host.toml",
        f'''role = "host"
[paths]
data_dir = "{data_dir.as_posix()}"
shared_dir = "{shared_dir.as_posix()}"

[claude]
config_dir = "{pinned.as_posix()}"
''',
    )

    cfg = config_module.load(cfg_path)

    assert cfg.claude.config_dir == pinned.resolve()
    # "auto" claude_projects now derives from the pinned config dir, not ~/.claude
    assert cfg.claude_projects == pinned.resolve() / "projects"


def test_explicit_claude_projects_overrides_config_dir_derivation(tmp_path):
    data_dir = tmp_path / "data"
    shared_dir = tmp_path / "share"
    pinned = tmp_path / ".claude-personal"
    explicit_projects = tmp_path / "elsewhere" / "projects"
    for d in (data_dir, shared_dir, pinned):
        d.mkdir()
    cfg_path = _write(
        tmp_path / "host.toml",
        f'''role = "host"
[paths]
data_dir = "{data_dir.as_posix()}"
shared_dir = "{shared_dir.as_posix()}"
claude_projects = "{explicit_projects.as_posix()}"

[claude]
config_dir = "{pinned.as_posix()}"
''',
    )

    cfg = config_module.load(cfg_path)

    # An explicit claude_projects wins over the config_dir-derived default.
    assert cfg.claude_projects == explicit_projects.resolve()
    assert cfg.claude.config_dir == pinned.resolve()


def test_explicit_allowed_tools_and_limits_are_respected(tmp_path):
    data_dir = tmp_path / "data"
    shared_dir = tmp_path / "share"
    data_dir.mkdir()
    shared_dir.mkdir()
    cfg_path = _write(
        tmp_path / "vm.toml",
        f'''role = "vm"
[paths]
data_dir = "{data_dir.as_posix()}"
shared_dir = "{shared_dir.as_posix()}"

[claude]
model = "claude-sonnet-5"
allowed_tools = ["Read", "Write", "Glob"]

[limits]
max_turns = 15
max_budget_usd = 1.00
''',
    )
    cfg = config_module.load(cfg_path)
    assert cfg.claude.model == "claude-sonnet-5"
    assert cfg.claude.allowed_tools == ["Read", "Write", "Glob"]
    assert cfg.limits.max_turns == 15
    assert cfg.limits.max_budget_usd == 1.00
