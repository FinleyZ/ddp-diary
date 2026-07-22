"""Shared pytest fixtures for the ddp_diary test suite."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ddp_diary.models import ClaudeConfig, Config, GitConfig, LimitsConfig, LogConfig, SyncConfig  # noqa: E402


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def data_repo(tmp_path: Path) -> Path:
    """A git-initialized data repo with the standard daily/weekly/monthly/inbox layout."""
    repo = tmp_path / "data"
    (repo / "daily").mkdir(parents=True)
    (repo / "weekly").mkdir()
    (repo / "monthly").mkdir()
    (repo / "inbox").mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "test@test.local", cwd=repo)
    _git("config", "user.name", "test", cwd=repo)
    (repo / ".gitkeep").write_text("", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "init", cwd=repo)
    return repo


@pytest.fixture
def shared_dir(tmp_path: Path) -> Path:
    d = tmp_path / "share"
    d.mkdir()
    return d


@pytest.fixture
def scratch_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir()
    return d


@pytest.fixture
def claude_projects_dir(tmp_path: Path) -> Path:
    d = tmp_path / "claude-projects"
    d.mkdir()
    return d


@pytest.fixture
def make_config():
    """Factory fixture: build a `Config` directly (bypassing TOML) for fast,
    focused unit tests. Returns a callable — see usage in test_sync_*.py,
    test_gitops.py, test_roles.py, test_runner.py."""

    def _make(
        *,
        role: str,
        data_dir: Path,
        shared_dir: Path,
        scratch_dir: Path,
        claude_projects: Path,
        push: bool = False,
        push_even_on_failure: bool = True,
        max_budget_usd: float = 0,
        max_turns: int = 0,
    ) -> Config:
        return Config(
            role=role,
            data_dir=data_dir,
            shared_dir=shared_dir,
            claude_projects=claude_projects,
            scratch_dir=scratch_dir,
            claude=ClaudeConfig(
                bin="claude",
                model="sonnet",
                output_format="json",
                allowed_tools=["Read", "Write"],
                add_dirs=[],
            ),
            limits=LimitsConfig(
                max_turns=max_turns,
                max_budget_usd=max_budget_usd,
                timeout_sec=900,
                skim_max_files=5,
                skim_max_lines=200,
            ),
            git=GitConfig(
                remote="origin",
                branch="master",
                push=push,
                push_even_on_failure=push_even_on_failure,
                commit_prefix="journal:",
            ),
            sync=SyncConfig(
                export_prefix="vm-daily-",
                cursor_file=".export-state",
                ingest_glob="*.md",
                mirror=False,
            ),
            log=LogConfig(file=scratch_dir / "ddp-diary.log", level="info"),
            config_path=scratch_dir / "fake.toml",
        )

    return _make
