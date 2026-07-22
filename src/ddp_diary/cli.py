"""Command-line entry point. Argparse only — dispatches to `runner.run_job()`
or the sync-only/doctor paths and holds no business logic itself (spec.md §6,
§9). This is deliberate: every future front-end (a test, an MCP server) can
call `runner.run_job` directly without going through this file at all.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import config as config_module
from . import doctor as doctor_module
from . import mount, runner
from .errors import ConfigError, DdpDiaryError, ShareUnavailableError, exit_code_for
from .models import Config


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)

    if args.command == "version":
        from . import __version__

        print(__version__)
        return 0

    try:
        cfg = config_module.load(Path(args.config), role_override=getattr(args, "role", None))
    except DdpDiaryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exit_code_for(exc)
    except Exception as exc:  # pragma: no cover - genuinely unexpected
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.command == "run":
            target_date = _parse_date(args.date) if args.date else None
            runner.run_job(
                cfg,
                args.job,
                target_date=target_date,
                dry_run=args.dry_run,
                no_push=args.no_push,
                verbose=args.verbose,
            )
            return 0

        if args.command == "backfill":
            _run_backfill(cfg, args)
            return 0

        if args.command == "sync":
            _run_sync(cfg, args)
            return 0

        if args.command == "doctor":
            return doctor_module.run(cfg, verbose=args.verbose)

    except DdpDiaryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exit_code_for(exc)
    except Exception as exc:
        # Never let an unexpected exception (e.g. a bug, or an OSError that
        # somehow escaped runner.py's own broad handler) leak a raw traceback
        # to what is normally an unattended cron/Task-Scheduler run — always a
        # clean message and exit code 1 (spec.md §9's "unexpected/unhandled").
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 1


def _run_backfill(cfg: Config, args: argparse.Namespace) -> None:
    """Reprocesses a `daily` date range. Weekly/monthly have no per-date
    identity to backfill against (spec.md §9) — only `daily` is meaningful here.
    """
    start = _parse_date(args.from_date)
    end = _parse_date(args.to_date)
    if start > end:
        raise ConfigError(f"--from ({start}) must not be after --to ({end})")

    current = start
    one_day = datetime.timedelta(days=1)
    while current <= end:
        runner.run_job(cfg, "daily", target_date=current, dry_run=args.dry_run)
        current += one_day


def _run_sync(cfg: Config, args: argparse.Namespace) -> None:
    from .sync import export as sync_export
    from .sync import ingest as sync_ingest

    if not mount.is_available(cfg.shared_dir):
        raise ShareUnavailableError(f"shared folder unavailable: {cfg.shared_dir}")

    if args.export_only:
        sync_export.run(cfg)
    elif args.ingest_only:
        sync_ingest.run(cfg)
    elif cfg.role == "host":
        sync_ingest.run(cfg)
    else:
        sync_export.run(cfg)


def _parse_date(value: str) -> datetime.date:
    return datetime.datetime.strptime(value, "%Y-%m-%d").date()


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ddp-diary")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run one period's synthesis")
    p_run.add_argument("--job", choices=["daily", "weekly", "monthly"], required=True)
    p_run.add_argument("--config", required=True)
    p_run.add_argument("--role", choices=["host", "vm"], default=None)
    p_run.add_argument("--date", default=None, help="override target date (YYYY-MM-DD)")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--no-push", action="store_true")
    p_run.add_argument("-v", "--verbose", action="store_true")

    p_backfill = sub.add_parser("backfill", help="reprocess a daily date range")
    p_backfill.add_argument("--config", required=True)
    p_backfill.add_argument("--role", choices=["host", "vm"], default=None)
    p_backfill.add_argument("--from", dest="from_date", required=True)
    p_backfill.add_argument("--to", dest="to_date", required=True)
    p_backfill.add_argument("--dry-run", action="store_true")

    p_sync = sub.add_parser("sync", help="run only the ingest/export stage")
    p_sync.add_argument("--config", required=True)
    p_sync.add_argument("--role", choices=["host", "vm"], default=None)
    group = p_sync.add_mutually_exclusive_group()
    group.add_argument("--export-only", action="store_true")
    group.add_argument("--ingest-only", action="store_true")

    p_doctor = sub.add_parser("doctor", help="environment/health check")
    p_doctor.add_argument("--config", required=True)
    p_doctor.add_argument("--role", choices=["host", "vm"], default=None)
    p_doctor.add_argument("-v", "--verbose", action="store_true")

    sub.add_parser("version", help="print the ddp-diary version")

    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
