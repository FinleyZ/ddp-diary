# Journal conventions

This repo is a personal engineering diary written by automated Claude Code runs. These
rules are the single source of truth for both machines — see spec.md §8. Do not restate
or duplicate them in a per-machine file; if a rule needs to change, change it here.

## Tone

Factual, first person, concise. No filler, no motivational fluff.

## Entry types

- **Daily** uses exactly these sections: `## Did`, `## Learned`, `## Stuck or open
  questions`, `## Do better`, `## Tomorrow`. Skip a section entirely if it is empty —
  never pad. Did = tasks and their state, never code-level detail. Learned = durable,
  transferable knowledge only. Do better = evidence-based self-review (AI usage,
  thinking habits).
- **Weekly** is an editorial digest, not a status report: 2–4 themed stories of the
  week with punchy headlines, an odds-and-ends list, a Do-better self-review built from
  the dailies, and one zoomed-out observation. Reference at least one concrete daily
  moment by date. No code-level detail.
- **Monthly** covers trajectory: skills leveled up, projects opened/closed, whether the
  month went where intended. The monthly run is the ONLY one allowed to edit
  `LONG_TERM.md`, and only conservatively — most months should not change it.

## Altitude

- **Did** is task-level, not code-level: tasks and their state (advanced / blocked /
  shipped / verified), one line each — no function names, commit hashes, register
  addresses, or line-level detail; that lives in git history and KB entries.
- **Learned** is durable knowledge only: transferable principles and gotchas still worth
  caring about in a year, stated as general lessons — task-specific detail folds into
  Did or gets dropped.

## Honesty

Never invent activity. If a day has no data, write a one-line entry saying so.

## Git

Every run writes/extends the entry file; the **core** (not this Claude invocation)
performs `git add -A && git commit` and, on the host, `git push` — see spec.md §12.
This Claude run does not need to touch git for the data repo at all.
