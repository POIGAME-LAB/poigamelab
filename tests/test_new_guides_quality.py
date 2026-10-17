"""Quality gate for the 2026-10-16 batch of spec-rendered guides (Notion publication gate, 2026-09).

Every guide must be reproducible from its spec, share the kinoko layout, carry a table of contents that
resolves, expose per-player experience data with source URLs, and be registered for the public build,
the sitemap and the guide hub. Specs live in research/new-guides/2026-10-16/.
"""
import csv
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import pytest

from scripts import build_public_site
from scripts.render_guide_from_spec import experience_json, render, validate

ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = ROOT / "research" / "new-guides" / "2026-10-16"
SPECS = sorted(p for p in SPEC_DIR.glob("*.json"))


def _spec(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _text(html):
    body = html[html.find("<body"):]
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", body, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


def test_batch_has_ten_specs():
    assert len(SPECS) == 10


@pytest.mark.parametrize("path", SPECS, ids=lambda p: p.stem)
def test_spec_is_valid(path):
    assert validate(_spec(path)) == []


@pytest.mark.parametrize("path", SPECS, ids=lambda p: p.stem)
def test_html_and_experience_json_match_spec(path):
    spec = _spec(path)
    html_path = ROOT / spec["file"]
    assert html_path.read_text(encoding="utf-8") == render(spec)
    exp_path = ROOT / "data" / "guide-experiences" / f"{spec['slug']}.json"
    assert json.loads(exp_path.read_text(encoding="utf-8")) == experience_json(spec)


@pytest.mark.parametrize("path", SPECS, ids=lambda p: p.stem)
def test_layout_toc_and_experience_panel(path):
    spec = _spec(path)
    html = (ROOT / spec["file"]).read_text(encoding="utf-8")
    assert "assets/guide-experience.css" in html and "assets/guide-experience.js" in html
    assert f'data-experience-src="data/guide-experiences/{spec["slug"]}.json"' in html
    assert html.count('<nav class="toc"') == 1
    assert html.index('class="hero"') < html.index('<nav class="toc"') < html.index('id="condition"')
    ids = set(re.findall(r'id="([^"]+)"', html))
    for target in re.findall(r'<nav class="toc".*?</nav>', html, flags=re.S)[0].split('href="#')[1:]:
        assert target.split('"')[0] in ids
    assert f'<link rel="canonical" href="https://poigamelab.com/{spec["file"]}"' in html


@pytest.mark.parametrize("path", SPECS, ids=lambda p: p.stem)
def test_public_text_has_no_internal_wording_or_unverified_markers(path):
    text = _text((ROOT / _spec(path)["file"]).read_text(encoding="utf-8"))
    for token in ("調査中", "準備中", "読み込み中", "検索しました", "Xでは", "Instagramでは", "YouTubeでは", "TODO", "ダミー"):
        assert token not in text, token
    assert "確実に達成" not in text and "必ず達成" not in text


@pytest.mark.parametrize("path", SPECS, ids=lambda p: p.stem)
def test_players_are_individual_cases_with_sources(path):
    exp = experience_json(_spec(path))
    players = exp["players"]
    assert len(players) >= 5
    assert len({p["id"] for p in players}) == len(players)
    assert any(p["status"] in ("retired", "ongoing") for p in players) or "確認できていません" in exp["notice"]
    for p in players:
        assert p["sources"] and all(u.startswith("https://") for u in p["sources"])
        assert p["milestones"]


def test_all_pages_registered_for_build_sitemap_and_hub():
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    registry = (ROOT / "site-researched-guides.js").read_text(encoding="utf-8")
    hub = (ROOT / "guides.html").read_text(encoding="utf-8")
    for path in SPECS:
        spec = _spec(path)
        assert spec["file"] in build_public_site.ROOT_FILES
        assert f"https://poigamelab.com/{spec['file']}" in sitemap
        assert spec["game"] in registry
        assert spec["file"] in hub


def test_new_games_do_not_duplicate_catalog_or_existing_guides():
    with open(ROOT / "games.csv", encoding="utf-8-sig", newline="") as fh:
        catalog = {row.get("game_name") or row.get("name") or "" for row in csv.DictReader(fh)}
    existing = {p.name for p in ROOT.glob("*-guide.html")} - {_spec(p)["file"] for p in SPECS}
    for path in SPECS:
        spec = _spec(path)
        assert spec["game"] not in catalog
        assert spec["file"] not in existing
    games = [_spec(p)["game"] for p in SPECS]
    assert len(set(games)) == len(games)


def test_guides_are_not_template_copies_of_each_other():
    texts = {p.stem: _text((ROOT / _spec(p)["file"]).read_text(encoding="utf-8")) for p in SPECS}
    names = sorted(texts)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ratio = SequenceMatcher(None, texts[a][:6000], texts[b][:6000], autojunk=False).quick_ratio()
            assert ratio < 0.85, (a, b, ratio)


@pytest.mark.parametrize("path", SPECS, ids=lambda p: p.stem)
def test_guide_points_to_real_current_offer_pages_not_missing_comparison_page(path):
    spec = _spec(path)
    html = (ROOT / spec["file"]).read_text(encoding="utf-8")
    bar = re.search(r'<div class="poigame-context-bar">.*?</div>\s*</div>', html, flags=re.S).group(0)
    assert 'href="offers.html"' not in bar and "game.html?game=" not in html
    assert re.search(r'<a href="https://[^"]+" target="_blank" rel="noopener nofollow">', bar)
    assert 'class="key offer-guide"' in html
    for link in spec["offerLinks"]:
        assert f'<a href="{link["url"]}" target="_blank" rel="noopener nofollow">{link["label"]}</a>' in html
    assert spec["game"] not in (ROOT / "games.csv").read_text(encoding="utf-8-sig")


def test_warau_review_based_records_stay_identifiable():
    index = json.loads((SPEC_DIR / "evidence" / "warau-review-index.json").read_text(encoding="utf-8"))["reviews"]
    keyed = {(r["guide"], r["player"]): r for r in index}
    for path in SPECS:
        spec = _spec(path)
        for p in spec["experience"]["players"]:
            if any("warau.jp" in u and "point_id=" in u for u in p["sources"]) and not p["sources"][0].startswith("https://www.warau.jp/style"):
                detail = " ".join(p.get("sourceDetails", []))
                assert detail, (spec["slug"], p["id"])
                rec = keyed[(spec["slug"], p["id"])]
                assert rec["postedOn"] in detail and rec["posterLabel"] in detail
                assert len(rec["bodySha256"]) == 64
    assert len(index) >= 60


def test_guides_without_failed_cases_state_the_success_bias():
    for slug in ("sangokushi-shinsen", "the-ants", "tsue-to-ken"):
        exp = experience_json(_spec(SPEC_DIR / f"{slug}.json"))
        assert all(p["status"] != "retired" for p in exp["players"])
        assert "偏" in exp["notice"]
