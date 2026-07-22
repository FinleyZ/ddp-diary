"""HOST: move new `*.md` files from the shared folder root into the data repo's
`inbox/`.

Non-recursive by design, matching the glob the share export writes to (share
root only) — this must never touch the VM's own `cron.log`, its git repo, or any
subdirectory of the share (spec.md §11). Uses `shutil.move`, not `os.rename`,
because a move from a VMware-mounted share to a local disk crosses devices —
`os.rename` raises `EXDEV` there (spec.md §6's cross-platform gotcha).

A file that would overwrite an existing, not-yet-processed `inbox/` entry is
SKIPPED and reported, never silently clobbered (spec.md §11's ingest-conflict
rule) — the caller decides how to log a conflict; this module only reports it.
"""

from __future__ import annotations

import shutil

from .. import mount
from ..models import Config, IngestResult


def run(config: Config) -> IngestResult:
    """Move matching share-root files into `data_dir/inbox/`. An empty result
    means the share was unavailable or had nothing new — both normal, not
    errors (spec.md §10)."""
    result = IngestResult()
    if not mount.is_available(config.shared_dir):
        return result

    inbox_dir = config.data_dir / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    for item in sorted(config.shared_dir.glob(config.sync.ingest_glob)):
        if not item.is_file():
            continue
        dest = inbox_dir / item.name
        if dest.exists():
            result.skipped_conflicts.append(item.name)
            continue
        try:
            shutil.move(str(item), str(dest))
        except OSError:
            # The share can vanish between the mount.is_available() probe
            # above and this move (a TOCTOU race). Treat that like "share
            # unavailable" (spec.md §10) for whatever remains: stop here
            # rather than let it surface as a crash — the next run retries
            # whatever wasn't moved yet.
            break
        result.ingested.append(item.name)
    return result
