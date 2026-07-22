"""VM: copy new dated entries from the local data repo's `daily/` into the
shared folder, tracked by a cursor file so repeated runs don't re-copy old
entries.

Copy-only, never deletes or moves the VM's own local files (spec.md §11's
copy-only semantics) — the VM keeps everything, forever, as its own local
record; the share only ever gains a copy.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .. import mount
from ..models import Config

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")


def run(config: Config) -> list[str]:
    """Export new `daily/*.md` files to the share as `<export_prefix><name>`.

    If no cursor exists yet, exports only the single most recent date (never
    the whole history on first run — ported verbatim from the original VM
    script's behavior). Returns the filenames exported this run — empty if the
    share was unavailable or nothing new existed, both normal, not errors.
    """
    if not mount.is_available(config.shared_dir):
        return []

    daily_dir = config.data_dir / "daily"
    if not daily_dir.is_dir():
        return []

    all_dates = sorted(p.name for p in daily_dir.iterdir() if p.is_file() and _DATE_RE.match(p.name))
    if not all_dates:
        return []

    cursor_path = config.scratch_dir / config.sync.cursor_file
    last = cursor_path.read_text(encoding="utf-8").strip() if cursor_path.exists() else ""

    todo = all_dates[-1:] if not last else [d for d in all_dates if d > last]

    exported: list[str] = []
    for name in todo:
        src = daily_dir / name
        dest = config.shared_dir / f"{config.sync.export_prefix}{name}"
        try:
            _atomic_copy(src, dest)
        except OSError:
            # The share can vanish between the mount.is_available() probe above
            # and this write (a TOCTOU race, e.g. the VMware mount dropping
            # mid-run). Treat that exactly like "share unavailable" (spec.md
            # §10): stop here without advancing the cursor past this date, so
            # the next run retries it — never let this surface as a crash.
            break
        cursor_path.write_text(name, encoding="utf-8")
        exported.append(name)
    return exported


def _atomic_copy(src: Path, dest: Path) -> None:
    """Write-temp-then-rename within the destination directory, so a reader on
    the host never observes a partially-written file mid-copy."""
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.copyfile(src, tmp)
    tmp.replace(dest)
