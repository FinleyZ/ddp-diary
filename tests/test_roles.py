"""Tests for roles.py: the two Role hooks that differ between host and vm
(spec.md §5). Exercised against real tmp-dir configs — `sync.ingest`/
`sync.export` are already unit-tested and cheap to run for real here."""

from __future__ import annotations

import datetime

import pytest

from ddp_diary import roles
from ddp_diary.models import RunContext


def test_host_role_ingests_on_daily_job(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    (shared_dir / "vm-daily-2026-07-20.md").write_text("x", encoding="utf-8")
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    ctx = RunContext(config=cfg, job="daily", target_date=datetime.date(2026, 7, 20))

    roles.HostRole().before_run(ctx)

    assert (data_repo / "inbox" / "vm-daily-2026-07-20.md").exists()


def test_host_role_skips_ingest_on_weekly_job(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    (shared_dir / "vm-daily-2026-07-20.md").write_text("x", encoding="utf-8")
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    ctx = RunContext(config=cfg, job="weekly", target_date=datetime.date(2026, 7, 20))

    roles.HostRole().before_run(ctx)

    assert not (data_repo / "inbox" / "vm-daily-2026-07-20.md").exists()
    assert (shared_dir / "vm-daily-2026-07-20.md").exists()  # untouched


def test_host_role_dry_run_does_not_ingest(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    (shared_dir / "vm-daily-2026-07-20.md").write_text("x", encoding="utf-8")
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    ctx = RunContext(config=cfg, job="daily", target_date=datetime.date(2026, 7, 20), dry_run=True)

    roles.HostRole().before_run(ctx)

    assert (shared_dir / "vm-daily-2026-07-20.md").exists()  # never moved


def test_vm_role_exports_on_daily_job(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    (data_repo / "daily" / "2026-07-20.md").write_text("x", encoding="utf-8")
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    ctx = RunContext(config=cfg, job="daily", target_date=datetime.date(2026, 7, 20))

    roles.VmRole().after_commit(ctx)

    assert (shared_dir / "vm-daily-2026-07-20.md").exists()


def test_vm_role_skips_export_on_monthly_job(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    (data_repo / "daily" / "2026-07-20.md").write_text("x", encoding="utf-8")
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    ctx = RunContext(config=cfg, job="monthly", target_date=datetime.date(2026, 7, 20))

    roles.VmRole().after_commit(ctx)

    assert not (shared_dir / "vm-daily-2026-07-20.md").exists()


def test_vm_role_dry_run_does_not_export(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    (data_repo / "daily" / "2026-07-20.md").write_text("x", encoding="utf-8")
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    ctx = RunContext(config=cfg, job="daily", target_date=datetime.date(2026, 7, 20), dry_run=True)

    roles.VmRole().after_commit(ctx)

    assert not (shared_dir / "vm-daily-2026-07-20.md").exists()


def test_for_role_returns_correct_class():
    assert isinstance(roles.for_role("host"), roles.HostRole)
    assert isinstance(roles.for_role("vm"), roles.VmRole)


def test_for_role_raises_on_unknown_role():
    with pytest.raises(ValueError):
        roles.for_role("cloud")
