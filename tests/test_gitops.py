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


# --- read_status (spec.md §9, for `ddp-diary status`) ----------------------


def test_read_status_reports_dirty_when_uncommitted_changes_present(data_repo):
    (data_repo / "daily" / "2026-07-22.md").write_text("# uncommitted", encoding="utf-8")

    st = gitops.read_status(data_repo)

    assert st.is_dirty is True


def test_read_status_reports_clean_when_nothing_uncommitted(data_repo):
    st = gitops.read_status(data_repo)

    assert st.is_dirty is False


def test_read_status_ahead_behind_none_when_no_upstream(data_repo):
    st = gitops.read_status(data_repo)

    assert st.ahead is None
    assert st.behind is None


def test_read_status_reports_ahead_count_with_a_tracked_upstream(tmp_path, data_repo):
    bare = tmp_path / "bare-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=str(data_repo), check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "master"], cwd=str(data_repo), check=True, capture_output=True)

    (data_repo / "daily" / "2026-07-22.md").write_text("# entry", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(data_repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "unpushed commit"], cwd=str(data_repo), check=True)

    st = gitops.read_status(data_repo)

    assert st.ahead == 1
    assert st.behind == 0


def test_read_status_reports_last_commit_subject_and_date(data_repo):
    st = gitops.read_status(data_repo)

    assert st.last_commit_subject == "init"
    assert st.last_commit_date is not None


def test_read_status_never_raises_on_non_repo_dir(tmp_path):
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()

    st = gitops.read_status(not_a_repo)  # must not raise

    assert st.is_dirty is None
    assert st.ahead is None
    assert st.behind is None
    assert st.last_commit_subject is None
    assert st.last_commit_date is None
