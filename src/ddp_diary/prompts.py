"""Assemble the final `claude -p` prompt: context header + task body + role
fragment + session digest (daily only) + shared conventions.

See spec.md §8. Every piece is read verbatim from `assets/` in the tool repo — the
single source of truth both machines get via `git pull` — and concatenated as
plain text. Deliberately NOT run through a template engine: markdown/code in these
files may contain literal `{}` (JSON examples, code blocks) that must not be
treated as `str.format` placeholders. Computed values (dates, week numbers) are
rendered into a small plain-text "Context" block instead and prepended.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path

from .models import Job, Role


def assets_root() -> Path:
    """Locate the tool repo's `assets/` directory.

    v1 assumes an editable install (`pip install -e .`), so this file's location
    inside `src/ddp_diary/` is a fixed number of parents below the repo root.
    `DDP_DIARY_ASSETS_DIR` overrides this for any other layout.
    """
    override = os.environ.get("DDP_DIARY_ASSETS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent.parent / "assets"


def build_context_block(job: Job, target_date: datetime.date) -> str:
    """A short plain-text header with computed values Claude must not re-derive
    (spec.md §12: the core injects the date; Claude never shells out to `date`)."""
    lines = [f"Target date: {target_date.isoformat()}"]
    if job == "weekly":
        iso_year, iso_week, _ = target_date.isocalendar()
        week_start = target_date - datetime.timedelta(days=target_date.weekday())
        week_end = week_start + datetime.timedelta(days=6)
        lines.append(f"ISO week: {iso_year}-W{iso_week:02d}")
        lines.append(f"Week number: {iso_week}")
        lines.append(f"Date range: {week_start.isoformat()} to {week_end.isoformat()}")
    elif job == "monthly":
        first_of_this_month = target_date.replace(day=1)
        last_month_end = first_of_this_month - datetime.timedelta(days=1)
        lines.append(f"Target month (last calendar month): {last_month_end.strftime('%Y-%m')}")
    return "# Context\n\n" + "\n".join(lines)


def assemble(job: Job, role: Role, target_date: datetime.date, *, digest_text: str = "") -> str:
    """Build the full prompt text for one `claude -p` invocation.

    Order: context -> task body -> (daily only) session digest + role mechanics ->
    shared conventions. Weekly/monthly are host-only jobs (spec.md §5) and carry no
    role fragment — `roles/{host,vm}.md` only describe daily-job mechanics.
    """
    parts = [build_context_block(job, target_date), _read("prompts", "tasks", f"{job}.md")]

    if job == "daily":
        digest_template = _read("prompts", "partials", "session-digest.md")
        parts.append(f"{digest_template}\n\n{digest_text or '(no activity found for this date on this machine)'}")
        parts.append(_read("prompts", "roles", f"{role}.md"))

    parts.append(_read("conventions", "conventions.md"))
    return "\n\n---\n\n".join(p.strip() for p in parts if p.strip())


def _read(*parts: str) -> str:
    return assets_root().joinpath(*parts).read_text(encoding="utf-8")
