# Operations

See [spec.md](../spec.md) for the full reference. Quick pointers for day-to-day operation:

- §9 CLI & Commands — `run`, `backfill`, `sync`, `doctor`, and the exit-code table.
- §10 Scheduling & the Mount-Race Guard — Task Scheduler / cron setup, what happens if the share isn't mounted yet.
- §12 Error Handling, Budget, Logging & Cost — where logs and cost records live, what a `FAILED` line means, the always-push-after-failure rule.
- §14 Testing & Verification — how to prove a nightly run actually works (`--dry-run`, `doctor`, the acceptance checklist).

## Common commands

```
ddp-diary doctor --config config/host.toml
ddp-diary run --job daily --config config/host.toml --dry-run -v
ddp-diary sync --config config/vm.toml --export-only
ddp-diary backfill --config config/host.toml --from 2026-07-01 --to 2026-07-07
```

This file intentionally stays thin — spec.md is the source of truth.
