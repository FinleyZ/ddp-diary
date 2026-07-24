"""Integration tests for runner.py: the full orchestration spine (spec.md §4,
§5, §12). `claude_client.run` is monkeypatched so no real `claude` process is
invoked — these tests prove extraction -> prompt assembly -> (mocked) claude
-> commit -> role export -> cost log all wire together correctly.
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
from pathlib import Path

import pytest

from ddp_diary import claude_client, gitops, runner
from ddp_diary.errors import ClaudeInvocationError, ConfigError
from ddp_diary.errors import GitPushError
from ddp_diary.models import RunResult


def _write_activity(claude_projects_dir: Path, name: str, date_obj: datetime.date) -> None:
    """Write one fake session message at local noon on `date_obj`, converted
    to UTC for the file (matching real transcript format) — round-tripping
    through the same .astimezone() conversion session_extract.py uses, so
    this lands on exactly `date_obj` regardless of the test machine's
    timezone (no fixed-UTC-noon edge case near the international date line)."""
    local_noon = datetime.datetime.combine(date_obj, datetime.time(12, 0)).astimezone()
    iso_utc = local_noon.astimezone(datetime.timezone.utc).isoformat()
    content = json.dumps({"type": "user", "timestamp": iso_utc, "message": {"content": [{"type": "text", "text": "did stuff"}]}})
    proj_dir = claude_projects_dir / "proj1"
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / f"{name}.jsonl").write_text(content + "\n", encoding="utf-8")


def _fake_claude_writer(prompt_text, *, claude_cfg, limits, cwd):
    """A generic fake claude_client.run: writes daily/<target-date>.md for
    whatever date the prompt's Context block says, by parsing it out — reused
    across backfill tests instead of hand-wiring one date per test."""
    m = re.search(r"Target date: (\d{4}-\d{2}-\d{2})", prompt_text)
    date_str = m.group(1)
    (cwd / "daily" / f"{date_str}.md").write_text(f"# {date_str}\n\n## Did\n- backfilled\n", encoding="utf-8")
    return RunResult(ok=True, result_text="ok", total_cost_usd=0.01, num_turns=1, duration_ms=10, raw_stdout="", raw_stderr="", exit_code=0)


def _fake_claude_writer_failing_on(fail_date_str: str):
    def _fake(prompt_text, *, claude_cfg, limits, cwd):
        m = re.search(r"Target date: (\d{4}-\d{2}-\d{2})", prompt_text)
        date_str = m.group(1)
        if date_str == fail_date_str:
            raise ClaudeInvocationError(f"simulated failure for {date_str}")
        (cwd / "daily" / f"{date_str}.md").write_text(f"# {date_str}\n\n## Did\n- backfilled\n", encoding="utf-8")
        return RunResult(ok=True, result_text="ok", total_cost_usd=0.01, num_turns=1, duration_ms=10, raw_stdout="", raw_stderr="", exit_code=0)
    return _fake


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


# --- backfill_missing_days / run_daily_with_backfill (spec.md §11) ---------

BEFORE = datetime.date(2026, 7, 20)


def test_backfill_missing_days_skips_dates_with_existing_entries(
    monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config
):
    d_minus_1 = BEFORE - datetime.timedelta(days=1)
    d_minus_2 = BEFORE - datetime.timedelta(days=2)
    _write_activity(claude_projects_dir, "s1", d_minus_1)
    _write_activity(claude_projects_dir, "s2", d_minus_2)
    (data_repo / "daily" / f"{d_minus_2.isoformat()}.md").write_text("# already here\n", encoding="utf-8")

    monkeypatch.setattr(claude_client, "run", _fake_claude_writer)
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir, backfill_days=7)

    filled = runner.backfill_missing_days(cfg, before_date=BEFORE)

    assert filled == [d_minus_1]
    assert (data_repo / "daily" / f"{d_minus_2.isoformat()}.md").read_text(encoding="utf-8") == "# already here\n"


def test_backfill_missing_days_processes_oldest_first(
    monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config
):
    d_minus_1 = BEFORE - datetime.timedelta(days=1)
    d_minus_3 = BEFORE - datetime.timedelta(days=3)
    _write_activity(claude_projects_dir, "s1", d_minus_1)
    _write_activity(claude_projects_dir, "s2", d_minus_3)

    monkeypatch.setattr(claude_client, "run", _fake_claude_writer)
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir, backfill_days=7)

    filled = runner.backfill_missing_days(cfg, before_date=BEFORE)

    assert filled == [d_minus_3, d_minus_1]


def test_backfill_missing_days_is_best_effort_and_continues_past_a_failing_date(
    monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config
):
    d_minus_1 = BEFORE - datetime.timedelta(days=1)
    d_minus_2 = BEFORE - datetime.timedelta(days=2)  # older -> processed first -> will fail
    _write_activity(claude_projects_dir, "s1", d_minus_1)
    _write_activity(claude_projects_dir, "s2", d_minus_2)

    monkeypatch.setattr(claude_client, "run", _fake_claude_writer_failing_on(d_minus_2.isoformat()))
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir, backfill_days=7)

    filled = runner.backfill_missing_days(cfg, before_date=BEFORE)  # must not raise

    assert filled == [d_minus_1]  # d_minus_2 failed and was skipped, d_minus_1 still got processed


def test_backfill_missing_days_excludes_before_date_itself(
    monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config
):
    _write_activity(claude_projects_dir, "s1", BEFORE)  # activity ON before_date itself

    monkeypatch.setattr(claude_client, "run", _fake_claude_writer)
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir, backfill_days=7)

    filled = runner.backfill_missing_days(cfg, before_date=BEFORE)

    assert filled == []


def test_backfill_missing_days_respects_backfill_days_window(
    monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config
):
    too_old = BEFORE - datetime.timedelta(days=5)
    _write_activity(claude_projects_dir, "s1", too_old)

    monkeypatch.setattr(claude_client, "run", _fake_claude_writer)
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir, backfill_days=3)

    filled = runner.backfill_missing_days(cfg, before_date=BEFORE)

    assert filled == []  # outside the 3-day window


def test_backfill_missing_days_caps_at_backfill_max_per_run(
    monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config
):
    dates = [BEFORE - datetime.timedelta(days=n) for n in range(1, 6)]  # 5 missing dates
    for i, d in enumerate(dates):
        _write_activity(claude_projects_dir, f"s{i}", d)

    monkeypatch.setattr(claude_client, "run", _fake_claude_writer)
    cfg = make_config(
        role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir,
        claude_projects=claude_projects_dir, backfill_days=7, backfill_max_per_run=2,
    )

    filled = runner.backfill_missing_days(cfg, before_date=BEFORE)

    assert len(filled) == 2
    assert filled == sorted(dates)[:2]  # the 2 oldest


def test_backfill_missing_days_dry_run_does_not_commit(
    monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config
):
    d_minus_1 = BEFORE - datetime.timedelta(days=1)
    _write_activity(claude_projects_dir, "s1", d_minus_1)

    monkeypatch.setattr(claude_client, "run", _fake_claude_writer)
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir, backfill_days=7)

    before_log = subprocess.run(["git", "log", "--oneline"], cwd=str(data_repo), capture_output=True, text=True).stdout

    runner.backfill_missing_days(cfg, before_date=BEFORE, dry_run=True)

    after_log = subprocess.run(["git", "log", "--oneline"], cwd=str(data_repo), capture_output=True, text=True).stdout
    assert before_log == after_log  # no new commit


def test_run_daily_with_backfill_calls_backfill_then_todays_run_job(
    monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config
):
    d_minus_1 = datetime.date.today() - datetime.timedelta(days=1)
    _write_activity(claude_projects_dir, "s1", d_minus_1)
    _write_activity(claude_projects_dir, "s2", datetime.date.today())

    monkeypatch.setattr(claude_client, "run", _fake_claude_writer)
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir, backfill_days=7)

    ctx = runner.run_daily_with_backfill(cfg)

    assert (data_repo / "daily" / f"{d_minus_1.isoformat()}.md").exists()  # backfilled
    assert (data_repo / "daily" / f"{datetime.date.today().isoformat()}.md").exists()  # today
    assert ctx.target_date == datetime.date.today()


def test_run_daily_with_backfill_noop_when_backfill_days_is_zero(
    monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config
):
    """The critical regression guard: default config (backfill_days=0) must
    behave EXACTLY like a single plain run_job call — proves today's already-
    live setup is unaffected by this feature existing."""
    d_minus_1 = datetime.date.today() - datetime.timedelta(days=1)
    _write_activity(claude_projects_dir, "s1", d_minus_1)  # activity exists, but must be ignored

    monkeypatch.setattr(claude_client, "run", _fake_claude_writer)
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir, backfill_days=0)

    runner.run_daily_with_backfill(cfg)

    assert not (data_repo / "daily" / f"{d_minus_1.isoformat()}.md").exists()  # NOT backfilled
    assert (data_repo / "daily" / f"{datetime.date.today().isoformat()}.md").exists()  # today still ran

    log = subprocess.run(["git", "log", "--oneline"], cwd=str(data_repo), capture_output=True, text=True).stdout
    assert log.count("\n") == 2  # the fixture's "init" + exactly one new commit (today's)


def test_run_daily_with_backfill_returns_todays_run_context(
    monkeypatch, data_repo, shared_dir, scratch_dir, claude_projects_dir, make_config
):
    monkeypatch.setattr(claude_client, "run", _fake_claude_writer)
    cfg = make_config(role="vm", data_dir=data_repo, shared_dir=shared_dir, scratch_dir=scratch_dir, claude_projects=claude_projects_dir, backfill_days=0)

    ctx = runner.run_daily_with_backfill(cfg)

    assert ctx.job == "daily"
    assert ctx.target_date == datetime.date.today()
    assert ctx.committed is True
