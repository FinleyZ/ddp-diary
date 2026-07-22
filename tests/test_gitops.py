"""Tests for gitops.py: commit (skip-if-empty) and push (spec.md §12)."""

from __future__ import annotations

import subprocess

import pytest

from ddp_diary import gitops
from ddp_diary.errors import GitCommitError
from ddp_diary.models import GitConfig


def _git_cfg(**overrides) -> GitConfig:
    base = dict(remote="origin", branch="master", push=False, push_even_on_failure=True, commit_prefix="journal:")
    base.update(overrides)
    return GitConfig(**base)


def test_commit_creates_commit_when_something_staged(data_repo):
    (data_repo / "daily" / "2026-07-21.md").write_text("# entry", encoding="utf-8")

    committed = gitops.commit(data_repo, _git_cfg(), scope="daily", date_str="2026-07-21")

    assert committed is True
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=str(data_repo), capture_output=True, text=True).stdout
    assert "journal: daily 2026-07-21" in log


def test_commit_returns_false_when_nothing_staged(data_repo):
    assert gitops.commit(data_repo, _git_cfg(), scope="daily", date_str="2026-07-21") is False


def test_commit_is_idempotent_on_repeat_call(data_repo):
    (data_repo / "daily" / "2026-07-21.md").write_text("# entry", encoding="utf-8")

    first = gitops.commit(data_repo, _git_cfg(), scope="daily", date_str="2026-07-21")
    second = gitops.commit(data_repo, _git_cfg(), scope="daily", date_str="2026-07-21")

    assert first is True
    assert second is False  # nothing new to stage the second time


def test_commit_raises_on_invalid_repo(tmp_path):
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    with pytest.raises(GitCommitError):
        gitops.commit(not_a_repo, _git_cfg(), scope="daily", date_str="2026-07-21")


def test_push_is_noop_when_push_disabled(data_repo):
    ok, err = gitops.push(data_repo, _git_cfg(push=False))
    assert ok is True
    assert err is None


def test_push_fails_gracefully_with_no_remote(data_repo):
    ok, err = gitops.push(data_repo, _git_cfg(push=True))
    assert ok is False
    assert err  # some error message, but never raises
