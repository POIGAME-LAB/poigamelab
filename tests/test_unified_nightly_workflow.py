import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "refresh-verified-offers.yml"


def workflow_text():
    return WORKFLOW.read_text(encoding="utf-8")


def test_nightly_pipeline_builds_unified_snapshot_from_the_single_daily_scan():
    text = workflow_text()
    scan = "run: python scripts/daily_scan_review.py"
    snapshot = "run: python scripts/unified_offer_snapshot.py"

    assert text.count(scan) == 1
    assert text.count(snapshot) == 1
    assert text.index(scan) < text.index(snapshot)

    snapshot_start = text.index("- name: Build unified eight-site offer snapshot")
    next_step = text.index("- name: Write top-five content research handoff queue")
    snapshot_block = text[snapshot_start:next_step]
    assert "if: steps.refresh.outcome == 'success'" in snapshot_block
    assert snapshot in snapshot_block


def test_unified_snapshot_is_archived_to_r2_but_not_committed_to_git():
    text = workflow_text()
    archive = text.index("- name: Archive refresh outputs to Cloudflare R2")
    commit = text.index("- name: Commit compact public outputs only")
    failure = text.index("- name: Surface direct-refresh system failure")

    archive_block = text[archive:commit]
    commit_block = text[commit:failure]
    path = "data/unified_offer_snapshot.json"

    assert path in archive_block
    assert f"git add {path}" not in commit_block
    assert path in commit_block


def test_nightly_schedule_and_main_only_guard_remain_unchanged():
    text = workflow_text()
    assert text.count('cron: "17 16 * * *"') == 1
    assert "if: github.ref == 'refs/heads/main'" in text
    assert "group: poigamelab-production-writer" in text
    assert "cancel-in-progress: false" in text


def test_enabled_discovery_sources_match_exact_unified_eight_site_contract():
    policy = json.loads((ROOT / "config" / "refresh_policy.json").read_text(encoding="utf-8"))
    source_cfg = json.loads((ROOT / "config" / "point_sources.json").read_text(encoding="utf-8"))

    unified = [str(value) for value in policy["unifiedDailySources"]]
    enabled = [
        str(source["id"])
        for source in source_cfg["sources"]
        if source.get("new_game_discovery_enabled") is True
    ]

    assert len(unified) == 8
    assert len(set(unified)) == 8
    assert set(enabled) == set(unified)


def test_scheduled_comparison_sources_are_the_same_unified_eight_sources():
    policy = json.loads((ROOT / "config" / "refresh_policy.json").read_text(encoding="utf-8"))

    comparison = [str(value) for value in policy["comparisonSources"]]
    unified = [str(value) for value in policy["unifiedDailySources"]]

    assert comparison == unified
