# Architecture

See [spec.md](../spec.md) for the full design. Quick pointers:

- §3 Architecture Overview — the two-repo model, single core + thin launchers, role-parametrized behavior.
- §4 Data Flow — the two-channel diagram (data vs. code) and why there are two data repos.
- §5 Role Model — what `host` and `vm` each do, and the one invariant (only host pushes).
- §6 Repo Layout & Module Responsibilities — the module-by-module map of `src/ddp_diary/`.

This file intentionally stays thin — spec.md is the source of truth; duplicating it here would just create a second place to keep in sync.
