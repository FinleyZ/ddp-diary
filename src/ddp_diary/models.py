"""Typed data structures shared across ddp_diary modules.

Kept deliberately free of any I/O or business logic — every other module imports
from here, nothing here imports from them (except `errors`, for type hints only).
"""

from __future__ import annotations

import dataclasses
import datetime
from pathlib import Path
from typing import Literal, Optional

Role = Literal["host", "vm"]
Job = Literal["daily", "weekly", "monthly"]


@dataclasses.dataclass(frozen=True)
class ClaudeConfig:
    bin: str
    model: str
    output_format: str
    allowed_tools: list[str]
    add_dirs: list[Path]
    # None = inherit the CLI's active default (~/.claude). A path pins the
    # `claude -p` invocation to that config dir via CLAUDE_CONFIG_DIR, so the
    # summarizing account is fixed regardless of what the default login is.
    config_dir: Optional[Path] = None


@dataclasses.dataclass(frozen=True)
class LimitsConfig:
    max_turns: int
    max_budget_usd: float
    timeout_sec: int
    skim_max_files: int
    skim_max_lines: int


@dataclasses.dataclass(frozen=True)
class GitConfig:
    remote: str
    branch: str
    push: bool
    push_even_on_failure: bool
    commit_prefix: str


@dataclasses.dataclass(frozen=True)
class SyncConfig:
    export_prefix: str
    cursor_file: str
    ingest_glob: str
    mirror: bool


@dataclasses.dataclass(frozen=True)
class LogConfig:
    file: Path
    level: str


@dataclasses.dataclass(frozen=True)
class Config:
    """Fully resolved configuration for one machine/role. Immutable once loaded."""

    role: Role
    data_dir: Path
    shared_dir: Path
    claude_projects: Path
    scratch_dir: Path
    claude: ClaudeConfig
    limits: LimitsConfig
    git: GitConfig
    sync: SyncConfig
    log: LogConfig
    config_path: Path


@dataclasses.dataclass
class IngestResult:
    """Outcome of one host-side ingest run (spec.md §11's ingest-conflict rule:
    a share file that would overwrite an existing `inbox/` entry is skipped and
    reported, never silently clobbered)."""

    ingested: list[str] = dataclasses.field(default_factory=list)
    skipped_conflicts: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class SessionRecord:
    """One user/assistant message extracted from a Claude Code session transcript."""

    source_file: Path
    speaker: str  # "user" | "assistant"
    timestamp_local: datetime.datetime
    text: str


@dataclasses.dataclass
class RunResult:
    """Outcome of one `claude -p` invocation."""

    ok: bool
    result_text: str
    total_cost_usd: Optional[float]
    num_turns: Optional[int]
    duration_ms: Optional[int]
    raw_stdout: str
    raw_stderr: str
    exit_code: int


@dataclasses.dataclass
class RunContext:
    """Mutable state threaded through one run of `runner.run_job`."""

    config: Config
    job: Job
    target_date: datetime.date
    dry_run: bool = False
    no_push: bool = False
    verbose: bool = False

    # computed once at the top of run_job: verbose OR config.log.level == "debug"
    echo: bool = False

    # populated as the run progresses
    session_records: list[SessionRecord] = dataclasses.field(default_factory=list)
    digest_text: str = ""
    prompt_text: str = ""
    claude_result: Optional[RunResult] = None
    committed: bool = False
    push_attempted: bool = False
    pushed: bool = False
