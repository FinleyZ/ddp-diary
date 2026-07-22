"""Tests for sync/ingest.py: host-side move-from-share (spec.md §11)."""

from __future__ import annotations

import shutil

from ddp_diary.sync import ingest


def test_ingest_moves_matching_files_and_leaves_others(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    (shared_dir / "vm-daily-2026-07-20.md").write_text("content", encoding="utf-8")
    (shared_dir / "vm-notes.md").write_text("notes", encoding="utf-8")
    (shared_dir / "cron.log").write_text("not markdown", encoding="utf-8")  # must NOT be ingested

    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    result = ingest.run(cfg)

    assert set(result.ingested) == {"vm-daily-2026-07-20.md", "vm-notes.md"}
    assert result.skipped_conflicts == []
    assert (data_repo / "inbox" / "vm-daily-2026-07-20.md").exists()
    assert (data_repo / "inbox" / "vm-notes.md").exists()
    assert not (shared_dir / "vm-daily-2026-07-20.md").exists()  # moved, not copied
    assert (shared_dir / "cron.log").exists()  # non-.md left untouched


def test_ingest_does_not_recurse_into_subdirectories(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    subdir = shared_dir / "journal"
    subdir.mkdir()
    (subdir / "nested.md").write_text("should not be ingested", encoding="utf-8")

    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    result = ingest.run(cfg)

    assert result.ingested == []
    assert (subdir / "nested.md").exists()


def test_ingest_returns_empty_when_share_unavailable(data_repo, scratch_dir, claude_projects_dir, make_config, tmp_path):
    missing_share = tmp_path / "no-such-share"
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=missing_share, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    result = ingest.run(cfg)

    assert result.ingested == []
    assert result.skipped_conflicts == []


def test_ingest_creates_inbox_dir_if_missing(shared_dir, scratch_dir, claude_projects_dir, make_config, tmp_path):
    data_dir = tmp_path / "data-no-inbox"
    data_dir.mkdir()
    (shared_dir / "a.md").write_text("x", encoding="utf-8")

    cfg = make_config(role="host", data_dir=data_dir, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    result = ingest.run(cfg)

    assert result.ingested == ["a.md"]
    assert (data_dir / "inbox" / "a.md").exists()


def test_ingest_returns_empty_when_share_has_nothing_new(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    result = ingest.run(cfg)
    assert result.ingested == []
    assert result.skipped_conflicts == []


def test_ingest_skips_and_reports_conflict_instead_of_overwriting(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    """spec.md §11's ingest-conflict rule: a share file that would overwrite an
    existing, not-yet-processed inbox/ entry must be skipped and reported,
    never silently clobbered."""
    (data_repo / "inbox" / "vm-daily-2026-07-20.md").write_text("ORIGINAL not-yet-processed content", encoding="utf-8")
    (shared_dir / "vm-daily-2026-07-20.md").write_text("NEW conflicting content", encoding="utf-8")

    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    result = ingest.run(cfg)

    assert result.ingested == []
    assert result.skipped_conflicts == ["vm-daily-2026-07-20.md"]
    # the original, not-yet-processed content must survive untouched
    assert (data_repo / "inbox" / "vm-daily-2026-07-20.md").read_text(encoding="utf-8") == "ORIGINAL not-yet-processed content"
    # the conflicting file is left on the share rather than lost
    assert (shared_dir / "vm-daily-2026-07-20.md").read_text(encoding="utf-8") == "NEW conflicting content"


def test_ingest_survives_share_vanishing_mid_run(monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    """A TOCTOU race: the share passes mount.is_available() but the actual
    move raises OSError anyway (e.g. it was unmounted a moment later). This
    must degrade gracefully — like 'share unavailable' — never raise."""
    (shared_dir / "a.md").write_text("x", encoding="utf-8")
    (shared_dir / "b.md").write_text("y", encoding="utf-8")

    def fake_move(src, dst):
        raise OSError("simulated share vanished mid-move")

    monkeypatch.setattr(shutil, "move", fake_move)

    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    result = ingest.run(cfg)  # must not raise

    assert result.ingested == []
    assert (shared_dir / "a.md").exists()  # untouched — the failed move didn't partially apply
