from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_new_game_monitor_is_noindex_and_candidate_only():
    page = (ROOT / "new-game-status.html").read_text(encoding="utf-8")
    assert '<meta name="robots" content="noindex,nofollow">' in page
    assert "data/new_game_candidate_queue.json" in page
    assert "data/new_game_candidate_history.json" in page
    assert "ここに表示される候補は未確認です" in page
    assert "案件公開" in page
    assert "最高還元" in page


def test_new_game_monitor_shows_new_continuing_priority_and_inactive():
    page = (ROOT / "new-game-status.html").read_text(encoding="utf-8")
    for marker in ("今日のNEW", "優先レビュー", "継続掲載", "消えた候補"):
        assert marker in page
    assert "isNewToday===true" in page
    assert "reviewPriority==='high'" in page
    assert "active===false" in page


def test_monitor_escapes_dynamic_candidate_text():
    page = (ROOT / "new-game-status.html").read_text(encoding="utf-8")
    assert "POIGAME_DATA.escapeHtml" in page
    assert "esc(x.titleHint" in page
    assert "esc(x.source" in page


def test_monitor_revalidates_candidate_urls_before_rendering_links():
    page = (ROOT / "new-game-status.html").read_text(encoding="utf-8")
    assert "POIGAME_DATA.safeHttpUrl" in page
    assert "safeCandidateUrl" in page
