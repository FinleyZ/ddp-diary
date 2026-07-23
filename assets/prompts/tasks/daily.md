# Daily journal entry

Write today's daily journal entry for the target date given in the Context block
above (the orchestrator computed and injected it — do not re-derive or guess the
date). Follow the conventions above exactly.

## 1. Review recent history

Read the most recent *prior* day's entry in `daily/` — the newest file dated before
the target date (skip `inbox/`). Do not repeat work already journaled there; if today
continues that work, frame it as a continuation ("continued the UART driver from
yesterday: interrupt handler works, DMA still pending") rather than re-describing it.

Also check whether an entry for the **target date itself** already exists (from an
earlier run the same day). If it does, read it — in step 3 you will extend and refine
it, not overwrite it.

## 2. Gather input

Use the activity summary provided below (already extracted and bounded by the
orchestrator from this machine's Claude Code sessions) as your primary "what did I do
today" input. Do not attempt to read raw session transcripts yourself — the summary
below already is that input, sliced to this date.

If a role-specific section appears after this one, it describes additional input
sources for this machine (e.g. an inbox of external notes) — read that section too
before writing.

## 3. Write

Write `daily/<target-date>.md` with exactly these sections, skipping any that are
empty. **If an entry for the target date already exists** (an earlier run the same
day, per step 1), extend and refine it — merge in any new activity, don't duplicate
lines already there and don't blindly overwrite what's already been captured. If there
is genuinely no data for today, write a one-line entry saying so — never invent
activity.

- **## Did** — tasks and their state (advanced / blocked / shipped / verified), one
  line each.
- **## Learned** — durable knowledge only.
- **## Stuck or open questions** — what's genuinely blocked or unresolved.
- **## Do better** — 1-3 honest, evidence-based observations about how you could have
  worked smarter today (AI usage, thinking habits), each cited to an actual moment.
  Skip the section entirely rather than pad it with generic advice.
- **## Tomorrow** — carry-overs and intentions.

## 4. Stop there

Do not run `git add`, `git commit`, or `git push`, and do not attempt to push or touch
any shared/network folder. The orchestrator handles git and sync after you finish
writing (and, on the host, after any inbox archival described in the role-specific
section below).
