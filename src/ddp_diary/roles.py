"""Role abstraction: `HostRole` and `VmRole` differ only in two hooks around an
otherwise identical orchestration spine (spec.md §5). Adding a third role, if
ever needed, means adding one more subclass here — nothing else in the core
would change.
"""

from __future__ import annotations

import abc

from . import logging_setup
from .models import RunContext
from .sync import export as sync_export
from .sync import ingest as sync_ingest


class Role(abc.ABC):
    @abc.abstractmethod
    def before_run(self, ctx: RunContext) -> None: ...

    @abc.abstractmethod
    def after_commit(self, ctx: RunContext) -> None: ...


class HostRole(Role):
    """Ingests from the share before synthesis; never exports (host is the only
    publisher — it pushes to GitHub instead, handled in `gitops`/`runner`)."""

    def before_run(self, ctx: RunContext) -> None:
        if ctx.job != "daily":
            return
        if ctx.dry_run:
            logging_setup.log(ctx.config, "dry-run: would ingest from share", echo=ctx.echo)
            return
        result = sync_ingest.run(ctx.config)
        if result.ingested:
            logging_setup.log(ctx.config, f"ingested from share: {', '.join(result.ingested)}", echo=ctx.echo)
        if result.skipped_conflicts:
            logging_setup.log(
                ctx.config,
                f"WARNING: ingest conflict, left on share (inbox already has these): {', '.join(result.skipped_conflicts)}",
                echo=ctx.echo,
            )

    def after_commit(self, ctx: RunContext) -> None:
        pass


class VmRole(Role):
    """Nothing to gather beyond session extraction; exports new dailies to the
    share after a successful local commit. Never pushes to GitHub."""

    def before_run(self, ctx: RunContext) -> None:
        pass

    def after_commit(self, ctx: RunContext) -> None:
        if ctx.job != "daily":
            return
        if ctx.dry_run:
            logging_setup.log(ctx.config, "dry-run: would export new dailies to share", echo=ctx.echo)
            return
        exported = sync_export.run(ctx.config)
        if exported:
            logging_setup.log(ctx.config, f"exported to share: {', '.join(exported)}", echo=ctx.echo)


def for_role(role: str) -> Role:
    if role == "host":
        return HostRole()
    if role == "vm":
        return VmRole()
    raise ValueError(f"unknown role: {role!r}")
