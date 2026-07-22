"""Date-sliced, bounded extraction of Claude Code session activity for the diary
prompt.

Ported from the VM's original inline `python3 -c` date-slicer (see legacy/) and
generalized into a typed, reusable module used by BOTH roles. This is a deliberate
design decision (spec.md §17, 2026-07-20): moving this out of Claude's own
Read/Grep skimming loop and into deterministic Python is what eliminated the
"budget death" failure mode entirely — scanning `.jsonl` files here costs wall-clock
Python time, not Claude tokens. `skim_max_files`/`skim_max_lines` therefore bound
**prompt size** (how much digest text gets fed to Claude), not scan cost.

Two entry points:

- `dates_with_activity()` — cheap, UNBOUNDED (counts only, no message text). Used to
  find backfill candidates: dates with activity but no diary entry yet.
- `extract_for_date()` — bounded: only the `skim_max_files` most-recently-modified
  session files with activity on the target date are read, and the rendered digest
  is capped at `skim_max_lines` lines. Returns typed `SessionRecord`s (not just
  text) so a future transcript index can consume them without touching this
  module's callers (spec.md §15, future phase A).
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Optional

from .models import SessionRecord

_MAX_MESSAGE_CHARS = 1500


def dates_with_activity(claude_projects: Path) -> dict[str, int]:
    """Return {"YYYY-MM-DD": message_count} across every session file. Unbounded
    and cheap (no message text is retained) — safe to call over a whole history."""
    counts: dict[str, int] = {}
    for f in _iter_jsonl_files(claude_projects):
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    parsed = _parse_message_line(line)
                    if parsed is None:
                        continue
                    _speaker, ts_local, _text = parsed
                    day = ts_local.strftime("%Y-%m-%d")
                    counts[day] = counts.get(day, 0) + 1
        except OSError:
            continue
    return counts


def extract_for_date(
    claude_projects: Path,
    target_date: datetime.date,
    *,
    skim_max_files: int = 5,
    skim_max_lines: int = 200,
) -> tuple[list[SessionRecord], str]:
    """Extract session activity for exactly `target_date`.

    Every session file is scanned to find which ones have any activity that day
    (cheap: date-only comparison, no text retained). Among those, only the
    `skim_max_files` most-recently-modified are actually read for content —
    `skim_max_files <= 0` disables the file bound. The rendered digest is capped
    at `skim_max_lines` lines (`<= 0` disables the line bound).
    """
    target_str = target_date.strftime("%Y-%m-%d")

    candidates = [f for f in _iter_jsonl_files(claude_projects) if _file_has_activity_on(f, target_str)]
    candidates.sort(key=_safe_mtime, reverse=True)
    chosen = candidates[:skim_max_files] if skim_max_files > 0 else candidates

    records: list[SessionRecord] = []
    for f in chosen:
        records.extend(_extract_records_from_file(f, target_str))

    digest = _render_digest(records, skim_max_lines=skim_max_lines)
    return records, digest


def _iter_jsonl_files(claude_projects: Path):
    if not claude_projects.is_dir():
        return
    yield from claude_projects.rglob("*.jsonl")


def _safe_mtime(f: Path) -> float:
    try:
        return f.stat().st_mtime
    except OSError:
        return 0.0


def _parse_message_line(line: str) -> Optional[tuple[str, datetime.datetime, str]]:
    """Parse one JSONL line into (speaker, local timestamp, text), or None if the
    line isn't a user/assistant message with a usable timestamp."""
    try:
        msg = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    speaker = msg.get("type")
    if speaker not in ("user", "assistant"):
        return None
    ts = msg.get("timestamp")
    if not ts:
        return None
    try:
        dt_utc = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    dt_local = dt_utc.astimezone()

    content = msg.get("message", {}).get("content")
    if isinstance(content, list):
        text = " ".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    else:
        text = content or ""
    return speaker, dt_local, text.strip()


def _file_has_activity_on(f: Path, target_str: str) -> bool:
    try:
        with f.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parsed = _parse_message_line(line)
                if parsed is None:
                    continue
                _speaker, dt_local, _text = parsed
                if dt_local.strftime("%Y-%m-%d") == target_str:
                    return True
    except OSError:
        return False
    return False


def _extract_records_from_file(f: Path, target_str: str) -> list[SessionRecord]:
    out: list[SessionRecord] = []
    try:
        with f.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parsed = _parse_message_line(line)
                if parsed is None:
                    continue
                speaker, dt_local, text = parsed
                if dt_local.strftime("%Y-%m-%d") != target_str or not text:
                    continue
                out.append(
                    SessionRecord(
                        source_file=f,
                        speaker=speaker,
                        timestamp_local=dt_local,
                        text=text[:_MAX_MESSAGE_CHARS],
                    )
                )
    except OSError:
        pass
    return out


def _render_digest(records: list[SessionRecord], *, skim_max_lines: int) -> str:
    if not records:
        return ""
    records = sorted(records, key=lambda r: r.timestamp_local)
    lines: list[str] = []
    current_file: Optional[Path] = None
    emitted = 0

    def _capped() -> bool:
        return skim_max_lines > 0 and emitted >= skim_max_lines

    for rec in records:
        if _capped():
            lines.append(f"... (truncated at {skim_max_lines} lines)")
            break
        if rec.source_file != current_file:
            lines.append(f"=== {rec.source_file}")
            current_file = rec.source_file
            emitted += 1
            if _capped():
                lines.append(f"... (truncated at {skim_max_lines} lines)")
                break
        lines.append(f"{rec.timestamp_local.strftime('%H:%M')} [{rec.speaker}] {rec.text}")
        emitted += 1

    return "\n".join(lines)
