Write last month's monthly journal entry. Follow CLAUDE.md conventions exactly. Determine the date from the environment (run `date` if unsure); "last month" is the calendar month that just ended.

- Read last month's files in `weekly/` (the weeklies whose weeks fall mostly in that month).
- Cover trajectory: skills leveled up, projects opened/closed, whether the month went where intended.
- Write `monthly/YYYY-MM.md` for last month.
- Update `LONG_TERM.md` ONLY if something genuinely graduates to long-term (a skill or theme that persisted across the month). Be conservative — most months should not change it. This is the only run allowed to edit LONG_TERM.md.
- If there are no weeklies for last month, write a one-line entry saying so — never invent activity.
- `git add -A && git commit -m "journal: monthly YYYY-MM"`. Do not push — the wrapper script handles that.
