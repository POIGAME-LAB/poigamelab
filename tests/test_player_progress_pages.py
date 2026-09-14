import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _guide_block(catalog: str, name: str, next_name: str) -> str:
    return catalog.split(f'"{name}": {{', 1)[1].split(f'  "{next_name}": {{', 1)[0]


def test_township_card_removes_old_description_and_has_two_links():
    catalog = (ROOT / "site-guides.js").read_text(encoding="utf-8")
    block = catalog.split('"Township": {', 1)[1].split('  "きのこ伝説": {', 1)[0]
    assert "Lv60までの基礎攻略とLv70実プレイを1ページにまとめています。" not in block
    assert 'href: "township-lv70.html"' in block
    assert 'href: "progress.html?game=Township"' in block
    assert 'label: "みんなの進捗を見る →"' in block


def test_progress_links_follow_page_type_instead_of_every_game():
    catalog = (ROOT / "site-guides.js").read_text(encoding="utf-8")

    township = _guide_block(catalog, "Township", "きのこ伝説")
    tokyo = _guide_block(catalog, "東京ディバンカー", "パズル＆サバイバル")
    puzzles = _guide_block(catalog, "パズル＆サバイバル", "キングショット")
    kingshot = _guide_block(catalog, "キングショット", "放置少女")
    houchishojo = _guide_block(catalog, "放置少女", "エバーテイル")

    assert 'progress.html?game=Township' in township
    assert 'progress.html?game=東京ディバンカー' not in tokyo
    assert 'progress.html?game=パズル＆サバイバル' not in puzzles
    assert 'progress.html?game=キングショット' not in kingshot
    assert 'progress.html?game=放置少女' not in houchishojo
    assert 'href: "puzzles-survival-guide.html"' in puzzles
    assert 'href: "kingshot-guide.html"' in kingshot
    assert 'href: "houchishojo-guide.html"' in houchishojo


def test_inline_progress_is_embedded_in_research_guides_without_new_button():
    for filename, datafile in (
        ("puzzles-survival-guide.html", "puzzles-survival.json"),
        ("kingshot-guide.html", "kingshot.json"),
        ("houchishojo-guide.html", "houchishojo.json"),
    ):
        page = (ROOT / filename).read_text(encoding="utf-8")
        assert 'id="progress"' in page
        assert f'data-experience-src="data/guide-experiences/{datafile}"' in page
        assert 'href="#progress">みんなの進捗</a>' in page
        assert 'src="assets/guide-experience.js"' in page
        assert 'href="assets/guide-experience.css"' in page


def test_kingshot_progress_has_sourced_completed_and_retired_examples():
    data = json.loads((ROOT / "data" / "guide-experiences" / "kingshot.json").read_text(encoding="utf-8"))
    assert data["game"] == "キングショット"
    players = data["players"]
    assert len(players) >= 8
    assert any(player.get("status") == "completed" for player in players)
    assert any(player.get("status") == "retired" for player in players)
    text = json.dumps(players, ensure_ascii=False)
    assert "役場Lv28" in text
    assert "役場Lv24" in text
    assert "役場Lv20" in text
    assert "x.com/rinpointgame" in text
    for player in players:
        assert player.get("sources")
        assert all(str(url).startswith("https://") for url in player["sources"])


def test_houchishojo_progress_has_paid_unpaid_and_deadline_examples():
    data = json.loads((ROOT / "data" / "guide-experiences" / "houchishojo.json").read_text(encoding="utf-8"))
    assert data["game"] == "放置少女"
    players = data["players"]
    assert len(players) >= 8
    assert any(player.get("status") == "completed" for player in players)
    assert any(player.get("status") == "retired" for player in players)
    text = json.dumps(players, ensure_ascii=False)
    assert "14日" in text
    assert "36日" in text
    assert "1転生Lv19" in text
    assert "Lv72" in text and "Lv100" in text and "Lv119" in text and "Lv120" in text
    assert "note.com/yukidrm_grbr" in text
    assert "warau.jp" in text
    for player in players:
        assert player.get("sources")
        assert all(str(url).startswith("https://") for url in player["sources"])


def test_township_progress_restores_old_examples_and_new_lv70_examples():
    data = json.loads((ROOT / "data" / "guide-experiences" / "township.json").read_text(encoding="utf-8"))
    players = data["players"]
    assert len(players) >= 6
    summaries = "\n".join(str(player.get("summary", "")) for player in players)
    assert "約49日でLv70達成" in summaries
    assert "46日目にLv70達成" in summaries
    assert "55日目にLv70到達" in summaries
    milestone_text = json.dumps(players, ensure_ascii=False)
    assert '"day": 1' in milestone_text and '"level": 11' in milestone_text
    assert '"day": 10' in milestone_text and '"level": 22' in milestone_text
    assert '"day": 23' in milestone_text and '"level": 35' in milestone_text
    assert "ポイント反映問い合わせ中" in milestone_text


def test_progress_page_maps_existing_separate_datasets_and_has_safe_empty_state():
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


def test_public_builder_includes_progress_page_and_guide_experience_data():
    builder = (ROOT / "scripts" / "build_public_site.py").read_text(encoding="utf-8")
    assert '"progress.html"' in builder
    assert '"guide-experiences"' in builder
