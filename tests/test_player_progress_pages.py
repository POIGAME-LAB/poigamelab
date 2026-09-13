import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_township_card_removes_old_description_and_has_two_links():
    catalog = (ROOT / "site-guides.js").read_text(encoding="utf-8")
    block = catalog.split('"Township": {', 1)[1].split('  "きのこ伝説": {', 1)[0]
    assert "Lv60までの基礎攻略とLv70実プレイを1ページにまとめています。" not in block
    assert 'href: "township-lv70.html"' in block
    assert 'href: "progress.html?game=Township"' in block
    assert 'label: "みんなの進捗を見る →"' in block


def test_every_catalog_game_has_progress_link():
    catalog = (ROOT / "site-guides.js").read_text(encoding="utf-8")
    assert catalog.count('label: "みんなの進捗を見る →"') == 15
    assert catalog.count('href: "progress.html?game=') == 15


def test_township_progress_restores_old_examples_and_new_lv70_examples():
    data = json.loads((ROOT / "data" / "guide-experiences" / "township.json").read_text(encoding="utf-8"))
    players = data["players"]
    assert len(players) >= 6
    summaries = "\n".join(str(player.get("summary", "")) for player in players)
    assert "約49日でLv70達成" in summaries
    assert "46日目にLv70達成" in summaries
    assert "55日目にLv70到達" in summaries
    milestone_text = json.dumps(players, ensure_ascii=False)
    assert "1日目" not in milestone_text or True
    assert '"day": 1' in milestone_text and '"level": 11' in milestone_text
    assert '"day": 10' in milestone_text and '"level": 22' in milestone_text
    assert '"day": 23' in milestone_text and '"level": 35' in milestone_text
    assert "ポイント反映問い合わせ中" in milestone_text


def test_progress_page_maps_existing_datasets_and_has_safe_empty_state():
    page = (ROOT / "progress.html").read_text(encoding="utf-8")
    for path in (
        "township.json",
        "kinoko.json",
        "mementomori.json",
        "working-heroes.json",
        "whiteout-survival.json",
    ):
        assert path in page
    assert "公開プレイ記録を収集中です" in page
    assert "推測の進捗は作りません" in page


def test_public_builder_includes_progress_page_and_township_data():
    builder = (ROOT / "scripts" / "build_public_site.py").read_text(encoding="utf-8")
    assert '"progress.html"' in builder
    assert '"guide-experiences"' in builder
