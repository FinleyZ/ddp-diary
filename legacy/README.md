# legacy/

This directory is populated during migration with the retired per-machine
scripts — host `run-journal.ps1` + `prompts/` + `CLAUDE.md`, and the VM's
`run.sh` + `prompt.md` + `CLAUDE.md` — kept for reference and as a rollback
path. See the approved migration plan and spec.md §17's decisions log.

It is intentionally empty until that migration actually happens; ddp-diary
itself never reads from here.
