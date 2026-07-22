"""Invoke `claude -p` and parse its JSON result.

The only module that shells out to `claude` — see spec.md §6, §9, §12. The prompt
is piped via stdin (never argv) to sidestep Windows command-length limits and
cross-shell quoting entirely (spec.md §8's stdin decision).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Optional

from .errors import ClaudeInvocationError
from .models import ClaudeConfig, LimitsConfig, RunResult

_JSON_LINE_RE = re.compile(r"^\s*\{")


def run(prompt_text: str, *, claude_cfg: ClaudeConfig, limits: LimitsConfig, cwd: Path) -> RunResult:
    """Run one `claude -p` invocation, cwd set to the data repo so any file writes
    Claude makes land there. Raises `ClaudeInvocationError` (exit code 3, spec.md
    §9) on a nonzero exit, a timeout, or output that doesn't parse as the
    expected JSON result object — the last case is a protocol violation given
    `--output-format json` and is not silently tolerated.
    """
    argv = _build_argv(claude_cfg, limits)

    try:
        proc = subprocess.run(
            argv,
            input=prompt_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(cwd),
            timeout=limits.timeout_sec if limits.timeout_sec > 0 else None,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClaudeInvocationError(f"claude timed out after {limits.timeout_sec}s") from exc
    except OSError as exc:
        raise ClaudeInvocationError(f"failed to launch claude ({claude_cfg.bin}): {exc}") from exc

    parsed = _extract_json_result(proc.stdout)

    if proc.returncode != 0:
        detail = (parsed or {}).get("result") or proc.stdout[-2000:] or proc.stderr[-2000:]
        raise ClaudeInvocationError(f"claude exited {proc.returncode}: {detail}")

    if parsed is None:
        raise ClaudeInvocationError(
            "claude exited 0 but produced no parseable JSON result "
            f"(--output-format={claude_cfg.output_format}); stdout tail: {proc.stdout[-2000:]}"
        )

    if parsed.get("is_error"):
        # claude can exit 0 with a well-formed JSON result that still signals
        # failure (e.g. hitting --max-turns/--max-budget-usd mid-task): the
        # `subtype` names why. Treat this exactly like a nonzero exit — never
        # silently commit/push whatever partial content a truncated run wrote.
        subtype = parsed.get("subtype", "unknown")
        raise ClaudeInvocationError(
            f"claude reported is_error=true (subtype={subtype}): {str(parsed.get('result', ''))[:2000]}"
        )

    return RunResult(
        ok=True,
        result_text=str(parsed.get("result", "")),
        total_cost_usd=parsed.get("total_cost_usd"),
        num_turns=parsed.get("num_turns"),
        duration_ms=parsed.get("duration_ms"),
        raw_stdout=proc.stdout,
        raw_stderr=proc.stderr,
        exit_code=proc.returncode,
    )


def _build_argv(claude_cfg: ClaudeConfig, limits: LimitsConfig) -> list[str]:
    argv = [
        claude_cfg.bin,
        "-p",
        "--model", claude_cfg.model,
        "--output-format", claude_cfg.output_format,
        "--allowedTools", ",".join(claude_cfg.allowed_tools),
    ]
    for add_dir in claude_cfg.add_dirs:
        argv += ["--add-dir", str(add_dir)]
    if limits.max_turns > 0:
        argv += ["--max-turns", str(limits.max_turns)]
    if limits.max_budget_usd > 0:
        argv += ["--max-budget-usd", str(limits.max_budget_usd)]
    return argv


def _extract_json_result(stdout: str) -> Optional[dict]:
    """The last line matching a JSON object is the result — mirrors the original
    PowerShell parser (`Where-Object {$_ -match '^\\s*\\{'} | Select-Object -Last 1`)."""
    candidate = None
    for line in stdout.splitlines():
        if _JSON_LINE_RE.match(line):
            candidate = line
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None
