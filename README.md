# ddp-diary

Cross-platform automation for a personal engineering journal, run unattended on two
machines (a Windows host and a Linux VM) from **one Python core**.

Replaces two divergent, hand-synced scripts — a PowerShell orchestrator on the host and
a bash orchestrator on the VM — with a single `ddp_diary` package plus thin OS launchers.
Both machines clone this repo and run the same code; only a per-machine TOML config
(`config/host.toml` / `config/vm.toml`) differs.

**Start here:** [`spec.md`](spec.md) is the living design document and source of truth —
architecture, data flow, config reference, sync contract, and the roadmap beyond v1.

## Quick orientation

- `src/ddp_diary/` — the core (role-agnostic orchestration; a `host`/`vm` config switch
  selects behavior on an identical spine).
- `assets/` — conventions and prompts, shipped as code so both machines are always in
  sync (no more copy-pasted `CLAUDE.md`s drifting apart).
- `config/` — `host.toml`, `vm.toml`, and a documented `config.example.toml`.
- `launchers/` — thin Windows (`.cmd`/`.ps1`, Task Scheduler) and Linux (`.sh`, cron)
  entry points. No business logic lives here.
- `tests/` — unit + integration tests for the extractor, sync contract, and git ops.
- `legacy/` — populated during migration with the retired scripts, kept for reference.

## Running it

```
# host
python -m ddp_diary run --job daily --config config\host.toml

# vm
python3 -m ddp_diary run --job daily --config config/vm.toml
```

See `spec.md §9` (CLI) and `spec.md §10` (scheduling) for the full command reference and
how Task Scheduler / cron invoke this.

## Journal entries live elsewhere

This repo is the **tool only**. Journal entries (the actual `daily/weekly/monthly`
markdown) live in a separate **data repo** per machine — see `spec.md §4` and `§13` for
why, and `spec.md §17` for the decision log.
