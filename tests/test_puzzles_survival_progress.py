import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _guide_block(name: str, next_name: str) -> str:
    catalog = (ROOT / "site-guides.js").read_text(encoding="utf-8")
    return catalog.split(f'"{name}": {{', 1)[1].split(f'  "{next_name}": {{', 1)[0]


def test_puzzles_survival_progress_is_inside_guide():
    page = (ROOT / "puzzles-survival-guide.html").read_text(encoding="utf-8")
    assert 'href="#progress"' in page
    assert 'id="progress"' in page
    assert 'data-experience-src="data/guide-experiences/puzzles-survival.json"' in page
    assert 'assets/guide-experience.css' in page
    assert 'assets/guide-experience.js' in page


def test_puzzles_survival_progress_has_multiple_sourced_players():
    data = json.loads((ROOT / "data/guide-experiences/puzzles-survival.json").read_text(encoding="utf-8"))
    players = data["players"]
    assert len(players) >= 6
    assert all(player.get("sources") for player in players)
    assert any("CC17" in player.get("summary", "") and "7日" in player.get("summary", "") for player in players)
    assert any("CC22" in player.get("summary", "") for player in players)
    assert any(player.get("status") == "ongoing" for player in players)


def test_non_played_puzzles_guide_has_no_separate_progress_button():
    block = _guide_block("パズル＆サバイバル", "キングショット")
    assert 'href: "puzzles-survival-guide.html"' in block
    assert 'progress.html?game=パズル＆サバイバル' not in block


def test_tokyo_debunker_has_no_progress_button():
    block = _guide_block("東京ディバンカー", "パズル＆サバイバル")
    assert 'href: "tokyo-debunker-guide.html"' in block
    assert 'progress.html?game=東京ディバンカー' not in block
