import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_magic_jigsaw_guide_has_full_structure_and_inline_progress():
    page = (ROOT / "magic-jigsaw-puzzles-guide.html").read_text(encoding="utf-8")
    assert '<div class="eyebrow">POIGAME LAB 攻略データ</div>' in page
    assert page.count('class="stat"') == 3
    for anchor in ("condition", "progress", "route", "coins", "puzzle", "ads", "missions", "daily", "tracking", "target", "summary"):
        assert f'href="#{anchor}"' in page
    assert 'data-experience-src="data/guide-experiences/magic-jigsaw-puzzles.json"' in page
    assert 'src="assets/guide-experience.js"' in page
    assert 'href="assets/guide-experience.css"' in page
    assert "35〜70ピース" in page
    assert "エキストラボーナス" in page
    assert "X（Twitter）・Instagram・Web検索・YouTube" in page


def test_magic_jigsaw_progress_has_sourced_real_pace_examples():
    data = json.loads((ROOT / "data" / "guide-experiences" / "magic-jigsaw-puzzles.json").read_text(encoding="utf-8"))
    assert data["game"] == "マジックジグソーパズル"
    players = data["players"]
    assert len(players) >= 4
    assert all(player.get("status") == "completed" for player in players)
    text = json.dumps(players, ensure_ascii=False)
    assert "7,000コイン" in text and "9日" in text and "12時間20分" in text
    assert "3,500コイン" in text and "約3時間" in text
    assert "11,000コイン" in text and "約4日" in text
    assert "7日" in text and "約11時間" in text
    for player in players:
        assert player.get("sources")
        assert all(str(url).startswith("https://") for url in player["sources"])


def test_magic_jigsaw_catalog_has_only_guide_link_and_no_progress_button():
    catalog = (ROOT / "site-guides.js").read_text(encoding="utf-8")
    block = catalog.split('"マジックジグソーパズル": {', 1)[1].split('\n  }\n});', 1)[0]
    assert 'href: "magic-jigsaw-puzzles-guide.html"' in block
    assert "progress.html?game=マジックジグソーパズル" not in block
    assert "みんなの進捗を見る" not in block


def test_magic_jigsaw_catalog_pace_is_researched_not_placeholder():
    with (ROOT / "games.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["name"]: row for row in csv.DictReader(handle)}
    game = rows["マジックジグソーパズル"]
    assert "7,000コイン実例9日" in game["days"]
    assert "11,000コイン実例4〜7日" in game["days"]
    assert "15,000コイン期限22日" in game["days"]
    assert "広告視聴時間が必要" in game["difficulty"]
    assert "調査中" not in game["difficulty"]
