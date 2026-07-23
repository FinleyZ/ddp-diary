"""Tests for claude_client.py: argv construction and JSON result parsing
(spec.md §6, §9, §12). `run()` is tested with a monkeypatched `subprocess.run`
— no real `claude` process is ever invoked."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ddp_diary import claude_client
from ddp_diary.errors import ClaudeInvocationError
from ddp_diary.models import ClaudeConfig, LimitsConfig


def _claude_cfg(**overrides) -> ClaudeConfig:
    base = dict(bin="claude", model="sonnet", output_format="json", allowed_tools=["Read", "Write"], add_dirs=[])
    base.update(overrides)
    return ClaudeConfig(**base)


def _limits(**overrides) -> LimitsConfig:
    base = dict(max_turns=0, max_budget_usd=0, timeout_sec=900, skim_max_files=5, skim_max_lines=200)
    base.update(overrides)
    return LimitsConfig(**base)


def test_build_argv_omits_unset_limits():
    argv = claude_client._build_argv(_claude_cfg(), _limits())
    assert "--max-turns" not in argv
    assert "--max-budget-usd" not in argv
    assert argv[0] == "claude"
    idx = argv.index("--allowedTools")
    assert argv[idx + 1] == "Read,Write"


def test_build_argv_includes_limits_when_set():
    argv = claude_client._build_argv(_claude_cfg(), _limits(max_turns=15, max_budget_usd=1.0))
    assert argv[argv.index("--max-turns") + 1] == "15"
    assert argv[argv.index("--max-budget-usd") + 1] == "1.0"


def test_build_argv_includes_one_add_dir_per_entry():
    argv = claude_client._build_argv(_claude_cfg(add_dirs=[Path("/a"), Path("/b")]), _limits())
    assert argv.count("--add-dir") == 2


def test_build_env_returns_none_when_no_config_dir():
    assert claude_client._build_env(_claude_cfg()) is None


def test_build_env_sets_claude_config_dir_when_pinned():
    env = claude_client._build_env(_claude_cfg(config_dir=Path("/home/u/.claude-personal")))
    assert env is not None
    assert env["CLAUDE_CONFIG_DIR"] == str(Path("/home/u/.claude-personal"))
    # inherits the rest of the parent environment (not a bare 1-key dict)
    assert len(env) > 1


def test_run_passes_claude_config_dir_env_to_subprocess(monkeypatch, tmp_path):
    captured = {}

    def fake_run(*args, **kwargs):
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(args, returncode=0, stdout='{"result": "ok"}\n', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    claude_client.run(
        "prompt",
        claude_cfg=_claude_cfg(config_dir=Path("/home/u/.claude-personal")),
        limits=_limits(),
        cwd=tmp_path,
    )

    assert captured["env"] is not None
    assert captured["env"]["CLAUDE_CONFIG_DIR"] == str(Path("/home/u/.claude-personal"))


def test_run_leaves_env_inherited_when_no_config_dir(monkeypatch, tmp_path):
    captured = {}

    def fake_run(*args, **kwargs):
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(args, returncode=0, stdout='{"result": "ok"}\n', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    claude_client.run("prompt", claude_cfg=_claude_cfg(), limits=_limits(), cwd=tmp_path)

    # env=None means "inherit the parent environment unchanged"
    assert captured["env"] is None


def test_extract_json_result_picks_last_matching_line():
    stdout = (
        "some log line\n"
        '{"result": "first"}\n'
        "more noise\n"
        '{"result": "second", "total_cost_usd": 0.01}\n'
    )
    parsed = claude_client._extract_json_result(stdout)
    assert parsed == {"result": "second", "total_cost_usd": 0.01}


def test_extract_json_result_returns_none_when_no_json_line():
    assert claude_client._extract_json_result("just text\nno json here\n") is None


def test_extract_json_result_returns_none_on_malformed_json():
    assert claude_client._extract_json_result('{"unterminated": ') is None


def test_run_raises_on_nonzero_exit(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ClaudeInvocationError):
        claude_client.run("prompt", claude_cfg=_claude_cfg(), limits=_limits(), cwd=tmp_path)


def test_run_raises_when_no_json_despite_zero_exit(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode=0, stdout="no json here", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ClaudeInvocationError):
        claude_client.run("prompt", claude_cfg=_claude_cfg(), limits=_limits(), cwd=tmp_path)


def test_run_returns_result_on_success(monkeypatch, tmp_path):
    payload = {"result": "wrote the entry", "total_cost_usd": 0.0234, "num_turns": 3, "duration_ms": 4500}

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode=0, stdout=json.dumps(payload) + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = claude_client.run("prompt", claude_cfg=_claude_cfg(), limits=_limits(), cwd=tmp_path)

    assert result.ok is True
    assert result.result_text == "wrote the entry"
    assert result.total_cost_usd == 0.0234
    assert result.num_turns == 3
    assert result.duration_ms == 4500


def test_run_raises_on_timeout(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ClaudeInvocationError, match="timed out"):
        claude_client.run("prompt", claude_cfg=_claude_cfg(), limits=_limits(timeout_sec=1), cwd=tmp_path)


def test_run_raises_when_is_error_true_despite_zero_exit(monkeypatch, tmp_path):
    """claude can exit 0 with a well-formed JSON result that still signals
    failure (e.g. hitting --max-turns/--max-budget-usd mid-task) — this must
    not be silently treated as success."""
    payload = {"result": "ran out of turns", "is_error": True, "subtype": "error_max_turns", "total_cost_usd": 0.99}

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode=0, stdout=json.dumps(payload) + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ClaudeInvocationError, match="error_max_turns"):
        claude_client.run("prompt", claude_cfg=_claude_cfg(), limits=_limits(), cwd=tmp_path)


def test_run_succeeds_when_is_error_false(monkeypatch, tmp_path):
    payload = {"result": "all good", "is_error": False, "total_cost_usd": 0.01}

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode=0, stdout=json.dumps(payload) + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = claude_client.run("prompt", claude_cfg=_claude_cfg(), limits=_limits(), cwd=tmp_path)
    assert result.ok is True
