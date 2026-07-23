# Journal rules

This repo is a personal engineering diary written by automated Claude Code runs.

## Tone

Factual, first person, concise. No filler, no motivational fluff.

## Entry types

- **Daily** (`daily/YYYY-MM-DD.md`) uses exactly these sections: `## Did`, `## Learned`, `## Stuck or open questions`, `## Do better`, `## Tomorrow`. Skip a section entirely if it is empty — never pad. Did = tasks and their state, never code-level detail. Learned = durable, transferable knowledge only. Do better = evidence-based self-review (AI usage, thinking habits).
- **Weekly** (`weekly/YYYY-Www.md`) is an editorial digest, not a status report: 2–4 themed stories of the week with punchy headlines, an odds-and-ends list, a Do-better self-review built from the dailies, and one zoomed-out observation. Reference at least one concrete daily moment by date. No code-level detail.
- **Monthly** (`monthly/YYYY-MM.md`) covers trajectory: skills leveled up, projects opened/closed, whether the month went where intended. The monthly run is the ONLY one allowed to edit `LONG_TERM.md`.

## Inbox

`inbox/` is raw input (VM notes, quick thoughts, snippets). After a daily run folds inbox content into the entry, move the processed files to `inbox/processed/` — never delete them.

## Git

Every run ends with `git add -A && git commit -m "journal: <scope> <date>"` where scope is daily, weekly, or monthly. Do not push — the wrapper script pushes automatically after each successful run.

## Honesty

Never invent activity. If a day has no data, write a one-line entry saying so.
