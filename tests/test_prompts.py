"""Tests for prompts.py: context-block computation and prompt assembly
(spec.md §8, and §12's date-injection note). Derived values (ISO week, month
boundary) are computed in the test with the same stdlib calls the code uses,
rather than hardcoded, so these aren't a second guess at calendar arithmetic."""

from __future__ import annotations

import datetime

from ddp_diary import prompts


def test_daily_context_block_has_only_target_date():
    block = prompts.build_context_block("daily", datetime.date(2026, 7, 20))
    assert "Target date: 2026-07-20" in block
    assert "ISO week" not in block
    assert "Target month" not in block


def test_weekly_context_block_has_iso_week_and_range():
    d = datetime.date(2026, 7, 20)
    block = prompts.build_context_block("weekly", d)

    iso_year, iso_week, _ = d.isocalendar()
    week_start = d - datetime.timedelta(days=d.weekday())
    week_end = week_start + datetime.timedelta(days=6)

    assert f"Target date: {d.isoformat()}" in block
    assert f"ISO week: {iso_year}-W{iso_week:02d}" in block
    assert f"Week number: {iso_week}" in block
    assert f"Date range: {week_start.isoformat()} to {week_end.isoformat()}" in block


def test_monthly_context_block_has_last_calendar_month():
    d = datetime.date(2026, 7, 1)
    block = prompts.build_context_block("monthly", d)

    last_month_end = d.replace(day=1) - datetime.timedelta(days=1)

    assert f"Target month (last calendar month): {last_month_end.strftime('%Y-%m')}" in block


def test_assemble_daily_includes_digest_and_role_fragment():
    text = prompts.assemble("daily", "host", datetime.date(2026, 7, 20), digest_text="did the thing")

    assert "did the thing" in text
    assert "Host-specific mechanics" in text  # from assets/prompts/roles/host.md
    assert "Journal conventions" in text  # from assets/conventions/conventions.md


def test_assemble_weekly_excludes_role_fragment_and_digest():
    text = prompts.assemble("weekly", "host", datetime.date(2026, 7, 20))

    assert "Host-specific mechanics" not in text
    assert "Recent activity" not in text
    assert "Weekly journal digest" in text


def test_assemble_vm_role_uses_vm_fragment_not_host():
    text = prompts.assemble("daily", "vm", datetime.date(2026, 7, 20), digest_text="firmware work")

    assert "VM-specific mechanics" in text
    assert "Host-specific mechanics" not in text


def test_assemble_daily_with_no_digest_says_so_honestly():
    text = prompts.assemble("daily", "host", datetime.date(2026, 7, 20), digest_text="")
    assert "no activity found for this date" in text
