"""Tests for cli.py: argument parsing, dispatch, and exit-code mapping
(spec.md §9). `claude_client.run` is monkeypatched where a `run`/`backfill`
invocation would otherwise need a real `claude` process."""

from __future__ import annotations

import datetime

import pytest

from ddp_diary import cli, claude_client, runner
from ddp_diary.models import RunResult


def _config_path(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, *, role="host", push=False):
    import subprocess
    import sys

    claude_bin = sys.executable.replace("\\", "/")
    cfg_text = f'''role = "{role}"
[paths]
data_dir = "{str(data_repo).replace(chr(92), "/")}"
shared_dir = "{str(shared_dir).replace(chr(92), "/")}"
claude_projects = "{str(claude_projects_dir).replace(chr(92), "/")}"
scratch_dir = "{str(scratch_dir).replace(chr(92), "/")}"

[claude]
bin = "{claude_bin}"

[git]
push = {"true" if push else "false"}
'''
    path = tmp_path / f"{role}.toml"
    path.write_text(cfg_text, encoding="utf-8")
    return path


def test_version_command_prints_version(capsys):
    from ddp_diary import __version__

    code = cli.main(["version"])

    assert code == 0
    assert __version__ in capsys.readouterr().out


def test_missing_config_file_returns_exit_code_2(capsys):
    code = cli.main(["doctor", "--config", "/no/such/config.toml"])

    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_run_dry_run_via_cli_returns_zero(monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, capsys):
    cfg_path = _config_path(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path)

    code = cli.main(["run", "--job", "daily", "--config", str(cfg_path), "--dry-run", "--date", "2026-07-20"])

    assert code == 0


def test_backfill_processes_each_day_in_range(monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path):
    calls = []

    def fake_claude_run(prompt_text, *, claude_cfg, limits, cwd):
        calls.append(1)
        (cwd / "daily" / f"2026-07-1{len(calls)}.md").write_text("# entry\n", encoding="utf-8")
        return RunResult(ok=True, result_text="ok", total_cost_usd=0.01, num_turns=1, duration_ms=10, raw_stdout="", raw_stderr="", exit_code=0)

    monkeypatch.setattr(claude_client, "run", fake_claude_run)
    cfg_path = _config_path(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, role="vm")

    code = cli.main(["backfill", "--config", str(cfg_path), "--from", "2026-07-18", "--to", "2026-07-19"])

    assert code == 0
    assert len(calls) == 2  # one per day in [--from, --to]


def test_backfill_from_after_to_is_a_clean_config_error(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, capsys):
    cfg_path = _config_path(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path)

    code = cli.main(["backfill", "--config", str(cfg_path), "--from", "2026-07-20", "--to", "2026-07-10"])

    assert code == 2  # ConfigError — a bad argument range, not an "unexpected" failure
    assert "error:" in capsys.readouterr().err


def test_sync_raises_exit_code_6_when_share_unavailable(data_repo, scratch_dir, claude_projects_dir, tmp_path, capsys):
    missing_share = tmp_path / "no-such-share"
    cfg_path = _config_path(data_repo, missing_share, scratch_dir, claude_projects_dir, tmp_path)

    code = cli.main(["sync", "--config", str(cfg_path)])

    assert code == 6
    assert "shared folder unavailable" in capsys.readouterr().err


def test_sync_host_role_ingests_by_default(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path):
    (shared_dir / "a.md").write_text("x", encoding="utf-8")
    cfg_path = _config_path(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, role="host")

    code = cli.main(["sync", "--config", str(cfg_path)])

    assert code == 0
    assert (data_repo / "inbox" / "a.md").exists()


def test_doctor_dispatches_and_returns_its_exit_code(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path):
    cfg_path = _config_path(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, role="vm")

    code = cli.main(["doctor", "--config", str(cfg_path)])

    assert code == 0  # claude.bin points at a real python executable; share/git-remote are WARN-only for vm


def test_status_command_dispatches_and_returns_zero(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, capsys):
    cfg_path = _config_path(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, role="host")

    code = cli.main(["status", "--config", str(cfg_path)])

    assert code == 0
    assert "role: host" in capsys.readouterr().out


def test_run_daily_without_date_dispatches_through_backfill_wrapper(monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path):
    calls = []
    monkeypatch.setattr(runner, "run_daily_with_backfill", lambda cfg, **kw: calls.append("backfill_wrapper"))
    monkeypatch.setattr(runner, "run_job", lambda cfg, job, **kw: calls.append("plain_run_job"))

    cfg_path = _config_path(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, role="host")
    code = cli.main(["run", "--job", "daily", "--config", str(cfg_path)])  # no --date

    assert code == 0
    assert calls == ["backfill_wrapper"]


def test_run_daily_with_explicit_date_bypasses_backfill_wrapper(monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path):
    calls = []
    monkeypatch.setattr(runner, "run_daily_with_backfill", lambda cfg, **kw: calls.append("backfill_wrapper"))
    monkeypatch.setattr(runner, "run_job", lambda cfg, job, **kw: calls.append("plain_run_job"))

    cfg_path = _config_path(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, role="host")
    code = cli.main(["run", "--job", "daily", "--config", str(cfg_path), "--date", "today"])

    assert code == 0
    assert calls == ["plain_run_job"]


def test_run_weekly_bypasses_backfill_wrapper_even_without_date(monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path):
    calls = []
    monkeypatch.setattr(runner, "run_daily_with_backfill", lambda cfg, **kw: calls.append("backfill_wrapper"))
    monkeypatch.setattr(runner, "run_job", lambda cfg, job, **kw: calls.append("plain_run_job"))

    cfg_path = _config_path(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, role="host")
    code = cli.main(["run", "--job", "weekly", "--config", str(cfg_path)])

    assert code == 0
    assert calls == ["plain_run_job"]


def test_date_accepts_today_and_yesterday_aliases_case_insensitively():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    assert cli._parse_date("today") == today
    assert cli._parse_date("TODAY") == today
    assert cli._parse_date("Today") == today
    assert cli._parse_date("yesterday") == yesterday
    assert cli._parse_date("YESTERDAY") == yesterday
    assert cli._parse_date("2026-07-20") == datetime.date(2026, 7, 20)


def test_bad_date_format_returns_exit_code_2_not_1(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, capsys):
    cfg_path = _config_path(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, role="host")

    code = cli.main(["run", "--job", "daily", "--config", str(cfg_path), "--date", "not-a-date"])

    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_backfill_from_and_to_accept_relative_aliases(monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path):
    calls = []

    def fake_claude_run(prompt_text, *, claude_cfg, limits, cwd):
        calls.append(1)
        return RunResult(ok=True, result_text="ok", total_cost_usd=0.01, num_turns=1, duration_ms=10, raw_stdout="", raw_stderr="", exit_code=0)

    monkeypatch.setattr(claude_client, "run", fake_claude_run)
    cfg_path = _config_path(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, role="vm")

    code = cli.main(["backfill", "--config", str(cfg_path), "--from", "yesterday", "--to", "today"])

    assert code == 0
    assert len(calls) == 2


def test_unexpected_exception_never_leaks_a_traceback(monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, capsys):
    """A bare, non-DdpDiaryError exception anywhere in the dispatch must still
    produce a clean `error: ...` message and exit code 1 — never a raw
    traceback in what's normally an unattended cron/Task-Scheduler run."""

    def boom(*args, **kwargs):
        raise RuntimeError("something truly unexpected")

    monkeypatch.setattr(claude_client, "run", boom)
    cfg_path = _config_path(data_repo, shared_dir, scratch_dir, claude_projects_dir, tmp_path, role="vm")

    code = cli.main(["run", "--job", "daily", "--config", str(cfg_path), "--date", "2026-07-20"])

    assert code == 1
    err = capsys.readouterr().err
    assert "error: something truly unexpected" in err
    assert "Traceback" not in err
