# Weekly journal digest

Write this week's journal digest for the week given in the Context block above (ISO
week identifier and date range already computed by the orchestrator). Read the last 7
files in `daily/` (never `inbox/`). Write `weekly/<iso-week>.md`.

This is NOT a status report — it's an editorial digest of the week, the kind a witty
newsletter editor would write about one engineer's seven days. First person, honest,
lightly wry. No filler, no motivational fluff, and absolutely no code-level detail (no
function names, line numbers, or branch names — talk at the level of tasks,
storylines, and stakes).

## Structure

```
# Week <NN> · <date range>

## Topics of the week
## Odds and ends
## Do better
## One small observation
```

- **Topics of the week** — pick the 2-4 threads that actually defined the week. Each
  gets a short, punchy headline capturing the arc (a twist, an irony, a turning point —
  not a task name), and ONE narrative paragraph telling the story: what you were
  chasing, how it moved or refused to move, the surprise or payoff. Anchor each with at
  least one concrete moment by date. If a thread was several days of grind, say what
  the grind was about, not what each day did.
- **Odds and ends** — 3-6 one-liners for the leftovers: small wins, tiny absurdities,
  things noticed in passing. Texture, not paragraphs.
- **Do better** — the week's self-review, built from the dailies' "Do better" items
  plus patterns visible across the seven days. 2-3 short paragraphs: how AI was used
  this week (what worked, what stayed manual, what should be delegated or prompted
  differently) and how you thought (recurring blind spots, where you moved fast vs.
  spun in place, one keep-doing and one stop-doing, said plainly). Only patterns with
  evidence in the dailies — skip what you can't back up.
- **One small observation** — one zoomed-out reflective paragraph about the week as a
  whole — a durable takeaway or a pattern in the shape of the week, worth remembering
  in a year.

If the week's dailies are thin, write a shorter honest digest — never pad, never
invent.

## Stop there

Do not run `git add`, `git commit`, or `git push`. The orchestrator commits after you
finish writing.
