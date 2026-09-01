from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_all_repository_writers_share_one_concurrency_group():
    trend = _workflow("discover-trending-games.yml")
    refresh = _workflow("refresh-verified-offers.yml")
    expected = "group: poigamelab-production-writer"
    assert expected in trend
    assert expected in refresh
    assert "cancel-in-progress: false" in trend
    assert "cancel-in-progress: false" in refresh


def test_no_legacy_split_writer_locks_remain():
    trend = _workflow("discover-trending-games.yml")
    refresh = _workflow("refresh-verified-offers.yml")
    combined = trend + "\n" + refresh
    assert "poigamelab-trend-discovery" not in combined
    assert "poigamelab-verified-refresh" not in combined


def test_only_two_workflows_write_repository_contents():
    workflows = ROOT / ".github" / "workflows"
    writers = []
    for path in workflows.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        if "contents: write" in text or "git push" in text:
            writers.append(path.name)
    assert sorted(writers) == ["discover-trending-games.yml", "refresh-verified-offers.yml"]
