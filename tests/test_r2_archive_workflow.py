from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "refresh-verified-offers.yml"


def workflow_text():
    return WORKFLOW.read_text(encoding="utf-8")


def test_r2_archive_uses_repository_secrets_and_scoped_bucket():
    text = workflow_text()
    for secret in (
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_ENDPOINT",
        "R2_BUCKET",
    ):
        assert f"secrets.{secret}" in text
    assert "poigamelab-data" not in text
    assert "AWS_ACCESS_KEY_ID" in text
    assert "AWS_SECRET_ACCESS_KEY" in text


def test_r2_state_is_restored_before_refresh():
    text = workflow_text()
    restore = text.index("- name: Restore high-growth refresh state from Cloudflare R2")
    refresh = text.index("- name: Check first-party comparison pages")
    assert restore < refresh
    block = text[restore:refresh]
    assert 's3://${R2_BUCKET}/state/latest/' in block
    assert 'gzip -dc "${restore_dir}/${name}.gz"' in block
    for name in (
        "new_game_candidate_queue.json",
        "new_game_candidate_history.json",
        "existing_game_candidate_queue.json",
        "comparison_candidate_queue.json",
        "comparison_review_queue.json",
        "comparison_refresh_status.json",
    ):
        assert name in block


def test_r2_archive_runs_only_after_success_and_before_git_commit():
    text = workflow_text()
    archive = text.index("- name: Archive refresh outputs to Cloudflare R2")
    commit = text.index("- name: Commit compact public outputs only")
    assert archive < commit
    archive_block = text[archive:commit]
    assert "if: steps.refresh.outcome == 'success'" in archive_block
    assert "set -euo pipefail" in archive_block
    assert 'test "${archived}" -gt 0' in archive_block


def test_r2_archive_compresses_and_checksums_high_growth_outputs():
    text = workflow_text()
    required = (
        "data/new_game_candidate_queue.json",
        "data/new_game_candidate_history.json",
        "data/existing_game_candidate_queue.json",
        "data/comparison_candidate_queue.json",
        "data/comparison_review_queue.json",
        "data/comparison_refresh_status.json",
        "data/published_offers.csv",
        "data/offer_history.csv",
    )
    for path in required:
        assert path in text
    assert 'gzip -9 -c "${path}"' in text
    assert "sha256sum *.gz > SHA256SUMS" in text


def test_r2_archive_writes_dated_and_latest_prefixes():
    text = workflow_text()
    assert "date -u +'%Y/%m/%d/%H%M%SZ'" in text
    assert 's3://${R2_BUCKET}/daily/${stamp}/' in text
    assert 's3://${R2_BUCKET}/state/latest/' in text
    assert '--endpoint-url "${R2_ENDPOINT}"' in text
    assert "--only-show-errors" in text


def test_compact_monitors_are_built_before_archive_and_committed():
    text = workflow_text()
    build = text.index("- name: Build compact public monitor snapshots")
    archive = text.index("- name: Archive refresh outputs to Cloudflare R2")
    commit = text.index("- name: Commit compact public outputs only")
    assert build < archive < commit
    assert "python scripts/write_public_monitors.py" in text[build:archive]
    commit_block = text[commit:]
    assert "git add data/new_game_monitor.json data/existing_game_monitor.json" in commit_block


def test_high_growth_files_are_not_committed_to_git():
    text = workflow_text()
    commit = text.index("- name: Commit compact public outputs only")
    failure = text.index("- name: Surface direct-refresh system failure")
    block = text[commit:failure]
    assert "git add data/published_offers.csv" in block
    assert "git add data/offer_history.csv" in block
    for path in (
        "data/new_game_candidate_queue.json",
        "data/new_game_candidate_history.json",
        "data/existing_game_candidate_queue.json",
        "data/comparison_candidate_queue.json",
        "data/comparison_review_queue.json",
        "data/comparison_refresh_status.json",
    ):
        assert f"git add {path}" not in block
        assert path in block
    assert "git restore --worktree" in block


def test_existing_daily_schedule_and_concurrency_are_unchanged():
    text = workflow_text()
    assert 'cron: "17 16 * * *"' in text
    assert text.count('cron: "17 16 * * *"') == 1
    assert "group: poigamelab-production-writer" in text
    assert "cancel-in-progress: false" in text
