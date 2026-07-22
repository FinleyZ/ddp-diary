"""Run banners, the COST line, and a structured JSON cost log.

Replaces `cron.log` living inside the data repos — the run log and cost log now
live in `config.scratch_dir` (`ddp-diary/state/`, gitignored), never committed
alongside diary entries (spec.md §7, §12, §13).
"""

from __future__ import annotations

import datetime
import json

from .models import Config, RunResult


def banner(config: Config, message: str, *, echo: bool = False) -> None:
    _append(config, f"===== {message} {_now()} =====", echo=echo)


def log(config: Config, message: str, *, echo: bool = False) -> None:
    _append(config, message, echo=echo)


def failure(config: Config, message: str, *, echo: bool = False) -> None:
    _append(config, f"FAILED {message} {_now()}", echo=echo)


def cost_line(config: Config, result: RunResult, *, echo: bool = False) -> None:
    cost = result.total_cost_usd if result.total_cost_usd is not None else float("nan")
    turns = result.num_turns if result.num_turns is not None else "?"
    seconds = (result.duration_ms / 1000) if result.duration_ms is not None else float("nan")
    _append(config, f"COST: {cost:.4f} USD, {turns} turns, {seconds:.0f}s", echo=echo)


def cost_log_path(config: Config):
    return config.log.file.with_suffix(".cost.jsonl")


def record_cost(config: Config, *, role: str, job: str, date_str: str, model: str, result: RunResult) -> None:
    """Append one JSON record per `claude -p` call — machine-parseable, one line
    each (spec.md §12's cost-logging requirement)."""
    path = cost_log_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": _now(),
        "role": role,
        "job": job,
        "date": date_str,
        "model": model,
        "total_cost_usd": result.total_cost_usd,
        "num_turns": result.num_turns,
        "duration_ms": result.duration_ms,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _append(config: Config, line: str, *, echo: bool = False) -> None:
    config.log.file.parent.mkdir(parents=True, exist_ok=True)
    with config.log.file.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    if echo or config.log.level == "debug":
        print(line)
