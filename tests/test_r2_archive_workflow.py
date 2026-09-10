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


def test_r2_archive_runs_only_after_success_and_before_git_commit():
    text = workflow_text()
    archive = text.index("- name: Archive refresh outputs to Cloudflare R2")
    commit = text.index("- name: Commit safe direct-refresh outputs")
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


def test_r2_archive_uses_dated_prefix_and_endpoint():
    text = workflow_text()
    assert "date -u +'%Y/%m/%d/%H%M%SZ'" in text
    assert 's3://${R2_BUCKET}/daily/${stamp}/' in text
    assert '--endpoint-url "${R2_ENDPOINT}"' in text
    assert "--only-show-errors" in text


def test_existing_daily_schedule_and_concurrency_are_unchanged():
    text = workflow_text()
    assert 'cron: "17 16 * * *"' in text
    assert text.count('cron: "17 16 * * *"') == 1
    assert "group: poigamelab-production-writer" in text
    assert "cancel-in-progress: false" in text
