"""Integration tests for runner.py: the full orchestration spine (spec.md §4,
§5, §12). `claude_client.run` is monkeypatched so no real `claude` process is
invoked — these tests prove extraction -> prompt assembly -> (mocked) claude
-> commit -> role export -> cost log all wire together correctly.
"""

from __future__ import annotations

import datetime
import subprocess

import pytest

from ddp_diary import claude_client, gitops, runner
from ddp_diary.errors import ClaudeInvocationError, ConfigError
from ddp_diary.errors import GitPushError
from ddp_diary.models import RunResult


def test_dry_run_does_not_commit_or_touch_share(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    ctx = runner.run_job(cfg, "daily", target_date=datetime.date(2026, 7, 20), dry_run=True)

    assert ctx.committed is False
    assert ctx.pushed is False
    log = subprocess.run(["git", "log", "--oneline"], cwd=str(data_repo), capture_output=True, text=True).stdout
    assert log.count("\n") == 1  # only the fixture's initial "init" commit


def test_success_path_commits_and_exports_and_logs_cost(monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    def fake_claude_run(prompt_text, *, claude_cfg, limits, cwd):
        # Simulate Claude writing the entry, as it would via its own Write tool call.
        (cwd / "daily" / "2026-07-20.md").write_text("# entry\n\n## Did\n- did the thing\n", encoding="utf-8")
        return RunResult(
            ok=True, result_text="wrote it", total_cost_usd=0.01, num_turns=2,
            duration_ms=1200, raw_stdout="", raw_stderr="", exit_code=0,
        )

    monkeypatch.setattr(claude_client, "run", fake_claude_run)

    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir, push=False)

    ctx = runner.run_job(cfg, "daily", target_date=datetime.date(2026, 7, 20))

    assert ctx.committed is True
    assert (shared_dir / "vm-daily-2026-07-20.md").exists()  # VmRole.after_commit exported it

    cost_log = (scratch_dir / "ddp-diary.cost.jsonl").read_text(encoding="utf-8")
    assert '"total_cost_usd": 0.01' in cost_log


def test_failure_path_still_attempts_push_but_reraises_original_error(
    monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config
):
    def fake_claude_run(*args, **kwargs):
        raise ClaudeInvocationError("boom")

    monkeypatch.setattr(claude_client, "run", fake_claude_run)

    cfg = make_config(
        role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir,
        claude_projects=claude_projects_dir, push=True, push_even_on_failure=True,
    )

    with pytest.raises(ClaudeInvocationError):
        runner.run_job(cfg, "daily", target_date=datetime.date(2026, 7, 20))

    log_text = (scratch_dir / "ddp-diary.log").read_text(encoding="utf-8")
    assert "FAILED daily: boom" in log_text
    # push was attempted (and failed, no remote) rather than skipped outright
    assert "FAILED push" in log_text


def test_push_is_attempted_only_once_even_when_the_push_itself_is_the_failure(
    monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config
):
    """If synthesis SUCCEEDS but push fails (no remote), the failure handler's
    best-effort retry must not attempt push a second time — git push isn't
    guaranteed side-effect-idempotent (e.g. a webhook on the remote)."""

    def fake_claude_run(prompt_text, *, claude_cfg, limits, cwd):
        (cwd / "daily" / "2026-07-20.md").write_text("# entry\n", encoding="utf-8")
        return RunResult(ok=True, result_text="ok", total_cost_usd=0.01, num_turns=1, duration_ms=100, raw_stdout="", raw_stderr="", exit_code=0)

    monkeypatch.setattr(claude_client, "run", fake_claude_run)

    push_calls = []
    real_push = gitops.push

    def counting_push(data_dir, git_cfg):
        push_calls.append(1)
        return real_push(data_dir, git_cfg)

    monkeypatch.setattr(gitops, "push", counting_push)

    cfg = make_config(
        role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir,
        claude_projects=claude_projects_dir, push=True, push_even_on_failure=True,
    )

    with pytest.raises(GitPushError):
        runner.run_job(cfg, "daily", target_date=datetime.date(2026, 7, 20))

    assert len(push_calls) == 1  # not 2


def test_vm_role_rejects_weekly_and_monthly_jobs(data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    with pytest.raises(ConfigError, match="vm role does not run"):
        runner.run_job(cfg, "weekly", target_date=datetime.date(2026, 7, 20))
    with pytest.raises(ConfigError, match="vm role does not run"):
        runner.run_job(cfg, "monthly", target_date=datetime.date(2026, 7, 20))


def test_vm_export_then_host_ingest_end_to_end(monkeypatch, tmp_path, shared_dir, make_config):
    """Closes the gap: a real VM run_job (mocked claude) exports a fresh daily
    entry to the share, and a subsequent real HOST run_job (mocked claude)
    ingests and folds it — proving the full VM->share->host chain wires
    together, not just its two halves in isolation."""
    import subprocess as sp

    vm_data = tmp_path / "vm-data"
    (vm_data / "daily").mkdir(parents=True)
    sp.run(["git", "init", "-q"], cwd=str(vm_data), check=True)
    sp.run(["git", "config", "user.email", "t@t.local"], cwd=str(vm_data), check=True)
    sp.run(["git", "config", "user.name", "t"], cwd=str(vm_data), check=True)
    (vm_data / ".gitkeep").write_text("", encoding="utf-8")
    sp.run(["git", "add", "-A"], cwd=str(vm_data), check=True)
    sp.run(["git", "commit", "-q", "-m", "init"], cwd=str(vm_data), check=True)

    host_data = tmp_path / "host-data"
    for d in ("daily", "weekly", "monthly", "inbox"):
        (host_data / d).mkdir(parents=True)
    sp.run(["git", "init", "-q"], cwd=str(host_data), check=True)
    sp.run(["git", "config", "user.email", "t@t.local"], cwd=str(host_data), check=True)
    sp.run(["git", "config", "user.name", "t"], cwd=str(host_data), check=True)
    (host_data / ".gitkeep").write_text("", encoding="utf-8")
    sp.run(["git", "add", "-A"], cwd=str(host_data), check=True)
    sp.run(["git", "commit", "-q", "-m", "init"], cwd=str(host_data), check=True)

    vm_scratch = tmp_path / "vm-state"
    host_scratch = tmp_path / "host-state"
    vm_scratch.mkdir()
    host_scratch.mkdir()
    claude_projects = tmp_path / "claude-projects"
    claude_projects.mkdir()

    def fake_claude_run_vm(prompt_text, *, claude_cfg, limits, cwd):
        (cwd / "daily" / "2026-07-20.md").write_text("# 2026-07-20\n\n## Did\n- firmware work\n", encoding="utf-8")
        return RunResult(ok=True, result_text="ok", total_cost_usd=0.01, num_turns=1, duration_ms=100, raw_stdout="", raw_stderr="", exit_code=0)

    monkeypatch.setattr(claude_client, "run", fake_claude_run_vm)
    vm_cfg = make_config(role="vm", data_dir=vm_data, shared_dir=shared_dir, scratch_dir=vm_scratch, claude_projects=claude_projects)
    runner.run_job(vm_cfg, "daily", target_date=datetime.date(2026, 7, 20))

    assert (shared_dir / "vm-daily-2026-07-20.md").exists()

    def fake_claude_run_host(prompt_text, *, claude_cfg, limits, cwd):
        assert "firmware work" in (cwd / "inbox" / "vm-daily-2026-07-20.md").read_text(encoding="utf-8")
        (cwd / "daily" / "2026-07-20.md").write_text("# 2026-07-20\n\n## Did\n- folded firmware work\n", encoding="utf-8")
        return RunResult(ok=True, result_text="ok", total_cost_usd=0.02, num_turns=1, duration_ms=100, raw_stdout="", raw_stderr="", exit_code=0)

    monkeypatch.setattr(claude_client, "run", fake_claude_run_host)
    host_cfg = make_config(role="host", data_dir=host_data, shared_dir=shared_dir, scratch_dir=host_scratch, claude_projects=claude_projects)
    runner.run_job(host_cfg, "daily", target_date=datetime.date(2026, 7, 20))

    assert (host_data / "daily" / "2026-07-20.md").read_text(encoding="utf-8") == "# 2026-07-20\n\n## Did\n- folded firmware work\n"
    assert not (shared_dir / "vm-daily-2026-07-20.md").exists()  # ingested (moved), not left behind


def test_verbose_echoes_to_stdout(capsys, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    runner.run_job(cfg, "daily", target_date=datetime.date(2026, 7, 20), dry_run=True, verbose=True)

    captured = capsys.readouterr()
    assert "daily started" in captured.out


def test_non_verbose_is_silent_on_stdout(capsys, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config):
    cfg = make_config(role="host", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir)

    runner.run_job(cfg, "daily", target_date=datetime.date(2026, 7, 20), dry_run=True, verbose=False)

    captured = capsys.readouterr()
    assert captured.out == ""
