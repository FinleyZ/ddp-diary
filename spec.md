# ddp-diary — spec

**Spec version:** 0.2.0 (draft) · **Last updated:** 2026-07-24 · **Tracks tool version:** v1.0.0

This document is the single source of truth for what ddp-diary is and how it behaves.
Code and spec disagreeing is a **spec bug** — fix one, then log the fix in §17. Every
material behavior change lands as a spec edit (bump the version above) before or
alongside the code change, not after.

**Status legend used throughout:** `v1` (built, in scope now) · `future` (documented,
not built) · `decided` (settled, see §17) · `open` (needs a decision).

---

## 1. Purpose & Non-Goals

**Purpose.** One Python core + thin OS launchers, one tool repo cloned on both a Windows
host and a Linux VM, replacing two divergent scripts (a PowerShell orchestrator on the
host, a bash orchestrator on the VM) and their hand-synced, already-drifted conventions
with a single-source implementation.

**What v1 delivers** (`v1`) — the core pipeline:
1. Cross-platform runner with an explicit `host`/`vm` role switch (§5).
2. Daily / weekly / monthly synthesis via headless `claude -p` (§8, §9).
3. VM→host entry sync through a VMware shared folder (§11).
4. Single-source conventions and prompts shipped inside this repo (§8).
5. Date-sliced, bounded session extraction from `~/.claude/projects/*.jsonl` (§6).
6. JSON cost logging per run (§12).
7. Deterministic git commit + push of the **host** data repo after every run (§12).
8. Idempotent backfill + dedup (§11).
9. Mount-race and missing-share guards (§10, §11).
10. `--dry-run` and `doctor` verification (§14).

**Non-goals for v1** (`future`, roadmap only — see §15): a local SQLite/FTS index over
session transcripts; Obsidian-friendly output (frontmatter, tags, wikilinks); an MCP
server exposing the journal. None of these ship in v1 even where trivial — v1 stops at
the list above.

**Success in one sentence:** an unattended nightly run on each machine produces the
correct entry for the period, logs its cost, commits, and (host only) pushes to GitHub
— with zero manual steps and no hardcoded paths anywhere in the code.

---

## 2. Glossary & Naming

- **ddp-diary** — the tool's name, chosen by the user. Not an acronym; treated as a
  proper noun throughout this spec and the code (package `ddp_diary`, CLI `ddp-diary`).
- **role** — `host` or `vm`. An explicit switch (config or `--role`), never inferred
  silently. See §5.
- **tool repo** — this repository: the Python core, launchers, conventions, prompts,
  config templates, and this spec. Cloned via git on both machines.
- **data repo** — a separate repository holding journal *entries* (`daily/ weekly/
  monthly/ LONG_TERM.md`). There are **two data repos**, one per machine (§4) — this is
  a deliberate design choice, not an oversight (see the decisions log, §17).
- **entry** — one dated journal file, e.g. `daily/2026-07-20.md`.
- **period** — `daily`, `weekly`, or `monthly` — which synthesis job is running.
- **session** — one Claude Code transcript file, `~/.claude/projects/<slug>/<id>.jsonl`.
- **share** — the VMware shared folder that carries the VM→host entry export. It is
  transport only, never a source of truth for tool behavior or conventions.
- **export cursor** — the VM-side marker of the newest entry already copied to the
  share, so re-runs don't re-copy old files.
- **backfill** — writing (or amending) an entry for a *past* date because activity for
  that date was found late (e.g., a delayed VM export).
- **synthesis** — the act of a `claude -p` run producing/extending an entry file.

Domain content (firmware tickets, product names, KB numbers) is journal *content*; the
tool never interprets it — see §1 non-goals.

---

## 3. Architecture Overview

**Two-repo model.** The tool repo (code + conventions, versioned, cloned on both
machines) is separate from the data repo(s) (journal entries). This keeps conventions
single-sourced as code while isolating entry history and any host-side secrets (git
credentials) from the tool's own version control.

**Single core, thin launchers.** All logic lives in `src/ddp_diary/`. Launchers
(`launchers/windows/*.cmd`→`run.ps1`, `launchers/linux/run.sh`) only locate a Python
interpreter and forward arguments — they contain no business logic, so every future
front-end (a test, an MCP server, a daemon) can call the same core directly.

**Role-parametrized behavior.** Every job runs the identical orchestration spine
(`runner.py`); `config.role` selects a `HostRole` or `VmRole` strategy object that
supplies two hooks (`before_run`, `after_commit`). Everything else — extraction, prompt
assembly, the Claude invocation, commit — is shared code.

**External dependencies.** `claude` CLI (headless, `-p` mode), `git`, the VMware shared
folder (host: a Windows path; VM: `/mnt/hgfs/...`), Python ≥3.9 (3.11+ preferred for
stdlib `tomllib`; `tomli` fallback documented in `pyproject.toml`). `doctor` (§14)
checks all of these are present and reachable before a real run is trusted.

---

## 4. Data Flow

**Two channels — not three.** It is easy to misread this as three "combine" steps.
There are really only **two hops of diary content**, plus one **unrelated code
channel** that never carries diary content:

```
DATA channel (diary content — 2 hops):
  VM sessions --extract--> claude -p --> VM data repo (local commit, never pushed)
                                              |
                                              v  export (copy-only, cursor-tracked)
                                            share (vm-daily-*.md)
                                              |
                                              v  ingest (move --> inbox/)
  host sessions --extract--> claude -p --> host data repo (commit) --> GitHub (push)
                                                   ^
                                                   |  hop 2: the fold happens here —
                                                   |  host synthesis merges ingested
                                                   |  VM entries + host session activity

CODE channel (tool + conventions — separate, never carries diary content):
  ddp-diary tool repo --git pull--> identical core / prompts / conventions on both machines
```

The share carries **only** the one-way VM→host entry export; it is never a source of
truth for the tool itself. Confusing the code channel (git pull of this repo) with the
data channel is what makes this look like a third merge — it is not; conventions and
diary content never cross paths.

**Two data repos, by design** (`decided`, §17):
- **VM data repo** — local, **never pushed**. Gives the VM its own git history/diff
  independent of the share or the host. Only the VM itself ever reads this history.
- **Host data repo** — the **single canonical, GitHub-pushed** record. This is the one
  that matters externally and the one that survives if the VM or the share is lost.

---

## 5. Role Model

| Stage | host | vm |
|---|---|---|
| Ingest from share → `inbox/` | ✓ | — |
| Extract local sessions | ✓ | ✓ |
| Synthesize entry (`claude -p`) | ✓ | ✓ |
| Commit to local data repo | ✓ | ✓ |
| Export new entries → share | — | ✓ |
| Push data repo to GitHub | ✓ | — |

**Invariant:** exactly one role (`host`) ever pushes to GitHub. The VM is fully
offline-safe after cloning the tool repo once — it needs no network for its nightly run.

**Role selection:** `--role` flag > `config.role` > hard error. Never guessed from
hostname, OS, or any other signal — an ambiguous role is a configuration bug, not
something to paper over.

**Job restriction is enforced, not just scheduled around:** `runner.run_job()` raises a
`ConfigError` (exit `2`) if `role == "vm"` and `job != "daily"`. The VM only ever having
a `daily` cron entry (§10) is what makes this true in practice, but the guard means a
mistaken manual `--role vm --job weekly` invocation fails cleanly instead of silently
producing a weekly digest in the VM's local repo.

- **`HostRole.before_run`** → `sync.ingest.run()` (move share `*.md` into `inbox/`,
  mount-guarded, best-effort).
- **`HostRole.after_commit`** → no-op.
- **`VmRole.before_run`** → no-op (ensure local dirs exist).
- **`VmRole.after_commit`** → `sync.export.run()` (copy new dailies to the share,
  advance the cursor, mount-guarded).

---

## 6. Repo Layout & Module Responsibilities

```
ddp-diary/
├─ pyproject.toml  spec.md  README.md  CHANGELOG.md  .gitignore  .editorconfig
├─ src/ddp_diary/
│  ├─ __main__.py       # `python -m ddp_diary` entry point
│  ├─ cli.py            # argparse only; dispatches to runner.run_job(); no logic
│  ├─ models.py         # Config, RunContext, RunResult, SessionRecord dataclasses
│  ├─ config.py         # TOML load -> validate -> resolve -> Config
│  ├─ paths.py           # cross-platform path + claude-binary + claude_projects resolution
│  ├─ mount.py           # shared-folder mount/writability guard
│  ├─ session_extract.py # date-sliced, bounded .jsonl extractor -> list[SessionRecord]
│  ├─ prompts.py         # assemble task + role + digest + conventions -> prompt text
│  ├─ claude_client.py   # build argv, invoke `claude -p` over stdin, parse JSON result/cost
│  ├─ gitops.py          # add/commit (skip if nothing staged), push (best-effort, logged)
│  ├─ roles.py           # Role ABC + HostRole / VmRole
│  ├─ runner.py          # the role-agnostic orchestration spine (§4 DATA channel, in code)
│  ├─ logging_setup.py   # run banners, COST line, structured log file
│  ├─ errors.py          # exception types <-> exit codes (§9)
│  └─ sync/
│     ├─ ingest.py       # HOST: move shared *.md -> inbox/ (glob-matched, mount-guarded)
│     └─ export.py       # VM: copy new daily/*.md -> shared vm-daily-*.md + advance cursor
├─ assets/
│  ├─ conventions/conventions.md   # SINGLE source: entry types, sections, tone, honesty
│  └─ prompts/
│     ├─ tasks/{daily,weekly,monthly}.md   # role-neutral task body
│     ├─ roles/{host,vm}.md                # role-specific mechanics
│     └─ partials/session-digest.md        # template the extracted digest is rendered into
├─ config/{host.toml, vm.toml, config.example.toml, local.toml (gitignored)}
├─ launchers/
│  ├─ windows/{daily,weekly,monthly}.cmd, run.ps1, register-tasks.ps1
│  └─ linux/{run.sh, crontab.example, install-cron.sh}
├─ docs/{architecture.md, operations.md, data-repo.md}   # short pointers into this spec
├─ tests/  fixtures/  test_*.py
└─ legacy/   # populated during migration with the retired scripts, kept for reference
```

**Module responsibility summary** (one line each): `cli.py` parses args and calls
`runner.run_job`, nothing else. `config.py` is the only place that reads environment/
filesystem to resolve a `Config`. `paths.py` and `mount.py` isolate all OS-specific
path/mount logic so the rest of the core is platform-neutral. `session_extract.py`
returns typed data (`SessionRecord`), not just text, so a future SQLite index (§15) can
consume it without touching this module's callers. `claude_client.py` is the only place
that shells out to `claude`. `gitops.py` is the only place that shells out to `git`.
`sync/ingest.py` and `sync/export.py` are the only role-specific I/O; everything else in
`sync/` is shared by construction (there is nothing else in `sync/`).

---

## 7. Configuration Reference

**Format:** TOML (`tomllib`, stdlib ≥3.11; `tomli` fallback below that — declared in
`pyproject.toml`). **Precedence:** CLI flag > `config/local.toml` (gitignored,
per-machine override) > `config/<role>.toml` > built-in default. `local.toml`
deliberately outranks the checked-in role file — its whole purpose is to override it
per-machine. (`DDP_DIARY_*` environment-variable overrides were considered but are
**not implemented in v1** — config files are hand-edited directly for a two-machine
personal tool; revisit only if that stops being true.) Every path the old scripts
hardcoded is now a key below — there is no hardcoded absolute path anywhere in
`src/ddp_diary/`.

| Key | Type | Meaning | Host | VM |
|---|---|---|---|---|
| `role` | str | `"host"` \| `"vm"` | `"host"` | `"vm"` |
| `paths.data_dir` | path | the machine's data repo | `C:\Users\<you>\pp\journal` | `~/journal` |
| `paths.shared_dir` | path | the VMware share root | `…\Virtual Machines\<vm-name>\shared\pp\log` | `/mnt/hgfs/share-folder/shared/pp/log` |
| `paths.claude_projects` | path\|"auto" | session transcripts root | `"auto"` (→ `claude.config_dir`/projects if pinned, else `~/.claude/projects`) | `"auto"` |
| `paths.scratch_dir` | path\|"auto" | state/log/cursor location | `"auto"` (→ `<tool_repo>/state`) | `"auto"` |
| `claude.bin` | path\|"auto" | `claude` executable | `"auto"` (→ `shutil.which`, `claude.cmd`) | `"auto"` |
| `claude.config_dir` | path\|"" | pin the account via `CLAUDE_CONFIG_DIR`; `""` = inherit default login | `.claude-personal` (pins the personal account) | `""` (set to the VM's personal dir at migration) |
| `claude.model` | str | model id | `"sonnet"` | `"claude-sonnet-5"` *(open, §17)* |
| `claude.output_format` | str | always `"json"` | `"json"` | `"json"` |
| `claude.allowed_tools` | list[str] | `--allowedTools` | `Read,Glob,Grep,Write,Edit,Bash(mv:*)` | `Read,Glob,Grep,Write,Edit` |
| `claude.add_dirs` | list[path] | extra `--add-dir` | `[]` (core extracts sessions itself; see §6) | `[]` |
| `limits.max_turns` | int | `--max-turns`, `0`=unset | `0` | `15` |
| `limits.max_budget_usd` | float | `--max-budget-usd`, `0`=no cap | `0` (log cost instead) | `1.00` |
| `limits.timeout_sec` | int | subprocess timeout | `900` | `900` |
| `limits.skim_max_files` | int | extractor file cap | `5` | `5` |
| `limits.skim_max_lines` | int | extractor per-file line cap | `200` | `200` |
| `limits.backfill_days` | int | auto-backfill look-back window, days; `0`=off | `0` (opt-in) | `0` (opt-in) |
| `limits.backfill_max_per_run` | int | cap on missing dates processed in one run | `3` | `3` |
| `git.remote` | str | data-repo remote name | `"origin"` | *(unused — VM never pushes)* |
| `git.branch` | str | data-repo branch | `"master"` | `"master"` (local only) |
| `git.push` | bool | push after commit | `true` | `false` |
| `git.push_even_on_failure` | bool | push in `finally` | `true` | `false` |
| `git.commit_prefix` | str | commit message prefix | `"journal:"` | `"journal:"` |
| `sync.export_prefix` | str | share filename prefix | *(unused)* | `"vm-daily-"` |
| `sync.cursor_file` | str | export cursor filename | *(unused)* | `".export-state"` |
| `sync.ingest_glob` | str | share files host ingests | `"*.md"` | *(unused)* |
| `sync.mirror` | bool | keep a full share-side mirror | `false` *(decided: drop, §17)* | `false` |
| `log.file` | path\|"auto" | run log | `"auto"` (→ `state/ddp-diary.log`) | `"auto"` |
| `log.level` | str | `"info"` \| `"debug"` | `"info"` | `"info"` |

**Future-only stubs** (present, commented out, unused in v1 — see §15):
```toml
# [store]   backend = "sqlite", path = "..."
# [publish] obsidian_vault = "..."
# [mcp]     enabled = false
```

**Validation:** an unknown key logs a warning; a missing required key fails fast with
exit code `2` (§9) and a message naming the key — never a deep failure inside a
subprocess call.

---

## 8. Conventions & Prompts

**Single-source principle.** The entry format and tone live once, in
`assets/conventions/conventions.md`, consumed by both roles. Changing the rules is one
commit to this repo — a `git pull` updates both machines. There is no `CLAUDE.md` in
either data repo.

**Shared, non-negotiable format rules** (from `conventions.md`): factual, first-person,
concise; **never invent activity** — a day with no data gets a one-line honest entry;
task-level altitude (no function names, commit hashes, register addresses — that
belongs in git history and KB entries, not the diary).

**Per-period templates:**
- **Daily** (`assets/prompts/tasks/daily.md`) — exactly `## Did / ## Learned / ## Stuck
  or open questions / ## Do better / ## Tomorrow`, skipping empty sections.
- **Weekly** — an editorial digest (2–4 themed stories, odds-and-ends, a Do-better
  self-review, one zoomed-out observation), not a status report.
- **Monthly** — trajectory (skills leveled up, projects opened/closed) and the **only**
  run allowed to edit `LONG_TERM.md`, conservatively.

**Shared format vs. role-specific mechanics:** the *what* (sections, tone) is shared and
lives in `tasks/`; the *how* (which sessions feed in, backfill routing, where output
lands) is role logic and lives in `roles/{host,vm}.md` plus `runner.py` — never baked
into the shared task prompt.

- `roles/host.md` — inbox is pre-populated by `sync.ingest`; fold `vm-daily-*.md` as the
  authoritative record of that VM day (don't copy verbatim); **backfill rule**: a
  `vm-daily-YYYY-MM-DD` dated *before* today folds into **that date's** file, not
  today's; dedup against the most recent existing entry before writing.
- `roles/vm.md` — firmware-focused; the session digest (§6, `session_extract.py`) is the
  primary input, not a Read/Grep skim of raw transcripts.

**Prompt assembly** (`prompts.py`): `task body → session digest (daily only) → role
fragment → conventions`, concatenated and piped to `claude -p` over **stdin** (never
argv — avoids Windows command-length limits and cross-shell quoting entirely). The
digest comes *before* the role fragment deliberately: `roles/host.md`'s own text says
"a SEPARATE source from the activity summary **above**," which only reads correctly if
the digest has already appeared earlier in the prompt. The core also injects the
**target date** as plain text (computed once, deterministically, in Python) — Claude
never shells out to `date` to determine "today," which is why `Bash(date:*)` is absent
from `claude.allowed_tools` (§7). `Bash(mv:*)` remains host-only, for the
inbox→`processed/` archival step, which stays a content judgment Claude makes (it knows
which files it actually folded) rather than mechanical git plumbing (§8, §12 decision).

---

## 9. CLI & Commands

```
ddp-diary run      --job {daily|weekly|monthly} --config PATH [--role host|vm]
                    [--date DATE] [--dry-run] [--no-push] [-v|--verbose]
ddp-diary backfill  --config PATH [--role host|vm] --from DATE --to DATE [--dry-run]
ddp-diary sync      --config PATH [--role host|vm] {--export-only|--ingest-only}
ddp-diary doctor    --config PATH [--role host|vm] [-v|--verbose]
ddp-diary status    --config PATH [--role host|vm] [-v|--verbose]
ddp-diary version
```

`--role` is accepted by every subcommand that loads a config (same override semantics
as `run`'s). `doctor -v`/`status -v` both print the fully resolved config before running
(shared via `doctor.print_resolved_config`, not duplicated) — useful for seeing exactly
what a given config file resolved to. `DATE` accepts `YYYY-MM-DD`, or the case-insensitive
aliases `today`/`yesterday` — accepted everywhere a date is taken (`run --date`,
`backfill --from`/`--to`).

- **`run`** — the main pipeline (§4 spine). `--role` overrides `config.role` for one
  invocation. For `--job daily` specifically, **omitting `--date` entirely** (the exact
  form the real scheduled launcher uses) routes through `runner.run_daily_with_backfill`
  — best-effort auto-backfill (§11) first, then today — while **any explicit `--date`**
  (including `--date today`) bypasses backfill and calls `run_job` directly. Non-`daily`
  jobs always call `run_job` directly; there is no weekly/monthly backfill concept.
- **`backfill --from --to`** — reprocesses a date range; dedup-safe (re-running is a
  no-op for dates that already have a correct entry). Independent of, and unaffected by,
  the `limits.backfill_days` auto-backfill mechanism above — this is the explicit,
  operator-driven range tool; that is the automatic, activity-driven catch-up.
- **`sync`** — runs only the ingest/export stage for the configured role, useful for
  retrying a failed share operation without a full synthesis run.
- **`doctor`** — environment/health check (§14); exit code reflects the worst check.
- **`status`** — a one-glance, read-only report: latest `daily/` entry and its age, git
  state (dirty/ahead/behind/last commit, via `gitops.read_status`), and the last run's
  outcome. Exists because answering "did it work" previously meant manually chaining
  `git log`, tailing the run log, and `doctor` across two directories. Always exits `0`
  except `1` if `data_dir` itself is unreachable (a reporting command finding something
  to *report* isn't itself a failure in the §9 sense). The "last run" line is **not**
  read from the cost-log JSONL alone — `record_cost()` only writes on a *successful*
  `claude` call, so after a failed run the JSONL would silently show stale success data
  from a prior night. Instead it scans the plain-text log for the most recent
  `started`/`ended` banner pair and checks whether a `FAILED` line falls between them,
  then pairs that success/fail signal with the cost-log's last line for `$`/turns/
  duration detail on an actual success.
- **`--dry-run`** — resolves config, extracts sessions, builds the prompt, and prints
  the planned actions (which files would be written/moved, the commit message, whether
  a push would occur) **without** invoking `claude`, writing entries, or touching git or
  the share.

**Exit codes** — reflects the *worst* failure encountered during the run:

| Code | Meaning |
|---|---|
| `0` | success |
| `1` | unexpected/unhandled error |
| `2` | config error (missing/invalid key or path) |
| `3` | `claude` invocation failed (nonzero exit, timeout, or unparseable output) |
| `4` | git commit failed |
| `5` | git push failed (host only; commits remain local, retried next run) |
| `6` | share unavailable when the requested operation required it (`sync` only — `run` treats a missing share as a soft skip/defer, not a failure; see §10–§11) |

---

## 10. Scheduling & the Mount-Race Guard

**Host — Windows Task Scheduler:**
| Job | Trigger | Action |
|---|---|---|
| `JournalDaily` | 21:00 daily | `launchers\windows\daily.cmd` |
| `JournalWeekly` | Sun 21:30 | `launchers\windows\weekly.cmd` |
| `JournalMonthly` | 1st @ 22:00 | `launchers\windows\monthly.cmd` |

Each `.cmd` calls `run.ps1`, which locates Python and runs
`python -m ddp_diary run --job <job> --config config\host.toml`. Re-pointing these three
actions during migration requires an **elevated shell** (S4U task registration) — a
manual step (§17).

**VM — cron**, mount-race guarded:
```
@reboot sleep 120
0 20 * * *  /home/<user>/ddp-diary/launchers/linux/run.sh >> /home/<user>/ddp-diary/state/cron.log 2>&1
```

**Mount-race guard:** the VMware share may not be mounted yet at boot-adjacent trigger
times. The `@reboot sleep 120` line stays as a coarse guard; independently, `mount.py`
probes existence **plus a real write-and-delete** before every ingest/export (a plain
existence check isn't enough — the mount point can exist as an empty directory stub
before the host tools finish attaching it; the write probe catches that too, and is
more portable than `os.path.ismount()`, which behaves inconsistently across VMware/
network mounts). A manual mid-boot run can't crash either. Because the check and the
actual write are still two separate steps, a share that vanishes *between* them (a
narrower TOCTOU race) is also handled: `sync/export.py` and `sync/ingest.py` catch
`OSError` around their real file operations and degrade the same way — stop, don't
advance the cursor / don't count the item as ingested, no crash. **Missing-share
behavior differs by role and by command:** for `run`, a missing (or mid-operation-lost)
share is a soft skip (host: proceed inbox-only; VM: write/commit the entry locally,
defer the export, leave the cursor unchanged so it retries next run) — never a hard
failure. For the explicit `sync` command, a share missing at the *start* **is** a
failure (exit `6`), since sync's only job is the share operation.

---

## 11. Sync Contract

- **Export cursor** (VM) — `paths.scratch_dir/.export-state` holds the name of the
  newest entry already exported. Export copies only entries with a *later* date, then
  advances the cursor. The cursor is trivially rebuildable from filenames if lost (worst
  case: a harmless re-export of already-ingested-and-folded content, caught by dedup).
  **Known limitation:** the comparison is a plain filename string, with no content-hash
  or mtime tracking — a date *older* than the cursor is never (re-)exported automatically,
  even if it's a fresh backfill or an amendment to an already-exported day. This matches
  the original VM script's behavior verbatim (a deliberate "reuse proven logic" choice,
  §17) and is rare in practice for a personal daily diary; if it's ever needed, either
  remove/edit `.export-state` by hand before the next `sync --export-only`, or copy the
  file to the share manually.
- **Ingest by glob** (host) — matches `sync.ingest_glob` (`*.md`) at the **share root
  only** (non-recursive), moving matches into `data_dir/inbox/`. This deliberately
  leaves the VM's own `cron.log`/mirror (if any) untouched.
- **Copy-only semantics** — `sync.export` never deletes or moves the VM's local
  entries; it only copies. Re-running is idempotent: nothing new to export copies
  nothing, and the share is never a required backup (§13).
- **Inbox-driven backfill rule** — a `vm-daily-YYYY-MM-DD` ingested with a date before
  "today" folds into **that date's** host entry (creating it if missing, marked
  backfilled), never into today's. This is host synthesis logic (`roles/host.md`), not
  sync mechanics — `sync.ingest` only relocates files; it never decides where content
  belongs. This is a **separate mechanism** from the auto-backfill below — this one is
  triggered by a *late file arriving from the VM*; the other by *this machine's own
  session activity having no entry yet*. Both can legitimately touch the same date's
  file on different nights; that's the same "extend, don't duplicate" synthesis
  responsibility either way, not a conflict between the two mechanisms.
- **Auto-backfill (activity-driven, `limits.backfill_days`)** — `runner.
  backfill_missing_days()` restores the original VM script's behavior (it auto-filled
  the past 7 days), dropped in the initial rewrite and re-added after the first real
  production run exposed the gap (spec.md §17, 2026-07-24). Ships **off** (`0`) on both
  roles — opt in deliberately once it's been watched run manually at least once, since
  host has no cost ceiling (`limits.max_budget_usd = 0`) and a wide window plus sparse
  history could otherwise queue an unbounded number of `claude` calls unattended.
  Bounded two ways: `backfill_days` limits how far back to *look* (via
  `session_extract.dates_with_activity()`, checked against which dates already have a
  `daily/{date}.md`); `backfill_max_per_run` independently caps how many missing dates
  get *processed* in one invocation, oldest first. Only fires when `run --job daily` is
  invoked with **no explicit `--date`** — the exact form the real scheduled launcher
  uses — via `runner.run_daily_with_backfill()`; an explicit `--date` (including
  `--date today`) always bypasses it. Each missing date is independent and best-effort
  (a failure on one is logged and does not stop the rest, and never affects today's own
  exit code) — the whole point is that one missed day shouldn't compound into losing
  every day after it too.
- **Dedup / entry identity** — an entry's identity is `(role's data repo, period, date)`.
  Before writing, synthesis reads the most recent existing entry for that identity and
  extends/replaces rather than duplicating. Re-running `run` or `backfill` for a date
  that already has a correct entry is a no-op change (idempotent).
- **Ingest conflict rule** — if ingest would overwrite an entry that already exists for
  a date/period, it **skips and logs**, never silently overwrites; `--force` (future,
  not v1) would be required to override.

---

## 12. Error Handling, Budget, Logging & Cost

- **Always-push-after-failure** (host only) — the push stage runs unconditionally after
  commit, in a `finally`-equivalent block, regardless of whether synthesis succeeded.
  Whatever was committed reaches GitHub even if this run's synthesis failed; the run's
  own exit code still reflects the synthesis failure (§9). `runner.py`'s failure handler
  catches bare `Exception`, not just the tool's own error types — an unexpected `OSError`
  (e.g. the share vanishing mid-write, a TOCTOU race past `mount.py`'s check; §10) must
  trigger this guarantee too, not bypass it by virtue of not being one of the tool's own
  types. The retry is itself idempotent: a second `commit`/`push` attempt in the same run
  never double-commits, double-exports, or double-pushes (tracked via `ctx.committed`
  only ever transitioning false→true, and a `ctx.push_attempted` guard) — `git push`
  isn't guaranteed safe to run twice for one failure (a remote-side webhook, for one).
- **Cost logging** — every `claude -p` call appends one JSON record to `log.file`'s
  companion cost log: `{timestamp, role, job, date, model, total_cost_usd, num_turns,
  duration_ms}`. Append-only, one line per call, machine-parseable. This is a direct
  port of the host's existing JSON-result parsing (`total_cost_usd`/`num_turns`/
  `duration_ms`), generalized to both roles.
- **Budget** — `limits.max_budget_usd`: `0` means no hard cap (host default — cost is
  logged, not gated); a nonzero value is passed as `--max-budget-usd` and a run that
  would exceed it is aborted by `claude` itself (VM default `1.00`, carried over from
  the incident history that motivated it).
- **Logging** — structured, leveled (`log.level`), to `log.file` and stdout; `--verbose`
  raises detail. Secrets are never logged (there are none in config — see §13).
- **Failure taxonomy** — every failure maps to one exit code (§9); config/claude/commit
  failures are not silently retried within a run, but a scheduled re-run the next period
  naturally retries (idempotent by design, §11).

---

## 13. Security & Data Durability

- **What's on GitHub:** only the **host** data repo's entries, pushed by the host role.
  The tool repo may be public or private independently of the data repo's visibility.
- **What is NOT on GitHub, ever:** raw session transcripts, cost logs, per-machine
  config (paths are not secret, but are not committed — `config/local.toml` is
  gitignored), share contents, and nothing from the VM's local data repo (which is
  never pushed anywhere, §4).
- **Secrets/auth:** git authentication uses the host's existing SSH credential (the
  `github-personal` alias/key already configured on this machine) — the tool reads,
  stores, and logs no tokens itself. `claude` authentication is whatever `claude` itself
  already uses on each machine; ddp-diary does not manage the credentials, but it *does*
  choose **which** logged-in account is used: `claude.config_dir` (§7) sets
  `CLAUDE_CONFIG_DIR` for the `claude -p` subprocess, pinning it to a specific config
  directory (and its `/projects` transcripts) regardless of the default `~/.claude`
  login. On the host this is pinned to the personal account (`.claude-personal`) so the
  journal never accidentally summarizes or reads sessions under a work account if the
  default login is switched. It never reads the token inside that dir — only points
  `claude` at it.
- **Durability:** the VM's local commit history is independent of the share; the host's
  GitHub push is the durable, externally-visible copy. The share is **transient
  transport only** — losing it loses nothing permanent, because nothing is copy-only
  deleted and the VM repo retains its own history regardless.

---

## 14. Testing & Verification

- **`--dry-run`** — proves config resolution, extraction, and prompt assembly without
  touching git, the share, or `claude`. Run on each machine before trusting a config
  change.
- **`doctor`** — checks: config validity (exit `2` on failure); every resolved path
  exists and is read/writable as required (exit `2`); the share is mounted (`WARN`, not
  `FAIL` — see §10; contributes `0` to the exit code either way); `claude.bin` resolves
  and is runnable (exit `3` — the same code a real `claude` launch failure would produce);
  the git remote is reachable, checked whenever `git.push` is true regardless of role
  (exit `5` — what a real push failure there would produce). The overall exit code is
  the *worst* (highest) code among all `FAIL`ed checks, `0` if none failed.
- **Nightly-run acceptance (per machine)** — pick a known date, run for real, then
  assert: the entry file exists with the correct sections for its period; a cost record
  was appended; a local commit exists for it; (host) the commit reached GitHub.
- **Determinism/idempotency tests** — re-running the same `--job`/`--date` produces no
  duplicate entry or commit (§11 dedup); re-running `sync` copies/ingests nothing new.
- **Unit vs. integration:** extractor date-slicing, cursor advancement, ingest glob
  matching, and dedup-identity logic are unit-tested with fixtures (`tests/fixtures/`)
  and no real `claude`/git/share dependency. The `claude` call, git commit/push, and
  share mount are integration-tested against a real (scratch) git repo and a real
  temp directory standing in for the share.

---

## 15. Versioned Roadmap

- **v1 — core** (this spec, §1's ten items). Acceptance: §16.
- **Future phase A — SQLite/FTS transcript index.** Fixes the lossy, bounded skim
  (`limits.skim_max_files/skim_max_lines`) and doubles as cross-project activity
  tracking. v1 must not preclude it: `session_extract.py` already returns typed
  `SessionRecord` objects, and re-running extraction over history is safe (pure
  function of the `.jsonl` files) — a future `[store]` config section and a
  `TranscriptStore` sink are the only additions needed.
- **Future phase B — Obsidian-friendly output.** Frontmatter (`product:`, tags),
  `[[wikilinks]]` on recurring entities (KB numbers, ticket IDs), and a starter vault
  config. Layers onto the entry writer; does not change the sync contract (§11). A
  future `[publish]` config section and a `Publisher` sink after commit.
- **Future phase C — optional MCP server.** Exposes `runner.run_job()` (and possibly
  `session_extract`) as MCP tools. Possible only because `cli.py` is a thin wrapper over
  a clean library call (§6) — no core changes needed to add this later. A future
  `[mcp]` config section.

Each future phase gets its own spec version bump and its own acceptance criteria when
it is actually scoped — none is designed further than "documented + seamed" here.

---

## 16. v1 "Done" — Acceptance Criteria

- [ ] One tool repo, cloned on both host and VM, drives both via `config.role`.
- [ ] `daily`/`weekly`/`monthly` synthesis produces correctly-sectioned entries via
  `claude -p` from date-sliced session input.
- [ ] VM→share→host→GitHub flow completes unattended on each machine's own schedule.
- [ ] Conventions and prompts are single-sourced in this repo (git), never duplicated
  per machine.
- [ ] Date-sliced extraction is correct across a day boundary and bounded (never reads
  a whole transcript).
- [ ] Every `claude -p` call logs a JSON cost record.
- [ ] Host push runs even after a failed synthesis (commits are never stranded).
- [ ] Backfill and dedup are idempotent (re-running changes nothing already correct).
- [ ] Mount-race and missing-share guards proven (a run survives an absent share on
  both roles without crashing).
- [ ] `--dry-run` and `doctor` pass on both machines.
- [ ] A real, supervised nightly run passes the acceptance check in §14 on **both**
  host and VM.

v1 is "done" only when every box above is checked on both machines — not when the code
merely compiles.

---

## 17. Open Questions & Decisions Log

### Decisions (ADR-lite — newest first)

- **2026-07-24 — Three usability improvements after the first real production
  run: auto-backfill (off by default), `status`, relative `--date` aliases.**
  All additive; `run_job`'s signature and idempotency logic untouched; the
  138-test suite (104 → 138) passed with zero regressions. Design was
  independently pressure-tested against the real deployed config/logs/journal
  (not just the source) before implementation — one correction came out of
  that: `limits.backfill_days` ships `0` (off) on both roles, not `7` as
  first drafted, specifically because host has no cost ceiling
  (`max_budget_usd = 0`) and the night it would matter most (several days
  away) is exactly the night no one is watching it fire for the first time.
  (1) `session_extract.dates_with_activity()` — dead code since the initial
  build, restoring the original VM script's auto-fill-the-past-week
  behavior — is now called by `runner.backfill_missing_days()`, wired through
  a new `runner.run_daily_with_backfill()` that `cli.py` routes to precisely
  when `--job daily` has no explicit `--date` (the real scheduled launcher's
  exact invocation); an explicit `--date` (even `today`) bypasses it and
  calls the unchanged `run_job` directly. Bounded by both `backfill_days`
  (how far back to look) and the new, independent `backfill_max_per_run`
  (how many missing dates get processed in one run — decoupled so a sparse
  history with a wide window can't queue unbounded `claude` calls). (2)
  `ddp-diary status` — new read-only command answering "did it work" in one
  command instead of manually chaining `git log`/log-tail/`doctor`; new
  `gitops.read_status()` (never raises; `ahead`/`behind` are `None` with no
  tracked upstream) and a promoted `doctor.print_resolved_config` (was
  private, safe rename, shared by both `-v` flags). Deliberately does **not**
  trust the cost-log JSONL alone for success/failure — `record_cost()` only
  writes on a successful `claude` call, so after a failure the JSONL would
  silently show stale success data from a prior night; instead scans the
  plain-text log's `started`/`ended` banner pair for an intervening `FAILED`
  line, then pairs that signal with the JSONL's last line for cost detail on
  an actual success. Guarded by a regression test proving this exact
  stale-JSONL trap can't happen. (3) `--date` accepts case-insensitive
  `today`/`yesterday` (both `run --date` and `backfill --from/--to`); a bad
  format now raises `ConfigError` → exit `2`, correcting a prior bare
  `ValueError` → exit `1` (confirmed no test locked in the old code). This
  same night's real production run (the first genuinely unattended one)
  incidentally became the first real-world proof of both this session's
  earlier "extend, don't overwrite" prompt fix and the `claude.config_dir`
  account pin — `status` showed the run OK, extending (not duplicating) an
  entry already present from an earlier manual test, pushed under the
  personal account.
- **2026-07-23 — Pin the summarizing account via `claude.config_dir`.** The host has a
  dual-account Claude setup (`~/.claude-personal` = personal account,
  `~/.claude-work` = work account, each a self-contained `CLAUDE_CONFIG_DIR`
  target). Since ddp-diary just runs `claude -p`, it would otherwise inherit whichever
  account the default `~/.claude` login happened to be at run time — so switching the
  active login to work would silently make the *journal* summarize and read sessions
  under the work account. Added a `claude.config_dir` config key: when set, the core
  exports `CLAUDE_CONFIG_DIR` for the `claude` subprocess (`claude_client._build_env`)
  *and* derives `paths.claude_projects` from `<config_dir>/projects`, so both the
  summarizing account and the session source are pinned together. `host.toml` pins
  `.claude-personal`. Verified with a real `claude -p` call under the pin (clean
  `is_error:false` completion, ~$0.03). Empty `""` keeps the old inherit-the-default
  behavior. Guarded by `test_config.py` (resolution + projects derivation) and
  `test_claude_client.py` (the `CLAUDE_CONFIG_DIR` env is passed to the subprocess).
- **2026-07-23 — Restored dropped "extend an existing same-date entry" prompt rule.**
  The first real production run surfaced a regression: `assets/prompts/tasks/daily.md`
  had no instruction for the case where an entry for the target date *already exists*
  (e.g. a manual run earlier the same day, then the scheduled 21:00 run). The original
  VM script's prompt had *"if today's file already exists from an earlier run, extend
  it — don't duplicate or overwrite"*; the rewrite lost it, so a second same-day run
  risked clobbering the first entry. Restored it: step 1 now reads the most recent
  *prior* day for continuity and separately notes an existing same-date entry; step 3
  says to extend/refine an existing same-date entry rather than overwrite. Guarded by
  `tests/test_prompts.py::test_daily_prompt_instructs_extend_not_overwrite_when_entry_exists`.
- **2026-07-21 — Post-build adversarial review, two independent passes.** Two review
  agents (correctness/cross-platform; spec-fidelity/completeness) read the finished
  v1 codebase against this spec and found real, concrete bugs — not just wording
  mismatches. Fixed: (1) `sync/ingest.py` silently overwrote a same-named, not-yet-
  processed `inbox/` file (spec's ingest-conflict rule was entirely unimplemented) —
  now skips and reports via `IngestResult.skipped_conflicts`. (2) A TOCTOU race —
  `mount.is_available()` passing but the actual write then failing (share vanishes
  mid-run) — raised a bare `OSError` that bypassed `runner.py`'s failure handling
  entirely (since it only caught `DdpDiaryError`), defeating the always-push
  guarantee and leaking a raw traceback through `cli.py`. Fixed at two layers:
  `sync/export.py`/`sync/ingest.py` now catch `OSError` around their real file
  operations and degrade like "share unavailable"; `runner.py`'s and `cli.py`'s
  exception handling broadened from `DdpDiaryError` to bare `Exception` as
  defense in depth for any other unexpected failure. (3) The failure-retry path
  could invoke `git push` twice for one failure (when the push itself was what
  failed) — fixed with a `ctx.push_attempted` guard, plus made `ctx.committed`
  sticky (false→true only) so a no-op retry commit can't reset it and
  double-trigger `role.after_commit`. (4) `claude_client.run()` only checked the
  process exit code and JSON-parseability, never the result's own `is_error`/
  `subtype` fields — a run that silently hit `--max-turns`/`--max-budget-usd`
  would exit 0 with valid JSON and be treated as full success; now raises on
  `is_error: true`. (5) `doctor.py` flattened every failing check to exit code 2
  and never actually differentiated by failure type despite spec claiming
  otherwise; rewritten to map each check to the exit code its failure would
  really cause in a `run` (`claude` executable → 3, git remote → 5 gated on
  `git.push` not role, others → 2), and its `-v` flag — previously accepted and
  silently ignored — now prints the resolved config. (6) The unknown-config-key
  warning spec.md §7 promised didn't exist; implemented in `config.py`. (7) The
  VM-only-runs-`daily` rule existed only as scheduling convention and prompt
  text, not an enforced invariant; `runner.run_job()` now raises `ConfigError`
  for `role=vm, job!=daily`. Also **corrected spec text to match already-correct,
  intentional code** rather than changing behavior: §7's precedence table had
  `local.toml` and the role config file in the wrong order (code, its own
  docstring, and the passing test all already agreed `local.toml` should win —
  only the table was backwards); §8's prompt-assembly order was documented
  backwards from what the role-fragment prose itself requires (digest must
  render before the role fragment for "the activity summary above" to make
  sense); §10 overclaimed using `os.path.ismount()` when the actual (more
  portable) implementation is existence + a write probe. Added 96 new/updated
  tests (68 → 96) covering every fix above plus a new end-to-end VM-export →
  host-ingest chained test.
- **2026-07-20 — Two data repos, one tool repo.** The VM keeps its own local, unpushed
  git repo (own history/diffability, independent of the share). The host's data repo is
  the single canonical, GitHub-pushed record. *Why:* considered collapsing to one data
  repo entirely (VM writes straight to the share, no VM git) — rejected because the
  user wants VM-side `git log`/diff for its own history even though it's never
  published; the marginal git overhead is worth that.
- **2026-07-20 — Conventions ship inside the tool repo, concatenated into the prompt.**
  Not read from a `CLAUDE.md` in the data repo, and not delivered via the share. *Why:*
  single source of truth reachable by `git pull` on both machines; removes the mount
  dependency for rules entirely (only entries still depend on the share).
  **Reversed** the original bootstrap design where conventions were mirrored into the
  share (`mirror_journal()`); that mirroring is dropped (see `sync.mirror = false`, §7).
- **2026-07-20 — Core owns git and session extraction; Claude does not.** The headless
  run only writes the entry file and (host) moves inbox items; `gitops.py` commits and
  pushes deterministically, and `session_extract.py` pre-digests sessions before the
  prompt is built. *Why:* shrinks Claude's tool surface, makes commit messages uniform,
  and turns "skim cheaply" from a prompt-level plea into bounded, testable code.
- **2026-07-20 — v1 scope is core pipeline only.** SQLite index, Obsidian output, and
  MCP are documented in §15 but not built. *Why:* ship one coherent, verifiable tool
  before layering on discovery/consumption features.
- **2026-07-20 — TOML for config**, not JSON/YAML/ini. *Why:* human-editable with
  comments, and `tomllib` is stdlib on modern Python — no dependency for the common case.

### Open questions

- **Model id split** (`open`) — host uses `sonnet`, VM uses `claude-sonnet-5`. Kept
  per-role rather than force-unified for now; revisit whether these should converge.
- **`$SHARE/journal/` mirror** (`decided`, leaning) — recommendation is to drop it
  (`sync.mirror = false`); the share then carries only the entry export, and the VM's
  own git history + a pre-migration `git bundle` (see the migration plan) are the
  backup. Keep only if a browsable VM backup on the host's side of the share is wanted.
- **"ddp" naming** (`open`, low priority) — currently treated as a plain proper noun
  with no expansion (§2). Revisit only if that turns out to matter.
- **State/log location** (`decided`) — `ddp-diary/state/` (gitignored), replacing
  `cron.log` living inside the data repos.
- **S4U scheduled-task changes** (`open`, operational) — require an elevated shell to
  re-register; this is a manual step performed by the user during migration, not
  something the tool automates in v1.
