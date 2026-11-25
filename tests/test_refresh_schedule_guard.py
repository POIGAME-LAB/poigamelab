"""Backup trigger for a dropped daily refresh (2026-11-24 JST: the scheduled run was never created)."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import refresh_schedule_guard as guard  # noqa: E402

NOW = datetime(2026, 11, 24, 1, 13, tzinfo=timezone.utc)  # 10:13 JST


def test_runs_only_when_nothing_ran_or_was_created_today():
    status = {"startedAt": "2026-11-22T21:53:06+00:00"}           # 11/23 JST
    runs = [{"createdAt": "2026-11-22T21:52:50Z", "status": "completed", "conclusion": "success"}]
    assert guard.decide(status, runs, NOW) == (True, "no_refresh_today")


def test_skips_when_today_was_already_refreshed():
    assert guard.decide({"startedAt": "2026-11-23T21:00:00+00:00"}, [], NOW)[0] is False   # 06:00 JST today


def test_skips_when_a_run_was_created_today_in_any_state():
    status = {"startedAt": "2026-11-22T21:53:06+00:00"}
    for state, conclusion in (("queued", None), ("in_progress", None), ("completed", "failure")):
        run, reason = guard.decide(status, [{"createdAt": "2026-11-23T20:00:00Z", "status": state, "conclusion": conclusion}], NOW)
        assert run is False and reason.startswith("refresh_run_exists_today"), reason


def test_fails_closed_without_a_run_list():
    assert guard.decide({"startedAt": "2026-11-22T21:53:06+00:00"}, None, NOW) == (False, "run_list_unavailable")
    assert guard.decide(None, None, NOW)[0] is False


def test_jst_day_boundary():
    # 2026-11-23 15:30Z is 11/24 00:30 JST -> counts as today
    assert guard.decide({"startedAt": "2026-11-23T15:30:00Z"}, [], NOW)[0] is False
    # 2026-11-23 14:59Z is 11/23 23:59 JST -> yesterday
    assert guard.decide({"startedAt": "2026-11-23T14:59:00Z"}, [], NOW)[0] is True


def test_cli_writes_github_output(tmp_path, monkeypatch):
    status = tmp_path / "s.json"
    status.write_text(json.dumps({"startedAt": "2000-01-01T00:00:00Z"}), encoding="utf-8")
    runs = tmp_path / "r.json"
    runs.write_text("null", encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert guard.main(["--status", str(status), "--runs", str(runs)]) == 0
    assert "run=false" in out.read_text(encoding="utf-8")


def test_backup_workflow_only_dispatches_and_never_writes():
    text = (ROOT / ".github/workflows/refresh-backup-trigger.yml").read_text(encoding="utf-8")
    assert "contents: read" in text and "contents: write" not in text and "git push" not in text
    assert "gh workflow run refresh-verified-offers.yml" in text
    # A GITHUB_TOKEN-started run does not fire workflow_run, so the deploy must be dispatched here,
    # and only after the refresh it started finished successfully.
    watch = text.index("gh run watch")
    assert "--exit-status" in text[watch:watch + 120]
    assert text.index("gh workflow run deploy-pages.yml") > watch
    assert "research-new-game-content" not in text  # no paid-API research on backup days
    assert "if: steps.guard.outputs.run == 'true'" in text
    assert "secrets." not in text and "API_KEY" not in text
    # downstream workflows listen only to the refresh workflow, never to this trigger
    for name in ("deploy-pages.yml", "research-new-game-content.yml"):
        assert "backup trigger" not in (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
