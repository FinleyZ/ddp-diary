"""Tests for session_extract.py: date-sliced, bounded session extraction
(spec.md §6, §15). Timestamps are computed relative to the test machine's own
local timezone (via the same `.astimezone()` call the code uses) rather than
hardcoded, so these tests are correct regardless of where they run.
"""

from __future__ import annotations

import datetime
import json
import os
import time
from pathlib import Path

from ddp_diary import session_extract


def _msg(role: str, iso_utc: str, text) -> str:
    content = text if isinstance(text, list) else [{"type": "text", "text": text}]
    return json.dumps({"type": role, "timestamp": iso_utc, "message": {"content": content}})


def _local_date(iso_utc: str) -> datetime.date:
    dt_utc = datetime.datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return dt_utc.astimezone().date()


def _write_session(dir_: Path, name: str, lines: list) -> Path:
    p = dir_ / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


NOON_A = "2026-07-20T12:00:00Z"
NOON_B = "2026-07-21T12:00:00Z"
DATE_A = _local_date(NOON_A)
DATE_B = _local_date(NOON_B)


def test_extract_for_date_finds_matching_messages(tmp_path):
    proj = tmp_path / "projects" / "some-slug"
    proj.mkdir(parents=True)
    _write_session(
        proj,
        "s1.jsonl",
        [
            _msg("user", NOON_A, "did some work on the widget"),
            _msg("assistant", NOON_A, "sure, here is the plan"),
            _msg("user", NOON_B, "different day, should not appear"),
        ],
    )

    records, digest = session_extract.extract_for_date(tmp_path / "projects", DATE_A)

    assert len(records) == 2
    assert all(r.timestamp_local.date() == DATE_A for r in records)
    assert "did some work on the widget" in digest
    assert "different day" not in digest


def test_extract_for_date_no_activity_returns_empty(tmp_path):
    proj = tmp_path / "projects" / "some-slug"
    proj.mkdir(parents=True)
    _write_session(proj, "s1.jsonl", [_msg("user", NOON_A, "only day A activity")])

    other_date = DATE_A + datetime.timedelta(days=10)
    records, digest = session_extract.extract_for_date(tmp_path / "projects", other_date)

    assert records == []
    assert digest == ""


def test_extract_ignores_non_user_assistant_and_malformed_lines(tmp_path):
    proj = tmp_path / "projects" / "some-slug"
    proj.mkdir(parents=True)
    _write_session(
        proj,
        "s1.jsonl",
        [
            "not even json {{{",
            json.dumps({"type": "system", "timestamp": NOON_A, "message": {"content": "ignored"}}),
            _msg("user", NOON_A, "the real message"),
        ],
    )

    records, _ = session_extract.extract_for_date(tmp_path / "projects", DATE_A)

    assert len(records) == 1
    assert records[0].text == "the real message"


def test_extract_handles_list_content_blocks_and_skips_non_text(tmp_path):
    proj = tmp_path / "projects" / "some-slug"
    proj.mkdir(parents=True)
    content_blocks = [
        {"type": "text", "text": "first part"},
        {"type": "tool_use", "name": "Bash"},  # non-text block, must be skipped
        {"type": "text", "text": "second part"},
    ]
    _write_session(proj, "s1.jsonl", [_msg("assistant", NOON_A, content_blocks)])

    records, _ = session_extract.extract_for_date(tmp_path / "projects", DATE_A)

    assert len(records) == 1
    assert records[0].text == "first part second part"


def test_extract_bounds_by_skim_max_files(tmp_path):
    proj = tmp_path / "projects" / "some-slug"
    proj.mkdir(parents=True)
    now = time.time()
    for i in range(8):
        p = _write_session(proj, f"s{i}.jsonl", [_msg("user", NOON_A, f"message from file {i}")])
        os.utime(p, (now + i, now + i))  # stagger mtimes: higher i = more recent

    records, _ = session_extract.extract_for_date(tmp_path / "projects", DATE_A, skim_max_files=3)

    files_seen = {r.source_file for r in records}
    assert files_seen == {proj / "s7.jsonl", proj / "s6.jsonl", proj / "s5.jsonl"}


def test_extract_truncates_digest_but_not_records_by_skim_max_lines(tmp_path):
    proj = tmp_path / "projects" / "some-slug"
    proj.mkdir(parents=True)
    lines = [_msg("user", NOON_A, f"message {i}") for i in range(50)]
    _write_session(proj, "s1.jsonl", lines)

    records, digest = session_extract.extract_for_date(tmp_path / "projects", DATE_A, skim_max_lines=5)

    assert len(records) == 50  # records are not truncated, only the rendered digest is
    assert "truncated at 5 lines" in digest


def test_dates_with_activity_counts_across_files_unbounded(tmp_path):
    proj = tmp_path / "projects" / "some-slug"
    proj.mkdir(parents=True)
    _write_session(
        proj,
        "s1.jsonl",
        [
            _msg("user", NOON_A, "one"),
            _msg("assistant", NOON_A, "two"),
            _msg("user", NOON_B, "three"),
        ],
    )

    counts = session_extract.dates_with_activity(tmp_path / "projects")

    assert counts[DATE_A.strftime("%Y-%m-%d")] == 2
    assert counts[DATE_B.strftime("%Y-%m-%d")] == 1


def test_missing_claude_projects_dir_returns_empty(tmp_path):
    missing = tmp_path / "does-not-exist"

    records, digest = session_extract.extract_for_date(missing, DATE_A)

    assert records == []
    assert digest == ""
    assert session_extract.dates_with_activity(missing) == {}
