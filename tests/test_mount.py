"""Tests for mount.py: the shared-folder availability probe (spec.md §10)."""

from __future__ import annotations

from ddp_diary import mount


def test_available_when_dir_is_writable(tmp_path):
    assert mount.is_available(tmp_path) is True


def test_unavailable_when_path_does_not_exist(tmp_path):
    assert mount.is_available(tmp_path / "does-not-exist") is False


def test_unavailable_when_path_is_a_file_not_a_directory(tmp_path):
    f = tmp_path / "a_file.txt"
    f.write_text("x", encoding="utf-8")
    assert mount.is_available(f) is False


def test_probe_file_is_cleaned_up(tmp_path):
    mount.is_available(tmp_path)
    leftovers = list(tmp_path.glob(".ddp-diary-probe-*"))
    assert leftovers == []
