"""Tests for sync/export.py: VM-side copy-to-share with cursor tracking
(spec.md §11)."""

from __future__ import annotations

import shutil

from ddp_diary.sync import export


def test_export_with_no_cursor_exports_only_most_recent(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    (data_repo / "daily" / "2026-07-18.md").write_text("day 18", encoding="utf-8")
    (data_repo / "daily" / "2026-07-19.md").write_text("day 19", encoding="utf-8")

    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    exported = export.run(cfg)

    assert exported == ["2026-07-19.md"]
    assert (shared_dir / "vm-daily-2026-07-19.md").exists()
    assert not (shared_dir / "vm-daily-2026-07-18.md").exists()  # never exported, by design
    assert (scratch_dir / ".export-state").read_text(encoding="utf-8") == "2026-07-19.md"


def test_export_is_idempotent_when_nothing_new(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    (data_repo / "daily" / "2026-07-19.md").write_text("day 19", encoding="utf-8")
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    first = export.run(cfg)
    second = export.run(cfg)

    assert first == ["2026-07-19.md"]
    assert second == []


def test_export_picks_up_incremental_new_dates(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    (data_repo / "daily" / "2026-07-19.md").write_text("day 19", encoding="utf-8")
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)
    export.run(cfg)

    (data_repo / "daily" / "2026-07-20.md").write_text("day 20", encoding="utf-8")
    second = export.run(cfg)

    assert second == ["2026-07-20.md"]
    assert (shared_dir / "vm-daily-2026-07-20.md").exists()
    assert (scratch_dir / ".export-state").read_text(encoding="utf-8") == "2026-07-20.md"


def test_export_never_deletes_or_moves_local_files(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    local = data_repo / "daily" / "2026-07-19.md"
    local.write_text("day 19", encoding="utf-8")
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    export.run(cfg)

    assert local.exists()  # copy-only — the VM's own file must survive


def test_export_ignores_non_dated_files(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    (data_repo / "daily" / "notes.md").write_text("not a dated entry", encoding="utf-8")
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    assert export.run(cfg) == []


def test_export_returns_empty_when_share_unavailable(data_repo, scratch_dir, claude_projects_dir, make_config, tmp_path):
    (data_repo / "daily" / "2026-07-19.md").write_text("day 19", encoding="utf-8")
    missing_share = tmp_path / "no-such-share"
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=missing_share, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    assert export.run(cfg) == []


def test_export_returns_empty_when_no_daily_dir(shared_dir, scratch_dir, claude_projects_dir, make_config, tmp_path):
    data_dir = tmp_path / "data-no-daily"
    data_dir.mkdir()
    cfg = make_config(role="vm", data_dir=data_dir, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    assert export.run(cfg) == []


def test_export_survives_share_vanishing_mid_run(monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    """A TOCTOU race: the share passes mount.is_available() but the actual
    copy raises OSError anyway. Must degrade gracefully — like 'share
    unavailable' — never raise, and never advance the cursor past a date that
    didn't actually make it across."""
    (data_repo / "daily" / "2026-07-19.md").write_text("day 19", encoding="utf-8")

    def fake_copyfile(src, dst):
        raise OSError("simulated share vanished mid-copy")

    monkeypatch.setattr(shutil, "copyfile", fake_copyfile)

    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    exported = export.run(cfg)  # must not raise

    assert exported == []
    assert not (scratch_dir / ".export-state").exists()  # cursor never advanced for a failed copy
