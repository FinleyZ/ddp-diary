# VM-specific mechanics

You are running on the **VM**. This machine has no `inbox/` and no external input to
fold — the activity summary provided above (from this machine's own Claude Code
sessions) is your only input for `daily`. This machine does not run `weekly` or
`monthly` jobs.

Focus: this machine's work is firmware/hardware-facing. Distinguish hardware-verified
progress (flashed, bench-tested, confirmed on real hardware) from code-only progress
(compiled, written, not yet run against hardware) — this distinction matters for an
honest "Do better" section. Never record "written and compiles" as equivalent to
"tested."

Do not run `git add` or `git commit` — the orchestrator commits locally after you
finish writing. Do not attempt to push, and do not touch the shared/network folder —
export to the share is a separate, orchestrator-driven step that runs after your
commit.
