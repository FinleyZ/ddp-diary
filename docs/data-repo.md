# Setting up a data repo

ddp-diary is the **tool** only — journal entries live in a separate **data
repo** per machine. See [spec.md §4](../spec.md) and §17's decisions log for
why there are two (host: GitHub-pushed canonical record; VM: local, unpushed).

## Layout a data repo needs

```
daily/
weekly/
monthly/
inbox/
inbox/processed/
LONG_TERM.md
```

No `CLAUDE.md`, no scripts, no prompts — those live in this tool repo and are
injected into the prompt at runtime (spec.md §8).

## Initializing a new data repo

```
mkdir -p daily weekly monthly inbox/processed
touch LONG_TERM.md
git init
git add -A && git commit -m "init"
```

The host additionally needs a GitHub remote (`git remote add origin ...`) for
`git.push = true` to have somewhere to push. The VM role never pushes, so no
remote is required there — see `config/vm.toml`'s `git.push = false`.

This file intentionally stays thin — spec.md is the source of truth.
