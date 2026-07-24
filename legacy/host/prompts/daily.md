Write today's daily journal entry. Follow CLAUDE.md conventions exactly. Determine today's date from the environment (run `date` if unsure) — do not guess it.

## 1. Gather input

- Read every file in `inbox/` (skip `inbox/processed/`). This is raw input: VM notes, quick thoughts, snippets.
- `inbox/vm-daily-*.md` files are exported daily entries from the Linux VM's own journal (firmware work). Treat them as the authoritative record of that day's VM work: fold the substance into today's entry, don't copy them verbatim.
- **Backfill rule:** if a `vm-daily-YYYY-MM-DD.md` is dated BEFORE today (late export), do not fold it into today's entry. Merge it into `daily/` for its own date instead: create that day's file if missing (note it as backfilled), or add to the existing entry without duplicating.
- Best-effort: skim Claude Code session history under `C:\Users\<you>\.claude\projects\` for what I worked on today. Only look at `.jsonl` files whose last-modified time is today. If the format is unreadable or inaccessible, silently fall back to inbox-only — do NOT fail the run.
- **Skim cheaply — this is a hard budget rule.** Session files can be enormous; NEVER read one whole. Per file: Grep for user-role messages and summaries first, then Read at most ~200 lines around the interesting parts. Cover at most the 5 most recently modified session files. You have a fixed dollar budget for the entire run; spend at most a third of your effort gathering — a decent entry that commits beats a perfect one that dies mid-run. Do not write helper/scratch scripts (you cannot delete files here; they litter the repo).
- **Multi-day session rule:** sessions can span multiple days. Include ONLY activity whose message timestamps fall on today's date — slice spanning sessions by timestamp, never summarize a whole file just because it was modified today.
- While skimming sessions, also note HOW I worked, not just what: prompts that needed many retries, context I failed to give up front, rabbit holes, moments where I accepted an answer without verifying, or where I did by hand what I could have delegated. This feeds the "Do better" section.

## 2. Dedup against yesterday

Before writing, read the most recent existing file in `daily/`. Do not repeat work already journaled there. If today continued that work, frame it as a continuation ("continued the UART driver from yesterday: interrupt handler works, DMA still pending") rather than re-describing it.

## 3. Write

Write `daily/YYYY-MM-DD.md` (today's date) with exactly these sections, skipping any that are empty. If there is genuinely no data for today, write a one-line entry saying so — never invent activity.

- **## Did** — TASKS, not code. Name each task and its state (advanced / blocked / shipped / verified) in one line. No function names, commit hashes, register addresses, or line-level detail — that lives in git history and KB entries, not here.
- **## Learned** — durable knowledge only: skills, transferable principles, gotchas I'd still care about in a year, stated as general lessons. If a lesson only matters inside this one task, fold it into the Did line or drop it.
- **## Stuck or open questions** — what's genuinely blocked or unresolved.
- **## Do better** — 1–3 honest, evidence-based observations about how I could work smarter, drawn from today's actual sessions and notes: how I used AI (prompting, context-giving, delegation, verification of its output), and how I thought (assumptions I didn't check, conclusions I jumped to, time spent where it didn't matter). Be specific and cite the moment ("burned an hour re-explaining the build setup — that belongs in the project's CLAUDE.md"). No generic advice, no manufactured criticism — skip the section entirely rather than pad it.
- **## Tomorrow** — carry-overs and intentions.

## 4. Clean up and commit

- Move each inbox file whose content you folded into the entry to `inbox/processed/` (use `mv`; never delete). If `inbox/vm-notes.md` had content, move it as `inbox/processed/vm-notes-YYYY-MM-DD.md` so the VM starts fresh. Leave untouched any inbox file you did not use.
- `git add -A && git commit -m "journal: daily YYYY-MM-DD"`. Do not push — the wrapper script handles that.
