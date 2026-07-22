# Host-specific mechanics

You are running on the **host** machine. The following applies to the `daily` job only
— ignore this section for `weekly`/`monthly`.

## Additional input: inbox

Read every file in `inbox/` (skip `inbox/processed/`). The orchestrator has already
moved any new files here from the shared folder before invoking you — this is raw
input: VM notes, quick thoughts, and `vm-daily-*.md` files exported from the Linux VM's
own journal (firmware work). This is a SEPARATE source from the activity summary above
(which covers only this machine's own Claude Code sessions) — read both.

- Treat `vm-daily-*.md` files as the authoritative record of that VM day's work: fold
  the substance into the relevant entry, don't copy them verbatim.
- **Backfill rule:** if a `vm-daily-YYYY-MM-DD.md` is dated BEFORE today, do NOT fold it
  into today's entry. Instead write or extend `daily/YYYY-MM-DD.md` for its own date
  (note it as backfilled) — a late VM export must never bleed into today's file.
- `inbox/vm-notes.md` (if present and non-empty) is a running scratch file of quick
  notes, not a dated export — fold anything usable into today's entry.

## Cleanup

After folding a file's content into an entry, move it to `inbox/processed/` (use `mv`;
never delete — this is the permanent archive, not a scratch space). Leave untouched any
inbox file you did not use this run. If `inbox/vm-notes.md` had content you used, move
it as `inbox/processed/vm-notes-<target-date>.md` so the VM's next export starts fresh.

Do not run `git add`, `git commit`, or `git push` — the orchestrator does this after
you finish writing and archiving.
