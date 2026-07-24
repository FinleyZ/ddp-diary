"""Tests for status.py: the one-glance "did it work" report (spec.md §9)."""

from __future__ import annotations

import datetime

from ddp_diary import status


def test_status_returns_zero_and_prints_role(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config, capsys):
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    code = status.run(cfg)

    assert code == 0
    assert "role: host" in capsys.readouterr().out


def test_status_data_dir_missing_returns_exit_code_1(shared_dir, scratch_dir, claude_projects_dir, make_config, tmp_path, capsys):
    missing_data = tmp_path / "no-such-data-dir"
    cfg = make_config(role="host", data_dir=missing_data, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    code = status.run(cfg)

    assert code == 1
    assert "error:" in capsys.readouterr().out


def test_status_reports_no_entry_found_when_daily_dir_empty(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config, capsys):
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    status.run(cfg)

    assert "latest daily entry: none found" in capsys.readouterr().out


def test_status_reports_days_since_last_entry(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config, capsys):
    three_days_ago = datetime.date.today() - datetime.timedelta(days=3)
    (data_repo / "daily" / f"{three_days_ago.isoformat()}.md").write_text("# entry", encoding="utf-8")
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    status.run(cfg)

    out = capsys.readouterr().out
    assert three_days_ago.isoformat() in out
    assert "3 days ago" in out


def test_status_reports_today_label_for_todays_entry(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config, capsys):
    today = datetime.date.today()
    (data_repo / "daily" / f"{today.isoformat()}.md").write_text("# entry", encoding="utf-8")
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    status.run(cfg)

    assert "(today)" in capsys.readouterr().out


def test_status_reports_no_log_found_yet(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config, capsys):
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    status.run(cfg)

    assert "last run: no log found yet" in capsys.readouterr().out


def test_status_reports_last_run_failure_from_log_scan(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config, capsys):
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    cfg.log.file.parent.mkdir(parents=True, exist_ok=True)
    cfg.log.file.write_text(
        "===== daily started 2026-07-23 21:00:00 =====\n"
        "FAILED daily: claude exited 1: boom 2026-07-23 21:00:10\n"
        "===== daily ended 2026-07-23 21:00:10 =====\n",
        encoding="utf-8",
    )

    status.run(cfg)

    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "daily started 2026-07-23 21:00:00" in out


def test_status_reports_last_run_success_with_cost_detail(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config, capsys):
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    cfg.log.file.parent.mkdir(parents=True, exist_ok=True)
    cfg.log.file.write_text(
        "===== daily started 2026-07-23 21:00:00 =====\n"
        "COST: 0.5638 USD, 5 turns, 75s\n"
        "===== daily ended 2026-07-23 21:01:15 =====\n",
        encoding="utf-8",
    )
    cost_log = cfg.log.file.with_suffix(".cost.jsonl")
    cost_log.write_text(
        '{"timestamp": "2026-07-23 21:01:15", "role": "host", "job": "daily", "date": "2026-07-23", '
        '"model": "sonnet", "total_cost_usd": 0.5638, "num_turns": 5, "duration_ms": 75000}\n',
        encoding="utf-8",
    )

    status.run(cfg)

    out = capsys.readouterr().out
    assert "OK" in out
    assert "FAILED" not in out
    assert "0.5638" in out
    assert "5 turns" in out


def test_status_ignores_stale_cost_log_after_a_failed_run(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config, capsys):
    """Regression guard for the exact mistake caught in design review: a
    failed run must not be reported as OK just because an OLDER successful
    run's cost-log entry is still the last line in the JSONL."""
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    cfg.log.file.parent.mkdir(parents=True, exist_ok=True)
    # Stale success in the cost log from a prior night...
    cost_log = cfg.log.file.with_suffix(".cost.jsonl")
    cost_log.write_text(
        '{"timestamp": "2026-07-22 21:01:15", "total_cost_usd": 0.01, "num_turns": 1, "duration_ms": 1000}\n',
        encoding="utf-8",
    )
    # ...but the most recent run in the log actually failed (no cost line, since record_cost is never reached on failure).
    cfg.log.file.write_text(
        "===== daily started 2026-07-23 21:00:00 =====\n"
        "FAILED daily: boom 2026-07-23 21:00:05\n"
        "===== daily ended 2026-07-23 21:00:05 =====\n",
        encoding="utf-8",
    )

    status.run(cfg)

    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "0.01" not in out  # must not surface the stale success detail


def test_status_verbose_prints_resolved_config(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config, capsys):
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    status.run(cfg, verbose=True)

    out = capsys.readouterr().out
    assert "role: host" in out
    assert "backfill_days" in out
