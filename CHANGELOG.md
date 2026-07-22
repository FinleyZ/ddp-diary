# Changelog

## v1.0.0 — unreleased

Initial rewrite. Replaces the two divergent per-machine scripts (host `run-journal.ps1`
PowerShell orchestrator, VM `run.sh` bash orchestrator) with one cross-platform Python
core (`ddp_diary`) driven by a `role = host | vm` config switch, plus thin OS launchers.

Carried over from the retired scripts (see `legacy/` after migration): the date-sliced
session extractor, budget/skim rules, backfill/dedup logic, VMware-share mount guards,
JSON cost-log parsing, and the deterministic always-push-after-commit behavior.

Hardened by a two-pass adversarial review before first use: fixed a silent-overwrite
bug in inbox ingest, a TOCTOU race that could bypass the always-push guarantee and leak
a raw traceback, a double-push-on-failure bug, undetected `is_error` results from
`claude`, a doctor exit-code bug, and a missing unknown-config-key warning. See
`spec.md §17`'s 2026-07-21 entry for the full list. 96 tests.

See `spec.md` for the full design and `spec.md §17` for the decisions log.
