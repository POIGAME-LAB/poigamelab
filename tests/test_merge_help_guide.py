import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_merge_help_progress_has_sourced_real_player_pace():
    data = json.loads((ROOT / "data" / "guide-experiences" / "merge-help.json").read_text(encoding="utf-8"))
    assert data["game"] == "Merge Help: ホームデザインパズル"
    players = data["players"]
    assert len(players) >= 3
    assert any(player.get("status") == "completed" for player in players)
    text = json.dumps(players, ensure_ascii=False)
    assert "22日でLv28" in text
    assert "Lv20" in text and '"day": 11' in text
    assert "1日目Lv7" in text or ('"day": 1' in text and '"label": "Lv7"' in text)
    assert "4日でLv10" in text
    assert "1日1レベル" in text
    assert "ameblo.jp/pointo-sora" in text
    assert "miyunoma.com" in text
    assert "warau.jp" in text
    for player in players:
        assert player.get("sources")
        assert all(str(url).startswith("https://") for url in player["sources"])


def test_merge_help_guide_matches_full_structure_and_strategy():
    page = (ROOT / "merge-help-guide.html").read_text(encoding="utf-8")
    assert '<div class="eyebrow">POIGAME LAB 攻略データ</div>' in page
    assert page.count('class="stat"') == 3
    for anchor in ("condition", "progress", "route", "xp", "board", "generator", "energy", "ads", "diamond", "daily", "target", "summary"):
        assert f'href="#{anchor}"' in page
    assert 'data-experience-src="data/guide-experiences/merge-help.json"' in page
    assert 'src="assets/guide-experience.js"' in page
    assert 'href="assets/guide-experience.css"' in page
    assert "四季盛" in page
    assert "2分で1回復" in page
    assert "XP+15" in page
    assert "22日" in page and "Lv28" in page
    assert "X（Twitter）" in page
    assert "具体的な到達日数とレベル" in page


def test_merge_help_has_no_separate_progress_button():
    catalog = (ROOT / "site-guides.js").read_text(encoding="utf-8")
    block = catalog.split('"Merge Help: ホームデザインパズル": {', 1)[1].split('  "マジックジグソーパズル": {', 1)[0]
    assert 'href: "merge-help-guide.html"' in block
    assert "progress.html?game=Merge" not in block
    assert "みんなの進捗を見る" not in block
