"""Guard around the VMware shared folder: is it mounted and writable right now?

See spec.md §10-§11: a missing/unwritable share is a normal, recoverable condition
for `run` (soft skip on host, deferred export on VM) and a hard failure only for the
explicit `sync` command. This module only answers the yes/no question — every
caller decides what "no" means for its own role and command.
"""

from __future__ import annotations

import os
from pathlib import Path


def is_available(shared_dir: Path) -> bool:
    """True if `shared_dir` exists and accepts a real write+delete right now.

    Existence-only checks are not enough for a VMware shared folder: the mount
    point can exist as an empty directory stub before the host tools finish
    attaching it. A write probe catches that case too, at negligible cost.
    Never raises — any OSError here just means "not available yet".
    """
    try:
        if not shared_dir.is_dir():
            return False
        probe = shared_dir / f".ddp-diary-probe-{os.getpid()}"
        with open(probe, "wb") as f:
            f.write(b"probe")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False
