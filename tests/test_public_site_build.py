import importlib.util
import json
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_public_site",
    ROOT / "scripts" / "build_public_site.py",
)
builder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(builder)


class LocalReferenceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"href", "src", "data-experience-src"} and value:
                self.references.append((tag, key, value))


def local_reference_target(page: Path, reference: str):
    raw = reference.strip()
    if not raw or raw.startswith(("#", "data:", "mailto:", "tel:", "javascript:", "//")):
        return None
    if "$" + "{" in raw or "{{" in raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        return None
    if parsed.path.startswith("/"):
        raise AssertionError(f"root-relative reference breaks project Pages: {page.name}: {raw}")
    path = unquote(parsed.path)
    if not path:
        return page
    return (page.parent / path).resolve()


@pytest.fixture
def output_dir():
    path = ROOT / ".test-public-site"
    if path.exists():
        shutil.rmtree(path)
    yield path
    if path.exists():
        shutil.rmtree(path)


def test_public_site_builder_copies_only_launch_allowlist(output_dir):
    copied = builder.build_public_site(output_dir)
    copied_set = set(copied)

    required = {
        "index.html", "game.html", "offers.html", "guides.html", "404.html",
        "about.html", "privacy.html", "contact.html", "tokyo-debunker-guide.html",
        "puzzles-survival-guide.html", "kingshot-guide.html", "houchishojo-guide.html",
        "evertale-guide.html", "site-data.js", "site-footer.js", "site-referrals.js",
        "site-guides.js", "site-image-rights.js", "site-header.js", "games.js",
        "games.csv", "robots.txt", "poigamelab_icon.png", "assets/guide-experience.css",
        "assets/guide-experience.js", "data/published_offers.csv", "data/offer_history.csv",
        "data/refresh_status.json", "data/exception_queue.json",
        "data/guide-experiences/kinoko.json", "data/guide-experiences/mementomori.json",
        "data/guide-experiences/whiteout-survival.json",
        "data/guide-experiences/working-heroes.json", "config/refresh_policy.json",
    }
    assert required <= copied_set

    forbidden = {
        "offers.csv", "sources.csv", "trend_sources.csv", "README.md", "AGENTS.md",
        "config/approved_offer_baselines.json", "config/offerwall_providers.json",
        "data/warau_baseline_candidates.json", "data/trend_candidates.json",
        "data/research_queue.json",
    }
    assert copied_set.isdisjoint(forbidden)
    for prefix in (".github/", "docs/", "scripts/", "tests/", "data/research_results/"):
        assert not any(path.startswith(prefix) for path in copied_set)
    assert {p for p in copied_set if p.startswith("data/")} == {
        "data/published_offers.csv", "data/offer_history.csv", "data/refresh_status.json",
        "data/exception_queue.json", "data/guide-experiences/kinoko.json",
        "data/guide-experiences/mementomori.json", "data/guide-experiences/whiteout-survival.json",
        "data/guide-experiences/working-heroes.json",
    }
    assert {p for p in copied_set if p.startswith("config/")} == {"config/refresh_policy.json"}


def test_public_artifact_is_self_contained_for_current_managed_games(output_dir):
    builder.build_public_site(output_dir)
    policy = json.loads((output_dir / "config" / "refresh_policy.json").read_text())
    assert set(policy["games"]) == {
        "Township", "きのこ伝説", "メメントモリ", "ワーキングヒーロー",
        "ホワイトアウト・サバイバル", "東京ディバンカー", "パズル＆サバイバル",
        "キングショット", "放置少女", "エバーテイル",
    }
    site_data = (output_dir / "site-data.js").read_text()
    assert "data/published_offers.csv" in site_data
    assert "config/refresh_policy.json" in site_data
    assert not (output_dir / "offers.csv").exists()
    not_found = (output_dir / "404.html").read_text()
    assert 'name="robots" content="noindex,nofollow"' in not_found
    assert 'src="site-footer.js"' in not_found



def test_mementomori_has_verified_published_reward(output_dir):
    builder.build_public_site(output_dir)
    import csv
    rows = list(csv.DictReader((output_dir / "data" / "published_offers.csv").open(encoding="utf-8", newline="")))
    matches = [row for row in rows if row["game"] == "メメントモリ" and row["verified"].lower() == "true"]
    assert matches, "MementoMori must keep at least one verified published offer"
    best = max(matches, key=lambda row: int(row["reward"]))
    assert best["site"] == "warau"
    assert best["platform"] == "iOS"
    assert best["reward"] == "11500"
    assert "point_id=206037" in best["url"]
    assert "ランク140到達" in best["condition"]
    assert "累計10000円課金" in best["condition"]

    review = json.loads((ROOT / "data" / "comparison_review_queue.json").read_text(encoding="utf-8"))
    evidence = next(
        item["sourceEvidence"] for item in review["items"]
        if item["game"] == "メメントモリ"
        and item["source"] == "warau"
        and item.get("sourceEvidence", {}).get("state") == "parsed"
        and item["sourceEvidence"].get("offerId") == "206037"
    )
    assert best["platform"] == evidence["platform"]
    assert int(best["reward"]) == evidence["rewardPoints"]

def test_mementomori_has_current_hapitas_comparison_pair(output_dir):
    builder.build_public_site(output_dir)
    import csv

    rows = list(csv.DictReader(
        (output_dir / "data" / "published_offers.csv").open(encoding="utf-8", newline="")
    ))
    matches = [
        row for row in rows
        if row["game"] == "メメントモリ" and row["site"] == "hapitas"
    ]
    assert {(row["platform"], row["reward"]) for row in matches} == {
        ("iOS", "4815"),
        ("Android", "4815"),
    }
    assert {row["url"] for row in matches} == {
        "https://hapitas.jp/item/detail/itemid/99420",
        "https://hapitas.jp/item/detail/itemid/99421",
    }
    assert all(row["verified"].lower() == "true" for row in matches)
    assert all("ランク160到達" in row["condition"] for row in matches)
    assert all(row["deadline"] == "インストール後45日以内" for row in matches)


def test_kinoko_has_current_hapitas_ios_android_pair(output_dir):
    builder.build_public_site(output_dir)
    import csv

    rows = list(csv.DictReader(
        (output_dir / "data" / "published_offers.csv").open(encoding="utf-8", newline="")
    ))
    matches = [
        row for row in rows
        if row["game"] == "きのこ伝説" and row["site"] == "hapitas"
    ]
    assert {(row["platform"], row["reward"], row["url"]) for row in matches} == {
        ("iOS", "18142", "https://hapitas.jp/item/detail/itemid/102450"),
        ("Android", "14792", "https://hapitas.jp/item/detail/itemid/102451"),
    }
    assert all(row["verified"].lower() == "true" for row in matches)
    assert all(row["updatedAt"] == "2026-09-08" for row in matches)
    assert all("Lv125到達" in row["condition"] for row in matches)
    assert all("Lv120は40日以内" in row["deadline"] for row in matches)
    assert all("Lv125は45日以内" in row["deadline"] for row in matches)


def test_puzzles_survival_has_current_hapitas_ios_android_pair(output_dir):
    builder.build_public_site(output_dir)
    import csv

    rows = list(csv.DictReader(
        (output_dir / "data" / "published_offers.csv").open(encoding="utf-8", newline="")
    ))
    matches = [
        row for row in rows
        if row["game"] == "パズル＆サバイバル" and row["site"] == "hapitas"
    ]
    assert {(row["platform"], row["reward"], row["url"]) for row in matches} == {
        ("iOS", "35015", "https://hapitas.jp/item/detail/itemid/98148"),
        ("Android", "30612", "https://hapitas.jp/item/detail/itemid/99158"),
    }
    assert all(row["verified"].lower() == "true" for row in matches)
    assert all(row["updatedAt"] == "2026-09-08" for row in matches)
    assert all(row["deadline"] == "インストール後30日以内" for row in matches)
    assert all("レベル7/12/17/25/30到達" in row["condition"] for row in matches)



def test_current_warau_offerwall_amounts_are_published_with_provider_labels(output_dir):
    builder.build_public_site(output_dir)
    import csv

    rows = list(csv.DictReader(
        (output_dir / "data" / "published_offers.csv").open(encoding="utf-8", newline="")
    ))
    expected = {
        "206501": ("メメントモリ", "iOS", "4906", "SmaAD"),
        "206500": ("メメントモリ", "Android", "4906", "SmaAD"),
        "206488": ("パズル＆サバイバル", "Android", "8628", "SmaAD"),
        "206460": ("パズル＆サバイバル", "Android", "13016", "GF Rewards"),
    }
    for offer_id, (game, platform, reward, provider) in expected.items():
        matches = [
            row for row in rows
            if row["site"] == "warau" and f"point_id={offer_id}" in row["url"]
        ]
        assert len(matches) == 1
        row = matches[0]
        assert row["game"] == game
        assert row["platform"] == platform
        assert row["reward"] == reward
        assert row["provider"] == provider
        assert row["verified"].lower() == "true"
        assert row["updatedAt"] == "2026-09-08"
        assert "StepUpミッションをクリア" in row["condition"]


def test_current_reviewed_warau_comparison_rows_match_source_evidence(output_dir):
    builder.build_public_site(output_dir)
    import csv

    rows = list(csv.DictReader(
        (output_dir / "data" / "published_offers.csv").open(encoding="utf-8", newline="")
    ))
    review = json.loads((ROOT / "data" / "comparison_review_queue.json").read_text(encoding="utf-8"))
    evidence_by_id = {
        str(item.get("sourceEvidence", {}).get("offerId")): item["sourceEvidence"]
        for item in review["items"]
        if item.get("source") == "warau"
        and item.get("sourceEvidence", {}).get("state") == "parsed"
        and item.get("sourceEvidence", {}).get("parserVersion") == "warau-stepup-v1"
    }
    expected = {
        "201872": ("ホワイトアウト・サバイバル", "Android", 11500),
        "201862": ("ホワイトアウト・サバイバル", "iOS", 11500),
        "206425": ("パズル＆サバイバル", "Android", 24600),
        "204984": ("キングショット", "Android", 16000),
        "204983": ("キングショット", "iOS", 16000),
        "206411": ("放置少女", "iOS", 2000),
    }
    for offer_id, (game, platform, reward) in expected.items():
        matches = [row for row in rows if row["site"] == "warau" and f"point_id={offer_id}" in row["url"]]
        assert len(matches) == 1
        row = matches[0]
        evidence = evidence_by_id[offer_id]
        assert row["game"] == game == next(
            item["game"] for item in review["items"]
            if str(item.get("sourceEvidence", {}).get("offerId")) == offer_id
        )
        assert row["platform"] == platform == evidence["platform"]
        assert int(row["reward"]) == reward == evidence["rewardPoints"]
        assert row["verified"].lower() == "true"
        assert row["updatedAt"] == "2026-09-08"

    assert not any(
        row["site"] == "warau" and "point_id=205557" in row["url"]
        for row in rows
    )


def test_builder_rejects_unsafe_output_locations(tmp_path):
    with pytest.raises(ValueError, match="unsafe_output_directory"):
        builder.build_public_site(ROOT)
    with pytest.raises(ValueError, match="unsafe_output_directory"):
        builder.build_public_site(tmp_path / "outside")


def test_all_static_local_html_references_exist_in_public_artifact(output_dir):
    builder.build_public_site(output_dir)
    output_root = output_dir.resolve()
    failures = []
    for page in sorted(output_dir.rglob("*.html")):
        parser = LocalReferenceParser()
        parser.feed(page.read_text(encoding="utf-8"))
        for tag, attribute, reference in parser.references:
            try:
                target = local_reference_target(page, reference)
            except AssertionError as error:
                failures.append(str(error))
                continue
            if target is None:
                continue
            if output_root not in target.parents and target != output_root:
                failures.append(f"reference escapes artifact: {page.name}: {reference}")
                continue
            if not target.exists():
                failures.append(f"missing local {tag}[{attribute}] target: {page.relative_to(output_dir)} -> {reference}")
    assert failures == []


def test_adsense_code_is_present_on_monetized_pages(output_dir):
    builder.build_public_site(output_dir)
    publisher_id = "ca-pub-2224207953863103"
    monetized_pages = {
        "index.html", "game.html", "offers.html", "guides.html", "kinoko-guide.html",
        "mementomori-guide.html", "township-lv60.html", "township-lv70.html",
        "whiteout-survival-guide.html", "working-heroes-guide.html", "tokyo-debunker-guide.html",
        "puzzles-survival-guide.html", "kingshot-guide.html", "houchishojo-guide.html",
        "evertale-guide.html",
    }
    for filename in monetized_pages:
        html = (output_dir / filename).read_text(encoding="utf-8")
        assert html.count(publisher_id) == 1
        assert "pagead2.googlesyndication.com/pagead/js/adsbygoogle.js" in html
        assert publisher_id in html.split("</head>", 1)[0]
    for filename in {"404.html", "data-status.html"}:
        assert publisher_id not in (output_dir / filename).read_text(encoding="utf-8")


def test_every_catalog_game_has_published_guide_mapping(output_dir):
    builder.build_public_site(output_dir)
    import csv
    import re
    games = list(csv.DictReader((output_dir / "games.csv").open(encoding="utf-8", newline="")))
    guide_text = (output_dir / "site-guides.js").read_text(encoding="utf-8")
    mapped_games = set(re.findall(r'^  "([^"]+)": \{$', guide_text, flags=re.MULTILINE))
    catalog_games = {row["name"] for row in games}
    assert mapped_games == catalog_games
    hrefs = re.findall(r'href: "([^"]+)"', guide_text)
    assert hrefs
    assert len(hrefs) == len(set(hrefs))
    guide_pages = {}
    for href in hrefs:
        assert not href.startswith("/")
        target = output_dir / href
        assert target.is_file(), f"missing guide target: {href}"
        guide_pages[href] = target.read_text(encoding="utf-8")
    for game in catalog_games:
        expected_backlink = f"game.html?game={game}"
        assert any(expected_backlink in html for html in guide_pages.values()), f"no guide page links back to game detail: {game}"


def test_ga4_uses_standard_gtag_snippet_once_on_public_pages(output_dir):
    builder.build_public_site(output_dir)
    measurement_id = "G-E4SF1QQDWB"
    loader = '<script async src="https://www.googletagmanager.com/gtag/js?id=' + measurement_id + '"></script>'
    config = "gtag('config', 'G-E4SF1QQDWB');"
    tracked_pages = {
        "index.html", "game.html", "offers.html", "guides.html", "kinoko-guide.html",
        "mementomori-guide.html", "township-lv60.html", "township-lv70.html",
        "whiteout-survival-guide.html", "working-heroes-guide.html", "tokyo-debunker-guide.html",
        "puzzles-survival-guide.html", "kingshot-guide.html", "houchishojo-guide.html",
        "evertale-guide.html", "about.html", "privacy.html", "contact.html", "404.html",
    }
    for filename in tracked_pages:
        html = (output_dir / filename).read_text(encoding="utf-8")
        head = html.split("</head>", 1)[0]
        assert html.count(loader) == 1
        assert html.count(config) == 1
        assert html.count(measurement_id) == 2
        assert 'src="site-analytics.js"' not in html
        assert loader in head
        assert config in head
        assert head.index(loader) < head.index(config)
    internal_status = (output_dir / "data-status.html").read_text(encoding="utf-8")
    assert measurement_id not in internal_status
    assert "googletagmanager.com/gtag/js" not in internal_status


def test_privacy_policy_discloses_google_analytics(output_dir):
    builder.build_public_site(output_dir)
    html = (output_dir / "privacy.html").read_text(encoding="utf-8")
    assert "Google Analytics 4" in html
    assert "Google プライバシーポリシー" in html
    assert "2026年9月5日" in html


def test_shared_header_and_navigation_are_wired(output_dir):
    builder.build_public_site(output_dir)
    header_js = (output_dir / "site-header.js").read_text(encoding="utf-8")
    assert "poigamelab_logo_horizontal.png" in header_js
    assert '["ゲームを探す", "index.html#game-list"]' in header_js
    assert '["案件一覧", "offers.html"]' in header_js
    assert '["攻略一覧", "guides.html"]' in header_js
    assert '["POIGAME LABとは", "about.html"]' in header_js
    assert '["お問い合わせ", "contact.html"]' in header_js
    assert "poigame-site-header__menu" in header_js
    assert "poigame-mobile-menu-dialog" in header_js
    shared_header_pages = {
        "index.html", "game.html", "offers.html", "guides.html", "kinoko-guide.html",
        "mementomori-guide.html", "township-lv60.html", "township-lv70.html",
        "whiteout-survival-guide.html", "working-heroes-guide.html", "tokyo-debunker-guide.html",
        "puzzles-survival-guide.html", "kingshot-guide.html", "houchishojo-guide.html",
        "evertale-guide.html", "about.html", "privacy.html", "contact.html",
    }
    for filename in shared_header_pages:
        html = (output_dir / filename).read_text(encoding="utf-8")
        assert html.count('src="site-header.js?v=20260905-0315"') == 1
        assert 'src="site-header.js"' not in html
    for filename in {
        "kinoko-guide.html", "mementomori-guide.html", "township-lv60.html", "township-lv70.html",
        "whiteout-survival-guide.html", "working-heroes-guide.html", "tokyo-debunker-guide.html",
        "puzzles-survival-guide.html", "kingshot-guide.html", "houchishojo-guide.html", "evertale-guide.html",
    }:
        assert '<header class="topbar">' not in (output_dir / filename).read_text(encoding="utf-8")


def test_homepage_cards_offer_direct_compare_and_guide_actions(output_dir):
    builder.build_public_site(output_dir)
    html = (output_dir / "index.html").read_text(encoding="utf-8")
    assert 'id="game-list"' in html
    assert 'href="offers.html" class="view-all"' in html
    assert 'src="site-guides.js"' in html
    assert "比較を見る" in html
    assert "攻略を見る" in html
    assert "card-action--guide" in html
    assert "game.html?game=" in html
    assert "#comparison" in html


def test_game_detail_renders_point_site_and_offerwall_provider_together(output_dir):
    builder.build_public_site(output_dir)
    html = (output_dir / "game.html").read_text(encoding="utf-8")
    assert "<th>ポイントサイト / 掲載枠</th>" in html
    assert "POIGAME_DATA.formatOfferSourceLabel(siteName, offer.provider)" in html
    assert "POIGAME_DATA.formatOfferSourceLabel(bestSiteName, bestOffer.provider)" in html
    assert "POIGAME_DATA.escapeHtml(sourceLabel)" in html


def test_game_detail_uses_compact_offer_condition_formatter(output_dir):
    builder.build_public_site(output_dir)
    html = (output_dir / "game.html").read_text(encoding="utf-8")
    assert html.count("POIGAME_DATA.summarizeOfferCondition(offer.condition, offer.type)") == 2
    assert 'POIGAME_DATA.escapeHtml(offer.condition)' not in html


def test_game_detail_exposes_guide_cta_near_top(output_dir):
    builder.build_public_site(output_dir)
    html = (output_dir / "game.html").read_text(encoding="utf-8")
    assert 'id="gameTopGuideCta"' in html
    assert 'id="gameTopGuideLinks"' in html
    assert 'id="comparison"' in html
    assert 'id="gameArtwork"' in html


def test_approved_catalog_game_art_is_published(output_dir):
    builder.build_public_site(output_dir)
    import csv
    games = {row["name"]: row for row in csv.DictReader((output_dir / "games.csv").open(encoding="utf-8", newline=""))}
    approved_local = {
        "Township": "assets/game-art/township-original.jpeg",
        "きのこ伝説": "assets/game-art/kinoko-original.png",
        "メメントモリ": "assets/game-art/mementomori-new.png.PNG",
        "ホワイトアウト・サバイバル": "assets/game-art/whiteout-survival-new.png.PNG",
        "東京ディバンカー": "assets/game-art/tokyo-debunker.jpeg",
        "パズル＆サバイバル": "assets/game-art/puzzles-survival-new.png.PNG",
        "キングショット": "assets/game-art/kingshot-new.png.PNG",
        "放置少女": "assets/game-art/houchishojo-new.png.PNG",
        "エバーテイル": "assets/game-art/evertale-new.png.PNG",
    }
    for game, image in approved_local.items():
        assert games[game]["image"] == image
        assert (output_dir / image).is_file(), f"missing approved image: {image}"
    published_local = {
        str(row.get("image") or "").strip()
        for row in games.values()
        if str(row.get("image") or "").strip().startswith("assets/game-art/")
    }
    assert published_local == set(approved_local.values())


def test_mobile_menu_uses_native_top_layer_dialog(output_dir):
    builder.build_public_site(output_dir)
    header_js = (output_dir / "site-header.js").read_text(encoding="utf-8")
    assert 'document.createElement("dialog")' in header_js
    assert 'dialog.showModal();' in header_js
    assert 'dialog.close();' in header_js
    assert 'document.body.appendChild(dialog)' in header_js
    assert '.poigame-mobile-menu-dialog::backdrop' in header_js
    assert 'width: 100vw;' in header_js
    assert 'height: 100dvh;' in header_js
    assert 'inset: 0;' in header_js
    assert 'box-sizing: border-box;' in header_js
    assert 'position: absolute;' in header_js
    assert 'top: calc(env(safe-area-inset-top, 0px) + 78px);' in header_js
    assert 'right: 14px;' in header_js
    assert 'aria-controls="poigame-mobile-menu"' in header_js
    assert 'document.body.style.overflow = open ? "hidden" : "";' in header_js
    assert 'z-index: 2147483001' not in header_js


def test_homepage_does_not_hide_shared_mobile_nav(output_dir):
    builder.build_public_site(output_dir)
    html = (output_dir / "index.html").read_text(encoding="utf-8")
    assert "\n    nav {\n" not in html
    assert "\n    nav a {\n" not in html
    assert "\n      nav {\n        display: none;\n      }" not in html
    assert "header nav {" in html
    assert "header nav a {" in html
    assert "header nav {\n        display: none;" in html
    assert 'src="site-header.js?v=20260905-0315"' in html


def test_image_rights_framework_is_published_and_rendered(output_dir):
    builder.build_public_site(output_dir)
    rights = (output_dir / "site-image-rights.js").read_text(encoding="utf-8")
    assert "POIGAME_IMAGE_RIGHTS" in rights
    assert "メメントモリ" not in rights
    assert "BANK OF INNOVATION" not in rights
    for filename in {"index.html", "offers.html", "guides.html", "game.html"}:
        html = (output_dir / filename).read_text(encoding="utf-8")
        assert 'src="site-image-rights.js"' in html
        assert "POIGAME_IMAGE_RIGHTS" in html
        assert "image-rights-note" in html or "gameArtworkRights" in html
    game_html = (output_dir / "game.html").read_text(encoding="utf-8")
    assert 'id="gameArtworkRights"' in game_html
