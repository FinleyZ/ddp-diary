"""Exception types mapped to process exit codes.

See spec.md §9 for the exit-code table this mirrors exactly. `errors_to_exit_code`
is the single place that turns a caught exception into the process's exit code, so
`cli.py` never has to guess.
"""

from __future__ import annotations


class DdpDiaryError(Exception):
    """Base for all ddp-diary errors. Exit code 1 (unexpected/unhandled)."""

    exit_code = 1


class ConfigError(DdpDiaryError):
    """Missing/invalid config key or path. Exit code 2."""

    exit_code = 2


class ClaudeInvocationError(DdpDiaryError):
    """`claude` exited nonzero, timed out, or produced unparseable output. Exit code 3."""

    exit_code = 3


class GitCommitError(DdpDiaryError):
    """`git add`/`git commit` failed unexpectedly. Exit code 4."""

    exit_code = 4


class GitPushError(DdpDiaryError):
    """`git push` failed; commits remain local, retried next run. Exit code 5."""

    exit_code = 5


class ShareUnavailableError(DdpDiaryError):
    """The shared folder was required (e.g. explicit `sync`) but unavailable. Exit code 6."""

    exit_code = 6


def exit_code_for(exc: BaseException) -> int:
    """Map any exception to a process exit code, defaulting unknown types to 1."""
    return getattr(exc, "exit_code", 1)
