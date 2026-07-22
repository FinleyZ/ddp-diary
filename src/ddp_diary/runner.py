"""The role-agnostic orchestration spine (spec.md §4's DATA channel, in code).

Every job (`daily`/`weekly`/`monthly`) runs the same sequence; only the two
`Role` hooks (`before_run`, `after_commit`) differ by machine — see spec.md §5.
This is the clean library entry point a future MCP server would call directly
(spec.md §15, future phase C) — `cli.py` is a thin wrapper over this function
and nothing more.
"""

from __future__ import annotations

import datetime
from typing import Optional

from . import claude_client, gitops, logging_setup, prompts, roles, session_extract
from .errors import ConfigError, GitPushError
from .models import Config, Job, RunContext


def run_job(
    config: Config,
    job: Job,
    *,
    target_date: Optional[datetime.date] = None,
    dry_run: bool = False,
    no_push: bool = False,
    verbose: bool = False,
) -> RunContext:
    """Run one period's synthesis end to end: role gather -> extract (daily) ->
    assemble prompt -> invoke claude -> commit -> role export -> push.

    Re-raises the triggering exception after best-effort commit+push, so
    `cli.py` can map it to the right exit code (spec.md §9) while still
    honoring the always-push-after-failure rule (spec.md §12). The except
    clause below deliberately catches bare `Exception`, not just
    `DdpDiaryError` — an unexpected `OSError` (e.g. the share vanishing
    between `mount.is_available()`'s check and the actual write — a TOCTOU
    race) must still trigger the always-push guarantee and a clean error
    message, not bypass both by virtue of not being one of our own types.
    """
    if config.role == "vm" and job != "daily":
        raise ConfigError(f"the vm role does not run '{job}' jobs (spec.md §5) — only 'daily' runs on vm")

    target_date = target_date or datetime.date.today()
    ctx = RunContext(
        config=config,
        job=job,
        target_date=target_date,
        dry_run=dry_run,
        no_push=no_push,
        verbose=verbose,
    )
    ctx.echo = verbose or config.log.level == "debug"
    role = roles.for_role(config.role)

    logging_setup.banner(config, f"{job} started", echo=ctx.echo)
    try:
        role.before_run(ctx)

        if job == "daily":
            records, digest = session_extract.extract_for_date(
                config.claude_projects,
                target_date,
                skim_max_files=config.limits.skim_max_files,
                skim_max_lines=config.limits.skim_max_lines,
            )
            ctx.session_records = records
            ctx.digest_text = digest

        ctx.prompt_text = prompts.assemble(job, config.role, target_date, digest_text=ctx.digest_text)

        if dry_run:
            logging_setup.log(config, f"dry-run: would invoke claude ({len(ctx.prompt_text)} prompt chars)", echo=ctx.echo)
        else:
            result = claude_client.run(
                ctx.prompt_text,
                claude_cfg=config.claude,
                limits=config.limits,
                cwd=config.data_dir,
            )
            ctx.claude_result = result
            logging_setup.cost_line(config, result, echo=ctx.echo)
            logging_setup.record_cost(
                config,
                role=config.role,
                job=job,
                date_str=target_date.isoformat(),
                model=config.claude.model,
                result=result,
            )

        _commit_and_push(ctx, role)

    except Exception as exc:
        logging_setup.failure(config, f"{job}: {exc}", echo=ctx.echo)
        _commit_and_push(ctx, role, best_effort=True)
        raise
    finally:
        logging_setup.banner(config, f"{job} ended", echo=ctx.echo)

    return ctx


def _commit_and_push(ctx: RunContext, role: roles.Role, *, best_effort: bool = False) -> None:
    """Commit whatever is staged, run the role's post-commit hook, then push.

    Called once on the success path and again (with `best_effort=True`) from
    the failure handler above — so this function must be safe to call twice
    in one run without double-committing, double-exporting, or double-pushing:
    - `ctx.committed` only ever transitions False -> True (never gets reset
      back to False by a second, no-op commit attempt), so `role.after_commit`
      only fires on the call that actually produced a fresh commit.
    - `ctx.push_attempted` guards push itself: if the FIRST call's own push is
      what failed (raising `GitPushError`, caught above), the retry call must
      not attempt push again — `git push` isn't guaranteed idempotent-safe
      against every possible remote-side effect (e.g. a webhook).
    """
    config = ctx.config
    if ctx.dry_run:
        logging_setup.log(config, "dry-run: would commit" + (" and push" if config.git.push else ""), echo=ctx.echo)
        return

    committed_this_call = False
    try:
        committed_this_call = gitops.commit(config.data_dir, config.git, scope=ctx.job, date_str=ctx.target_date.isoformat())
    except Exception:
        if not best_effort:
            raise

    if committed_this_call:
        ctx.committed = True
        role.after_commit(ctx)

    if ctx.push_attempted:
        return

    should_push = config.git.push and not ctx.no_push and (config.git.push_even_on_failure or ctx.committed)
    if should_push:
        ctx.push_attempted = True
        ok, err = gitops.push(config.data_dir, config.git)
        ctx.pushed = ok
        if not ok:
            logging_setup.failure(config, f"push ({err})", echo=ctx.echo)
            if not best_effort:
                raise GitPushError(err or "push failed")
