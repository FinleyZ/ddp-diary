"""`ddp-diary status` — a one-glance answer to "did it work" (spec.md §9).

Read-only, like `doctor`, but reports state rather than gating health: latest
diary entry and its age, git state (dirty/ahead/behind/last commit), and the
last run's outcome. Exists because answering "did it work" previously meant
manually chaining `git log`, tailing the run log, and `doctor` across two
directories — this puts it in one command.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Optional

from . import doctor, gitops, logging_setup
from .models import Config

_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
_BANNER_RE = re.compile(r"^===== (.+?) (started|ended) (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) =====$")


def run(config: Config, *, verbose: bool = False) -> int:
    if verbose:
        doctor.print_resolved_config(config)

    if not config.data_dir.is_dir():
        print(f"error: data_dir does not exist: {config.data_dir}")
        return 1

    print(f"role: {config.role}")
    print(f"data_dir: {config.data_dir}")

    _print_latest_entry(config.data_dir)
    _print_git_status(config.data_dir)
    _print_last_run(config)

    return 0


def _print_latest_entry(data_dir: Path) -> None:
    latest = _latest_daily_entry(data_dir)
    if latest is None:
        print("latest daily entry: none found")
        return
    days_since = (datetime.date.today() - latest).days
    if days_since == 0:
        age = "today"
    elif days_since == 1:
        age = "yesterday"
    else:
        age = f"{days_since} days ago"
    print(f"latest daily entry: {latest.isoformat()} ({age})")


def _print_git_status(data_dir: Path) -> None:
    st = gitops.read_status(data_dir)
    if st.last_commit_subject is None:
        print("git: not a repo, or no commits yet")
        return
    ahead = "unknown" if st.ahead is None else str(st.ahead)
    behind = "unknown" if st.behind is None else str(st.behind)
    dirty = "yes" if st.is_dirty else "no"
    print(f"git: last commit '{st.last_commit_subject}' ({st.last_commit_date})")
    print(f"     ahead={ahead} behind={behind} dirty={dirty}")


def _print_last_run(config: Config) -> None:
    outcome = _last_run_outcome(config.log.file)
    if outcome is None:
        print("last run: no log found yet")
        return
    ended = outcome["ended"] or "still running / never completed"
    word = "FAILED" if outcome["failed"] else "OK"
    print(f"last run: {outcome['job']} started {outcome['started']}, ended {ended} — {word}")
    if not outcome["failed"]:
        cost = _last_cost_record(logging_setup.cost_log_path(config))
        if cost is not None:
            seconds = (cost.get("duration_ms") or 0) / 1000
            print(
                f"     cost: ${cost.get('total_cost_usd')} · {cost.get('num_turns')} turns · {seconds:.0f}s"
            )


def _latest_daily_entry(data_dir: Path) -> Optional[datetime.date]:
    daily_dir = data_dir / "daily"
    if not daily_dir.is_dir():
        return None
    dates = []
    for p in daily_dir.iterdir():
        m = _DATE_RE.match(p.name)
        if m and p.is_file():
            try:
                dates.append(datetime.datetime.strptime(m.group(1), "%Y-%m-%d").date())
            except ValueError:
                continue
    return max(dates) if dates else None


def _last_run_outcome(log_path: Path) -> Optional[dict]:
    """Find the most recent 'started'..'ended' banner pair in the plain-text
    run log and whether a FAILED line appears between them. Deliberately does
    NOT trust the cost-log JSONL alone for success/failure — `record_cost()`
    only writes on a successful `claude` call, so after a failed run the
    JSONL would silently show stale success data from a prior night."""
    if not log_path.exists():
        return None
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    start_idx = None
    for i in range(len(lines) - 1, -1, -1):
        m = _BANNER_RE.match(lines[i])
        if m and m.group(2) == "started":
            start_idx = i
            break
    if start_idx is None:
        return None

    start_match = _BANNER_RE.match(lines[start_idx])
    job_name = start_match.group(1)
    started = start_match.group(3)

    failed = False
    ended = None
    for line in lines[start_idx + 1 :]:
        if line.startswith("FAILED"):
            failed = True
        m = _BANNER_RE.match(line)
        if m and m.group(2) == "ended":
            ended = m.group(3)
            break

    return {"job": job_name, "started": started, "ended": ended, "failed": failed}


def _last_cost_record(cost_log_path: Path) -> Optional[dict]:
    if not cost_log_path.exists():
        return None
    try:
        text = cost_log_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        return json.loads(text.splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return None
