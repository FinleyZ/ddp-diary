"""Tests for doctor.py: environment/health checks and their exit-code mapping
(spec.md §14)."""

from __future__ import annotations

from ddp_diary import doctor


def test_all_checks_pass_returns_zero(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config, capsys):
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    # claude.bin="claude" from make_config's default may not resolve on a
    # machine without claude installed — force a bin guaranteed to exist.
    import sys

    cfg = _with_claude_bin(cfg, sys.executable)

    code = doctor.run(cfg)

    assert code == 0
    out = capsys.readouterr().out
    assert "doctor: all checks passed" in out


def test_broken_claude_bin_fails_with_exit_code_3(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    cfg = _with_claude_bin(cfg, "/no/such/claude/binary/at/all")

    code = doctor.run(cfg)

    assert code == 3


def test_unwritable_scratch_dir_fails_with_exit_code_2(data_repo, shared_dir, claude_projects_dir, make_config, tmp_path):
    import sys

    # A file where a directory is expected can never be mkdir'd/written into.
    fake_scratch = tmp_path / "scratch-is-a-file"
    fake_scratch.write_text("x", encoding="utf-8")

    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=fake_scratch, claude_projects=claude_projects_dir)
    cfg = _with_claude_bin(cfg, sys.executable)

    code = doctor.run(cfg)

    assert code == 2


def test_missing_share_is_a_warning_not_a_failure(data_repo, scratch_dir, claude_projects_dir, make_config, tmp_path):
    import sys

    missing_share = tmp_path / "no-such-share"
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=missing_share, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    cfg = _with_claude_bin(cfg, sys.executable)

    code = doctor.run(cfg)

    assert code == 0  # WARN, not FAIL — spec.md §10's soft-skip philosophy


def test_git_remote_check_only_runs_when_push_is_enabled(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config, capsys):
    import sys

    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir, push=False)
    cfg = _with_claude_bin(cfg, sys.executable)

    doctor.run(cfg)

    assert "git remote reachable" not in capsys.readouterr().out


def test_git_remote_unreachable_fails_with_exit_code_5_when_push_enabled(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    import sys

    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir, push=True)
    cfg = _with_claude_bin(cfg, sys.executable)

    code = doctor.run(cfg)

    assert code == 5  # data_repo fixture has no remote configured


def test_verbose_prints_resolved_config(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config, capsys):
    import sys

    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    cfg = _with_claude_bin(cfg, sys.executable)

    doctor.run(cfg, verbose=True)

    out = capsys.readouterr().out
    assert "role: vm" in out
    assert str(data_repo) in out


def _with_claude_bin(cfg, bin_path: str):
    """Return a copy of `cfg` with `claude.bin` replaced — `Config`/`ClaudeConfig`
    are frozen dataclasses, so this rebuilds rather than mutates."""
    import dataclasses

    new_claude = dataclasses.replace(cfg.claude, bin=bin_path)
    return dataclasses.replace(cfg, claude=new_claude)
