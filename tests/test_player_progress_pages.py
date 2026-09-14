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
    evertale = _guide_block(catalog, "エバーテイル", "ATLAS: EARTH")
    atlas = _guide_block(catalog, "ATLAS: EARTH", "ファミリーファームの冒険")
    family = _guide_block(catalog, "ファミリーファームの冒険", "クロンダイクの冒険")
    klondike = _guide_block(catalog, "クロンダイクの冒険", "Merge Help: ホームデザインパズル")

    assert 'progress.html?game=Township' in township
    assert 'progress.html?game=東京ディバンカー' not in tokyo
    assert 'progress.html?game=パズル＆サバイバル' not in puzzles
    assert 'progress.html?game=キングショット' not in kingshot
    assert 'progress.html?game=放置少女' not in houchishojo
    assert 'progress.html?game=エバーテイル' not in evertale
    assert 'progress.html?game=ATLAS' not in atlas
    assert 'progress.html?game=ファミリーファームの冒険' not in family
    assert 'progress.html?game=クロンダイクの冒険' not in klondike
    assert 'href: "puzzles-survival-guide.html"' in puzzles
    assert 'href: "kingshot-guide.html"' in kingshot
    assert 'href: "houchishojo-guide.html"' in houchishojo
    assert 'href: "evertale-guide.html"' in evertale
    assert 'href: "atlas-earth-guide.html"' in atlas
    assert 'href: "family-farm-adventure-guide.html"' in family
    assert 'href: "klondike-adventures-guide.html"' in klondike


def test_inline_progress_is_embedded_in_research_guides_without_new_button():
    for filename, datafile in (
        ("puzzles-survival-guide.html", "puzzles-survival.json"),
        ("kingshot-guide.html", "kingshot.json"),
        ("houchishojo-guide.html", "houchishojo.json"),
        ("evertale-guide.html", "evertale.json"),
        ("atlas-earth-guide.html", "atlas-earth.json"),
        ("family-farm-adventure-guide.html", "family-farm-adventure.json"),
        ("klondike-adventures-guide.html", "klondike-adventures.json"),
    ):
        page = (ROOT / filename).read_text(encoding="utf-8")
        assert 'id="progress"' in page
        assert f'data-experience-src="data/guide-experiences/{datafile}"' in page
        assert 'href="#progress">' in page
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


def test_evertale_progress_tracks_consecutive_logins_and_reflection_cases():
    data = json.loads((ROOT / "data" / "guide-experiences" / "evertale.json").read_text(encoding="utf-8"))
    assert data["game"] == "エバーテイル"
    players = data["players"]
    assert len(players) >= 5
    text = json.dumps(players, ensure_ascii=False)
    assert "25時間" in text
    assert "15分" in text
    assert "ログイン忘れ" in text
    assert "Day4" in text
    assert "保証申請" in text
    for player in players:
        assert player.get("sources")
        assert all(str(url).startswith("https://") for url in player["sources"])


def test_atlas_earth_progress_has_paid_and_unpaid_pace_examples():
    data = json.loads((ROOT / "data" / "guide-experiences" / "atlas-earth.json").read_text(encoding="utf-8"))
    assert data["game"] == "ATLAS: EARTH"
    players = data["players"]
    assert len(players) >= 5
    text = json.dumps(players, ensure_ascii=False)
    assert "約30分" in text
    assert "土地14個" in text
    assert "7日" in text and "土地5個" in text
    assert "22日" in text and "土地14個" in text
    assert "無課金2週間" in text and "土地6個" in text
    assert "3日で土地1個" in text
    for player in players:
        assert player.get("sources")
        assert all(str(url).startswith("https://") for url in player["sources"])


def test_atlas_earth_guide_matches_full_guide_structure_and_has_pace_sections():
    page = (ROOT / "atlas-earth-guide.html").read_text(encoding="utf-8")
    assert '<div class="eyebrow">POIGAME LAB 攻略データ</div>' in page
    assert page.count('class="stat"') == 3
    assert 'href="#condition"' in page
    assert 'href="#progress"' in page
    assert 'href="#ab"' in page
    assert 'href="#paid"' in page
    assert 'href="#daily"' in page
    assert 'href="#judge"' in page
    assert "無課金2週間" in (ROOT / "data" / "guide-experiences" / "atlas-earth.json").read_text(encoding="utf-8")
    assert "土地は1区画" in page and "100 Atlas Bucks" in page
    assert "X（Twitter）・Instagram・Web検索・YouTube" in page


def test_family_farm_progress_has_fast_slow_and_lv40_failure_examples():
    data = json.loads((ROOT / "data" / "guide-experiences" / "family-farm-adventure.json").read_text(encoding="utf-8"))
    assert data["game"] == "ファミリーファームの冒険"
    players = data["players"]
    assert len(players) >= 8
    assert any(player.get("status") == "completed" for player in players)
    assert any(player.get("status") == "retired" for player in players)
    text = json.dumps(players, ensure_ascii=False)
    assert "7日でLv26" in text
    assert "9日でLv30" in text
    assert "24日でLv30" in text
    assert "20日でLv35" in text
    assert "Lv40未達" in text
    assert "note.com/doto_yatowarenai" in text
    assert "warau.jp" in text
    for player in players:
        assert player.get("sources")
        assert all(str(url).startswith("https://") for url in player["sources"])


def test_family_farm_guide_matches_full_guide_structure_and_core_strategy():
    page = (ROOT / "family-farm-adventure-guide.html").read_text(encoding="utf-8")
    assert '<div class="eyebrow">POIGAME LAB 攻略データ</div>' in page
    assert page.count('class="stat"') == 3
    for anchor in ("condition", "progress", "route", "orders", "explore", "energy", "bottleneck", "factory", "daily", "target", "summary"):
        assert f'href="#{anchor}"' in page
    assert "ヤギミルク" in page
    assert "探索ポイント" in page
    assert "掲示板注文" in page
    assert "Lv40" in page
    assert "X（Twitter）・Instagram" in page


def test_klondike_progress_has_fast_slow_lv40_and_credit_warning_examples():
    data = json.loads((ROOT / "data" / "guide-experiences" / "klondike-adventures.json").read_text(encoding="utf-8"))
    assert data["game"] == "クロンダイクの冒険"
    players = data["players"]
    assert len(players) >= 9
    assert any(player.get("status") == "completed" for player in players)
    assert any(player.get("status") == "retired" for player in players)
    text = json.dumps(players, ensure_ascii=False)
    assert "約45日" in text and "Lv40" in text
    assert "Lv41" in text
    assert "10日でLv24" in text
    assert "15日でLv22" in text
    assert "18日でLv22" in text
    assert "Lv9で早期撤退" in text
    assert "kochalog.com" in text
    assert "warau.jp" in text
    for player in players:
        assert player.get("sources")
        assert all(str(url).startswith("https://") for url in player["sources"])


def test_klondike_guide_matches_full_guide_structure_and_core_strategy():
    page = (ROOT / "klondike-adventures-guide.html").read_text(encoding="utf-8")
    assert '<div class="eyebrow">POIGAME LAB 攻略データ</div>' in page
    assert page.count('class="stat"') == 3
    for anchor in ("condition", "progress", "route", "board", "video", "production", "ship", "energy", "gem", "daily", "target", "summary"):
        assert f'href="#{anchor}"' in page
    assert "注文ボード" in page
    assert "ラリー" in page
    assert "乳製品工場" in page
    assert "Lv41" in page
    assert "X（Twitter）・Instagram・Web検索・YouTube" in page


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
