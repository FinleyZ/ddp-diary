Write this week's journal digest. Determine today's date and ISO week from the environment (run `date` if unsure). Read the last 7 files in `daily/` (never inbox). Write `weekly/YYYY-Www.md`.

This is NOT a status report — it's an editorial digest of my week, the kind a witty newsletter editor would write about one engineer's seven days. First person, honest, lightly wry. No filler, no motivational fluff, and absolutely no code-level detail (no function names, line numbers, or branch names — talk at the level of tasks, storylines, and stakes).

Structure:

# Week NN · <date range>

## Topics of the week
Pick the 2–4 threads that actually defined the week. Each gets:
- a short, punchy headline capturing the arc (a twist, an irony, a turning point — not a task name)
- ONE narrative paragraph telling the story: what I was chasing, how it moved or refused to move, the surprise or payoff. Anchor each with at least one concrete moment by date ("on Tuesday the customer log finally settled the argument"). If a thread was several days of grind, say what the grind was about, not what each day did.

## Odds and ends
3–6 one-liners for the leftovers: small wins, tiny absurdities, things noticed in passing. Texture, not paragraphs.

## Do better
The week's self-review, built from the dailies' "Do better" items plus patterns you can see across the seven days. 2–3 short paragraphs: how I used AI this week (what worked, what I kept doing the hard way, what I should delegate or prompt differently) and how I thought (recurring blind spots, where I moved fast vs. spun in place, one keep-doing and one stop-doing, said plainly). Only patterns with evidence in the dailies — skip what you can't back up.

## One small observation
One zoomed-out reflective paragraph about the week as a whole — a durable takeaway or a pattern in the shape of the week, the kind of thing worth remembering in a year.

If the week's dailies are thin, write a shorter honest digest — never pad, never invent. Then `git add -A && git commit -m "journal: weekly YYYY-Www"`. Do not push — the wrapper script handles that.
