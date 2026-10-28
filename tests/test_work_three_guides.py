"""Quality gate for the three guides added from the ChatGPT Work delivery (2026-10-27, audited 2026-10-28).

Guides: ザ・グランドマフィア / Bingo Blitz / Heroes vs Crazy Wiggler. They are guide-only additions: no catalog
row, no published offer, no comparison page. Specs live in research/new-guides/2026-10-28/ and are rendered with
scripts/render_guide_from_spec.py (inline source citations enabled).
"""
import csv
import json
import re
from html import unescape
from pathlib import Path

import pytest

from scripts import build_public_site
from scripts.render_guide_from_spec import experience_json, render, validate

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "research" / "new-guides" / "2026-10-28"
SLUGS = ("grand-mafia", "bingo-blitz", "heroes-vs-crazy-wiggler")
ID_LETTER = {"grand-mafia": "G", "bingo-blitz": "B", "heroes-vs-crazy-wiggler": "H"}
OWN_SOURCE_ADDITIONS = {
    "grand-mafia": {"G6": "https://apps.apple.com/jp/app/id1612013407"},
    "bingo-blitz": {"B8": "https://apps.apple.com/jp/app/id529996768"},
    "heroes-vs-crazy-wiggler": {},
}


def spec_of(slug):
    return json.loads((BATCH / f"{slug}.json").read_text(encoding="utf-8"))


def html_of(slug):
    return (ROOT / f"{slug}-guide.html").read_text(encoding="utf-8")


def text_of(html):
    body = html[html.find("<body"):]
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", body, flags=re.S)
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", body)))


def table_rows(html, heading):
    """Rows (list of cell texts) of the first table after the h2/h3 containing ``heading``."""
    start = html.index(heading)
    table = re.search(r"<table>.*?</table>", html[start:], flags=re.S).group(0)
    return [[unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh]>(.*?)</t[dh]>", row, flags=re.S)]
            for row in re.findall(r"<tr>(.*?)</tr>", table, flags=re.S)][1:]


def num(value):
    return int(re.sub(r"[^\d]", "", value))


@pytest.mark.parametrize("slug", SLUGS)
def test_spec_is_valid_and_outputs_match_spec(slug):
    spec = spec_of(slug)
    assert validate(spec) == []
    assert html_of(slug) == render(spec)
    exp_path = ROOT / "data" / "guide-experiences" / f"{slug}.json"
    assert json.loads(exp_path.read_text(encoding="utf-8")) == experience_json(spec)


def test_specs_are_reproducible_from_the_work_delivery():
    import subprocess
    import sys

    before = {s: (BATCH / f"{s}.json").read_text(encoding="utf-8") for s in SLUGS}
    subprocess.run([sys.executable, "-I", str(BATCH / "tools" / "build_specs.py")], cwd=ROOT, check=True, capture_output=True)
    after = {s: (BATCH / f"{s}.json").read_text(encoding="utf-8") for s in SLUGS}
    assert before == after


@pytest.mark.parametrize("slug", SLUGS)
def test_layout_toc_anchors_and_experience_panel(slug):
    html = html_of(slug)
    assert "assets/guide-experience.css" in html and "assets/guide-experience.js" in html
    assert f'data-experience-src="data/guide-experiences/{slug}.json"' in html
    assert html.count('<section id="pace" class="experience-panel"') == 1
    toc = re.findall(r'<nav class="toc".*?</nav>', html, flags=re.S)
    assert len(toc) == 1
    assert html.index('class="hero"') < html.index('<nav class="toc"') < html.index('id="condition"')
    ids = re.findall(r'\sid="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    targets = re.findall(r'href="#([^"]+)"', toc[0])
    assert len(targets) == 9 or len(targets) == len(set(targets))
    for target in targets:
        assert target in ids, target
    # every h2 section named in the TOC is a real heading
    for sec_id in re.findall(r'<section class="section" id="([^"]+)"><h2>', html):
        assert sec_id in targets


@pytest.mark.parametrize("slug", SLUGS)
def test_seo_head(slug):
    spec = spec_of(slug)
    html = html_of(slug)
    assert f'<link rel="canonical" href="https://poigamelab.com/{slug}-guide.html">' in html
    assert f"<title>{spec['title']} | POIGAME LAB</title>" in html
    desc = re.search(r'<meta name="description" content="([^"]+)"', html).group(1)
    assert 60 <= len(desc) <= 160
    assert html.count("<title>") == 1 and html.count('rel="canonical"') == 1
    assert "ポイ活攻略" in spec["title"] and spec["game"] in spec["title"]


@pytest.mark.parametrize("slug", SLUGS)
def test_citations_link_only_to_this_games_sources(slug):
    html = html_of(slug)
    spec = spec_of(slug)
    letter = ID_LETTER[slug]
    work_sources = {s["id"]: s["url"] for s in json.loads((BATCH / "work-originals" / "sources.json").read_text(encoding="utf-8"))["sources"]}
    page_sources = {s["id"]: s["url"] for s in spec["sources"]}
    for sid, url in page_sources.items():
        assert sid[0] in (letter, "R"), (slug, sid)
        expected = work_sources.get(sid) or OWN_SOURCE_ADDITIONS[slug][sid]
        assert url == expected, (slug, sid)
        assert f'id="src-{sid}"><a href="{url.replace("&", "&amp;")}" target="_blank" rel="noopener">{sid}：' in html
    cited = re.findall(r'<a class="cite" href="#src-([A-Z]\d+)">\[\1\]</a>', html)
    assert cited
    assert set(cited) <= set(page_sources)
    # the article body uses every non-rate source of its own game at least once
    assert {i for i in page_sources if i[0] == letter} <= set(cited)
    # no bare [ID] text is left behind
    assert not re.findall(r"\[[A-Z]\d+\]", re.sub(r'<a class="cite"[^>]*>.*?</a>', "", html))
    # the source list links only to this game's sources (no other game's ID)
    other = {"G", "B", "H"} - {letter}
    assert not [i for i in re.findall(r'id="src-([A-Z]\d+)"', html) if i[0] in other]


@pytest.mark.parametrize("slug", SLUGS)
def test_experience_json_structure(slug):
    data = json.loads((ROOT / "data" / "guide-experiences" / f"{slug}.json").read_text(encoding="utf-8"))
    assert data["schemaVersion"] == 1 and data["game"] == spec_of(slug)["game"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["updatedAt"])
    for key in ("title", "intro", "notice", "footnote"):
        assert data[key].strip()
    players = data["players"]
    assert len(players) >= 3
    assert len({p["id"] for p in players}) == len(players)
    page_urls = {s["url"] for s in spec_of(slug)["sources"]}
    for p in players:
        assert p["status"] in ("completed", "retired", "ongoing")
        assert p["summary"].strip() and p["note"].strip()
        assert p["milestones"] and all(m.get("label") for m in p["milestones"])
        assert p["sources"] and all(u in page_urls for u in p["sources"])
        assert p["sourceDetails"] and all(isinstance(d, str) and d for d in p["sourceDetails"])
    # at least one case that stopped early, so the guide is not success-only
    assert any(p["status"] == "retired" for p in players)


@pytest.mark.parametrize("slug", SLUGS)
def test_public_text_has_no_internal_wording(slug):
    text = text_of(html_of(slug))
    for token in ("調査中", "準備中", "読み込み中", "検索しました", "Xでは", "Instagramでは", "YouTubeでは", "TODO", "ダミー",
                  "画像準備中", "内部メモ", "handoff", "Claude", "ChatGPT", "Work原稿"):
        assert token not in text, token
    assert "確実に達成" not in text and "必ず達成" not in text


@pytest.mark.parametrize("slug", SLUGS)
def test_guide_only_addition_links_to_real_offer_pages(slug):
    spec = spec_of(slug)
    html = html_of(slug)
    assert "game.html?game=" not in html and "offers.html?game=" not in html
    bar = re.search(r'<div class="poigame-context-bar">.*?</div>\s*</div>', html, flags=re.S).group(0)
    assert re.search(r'<a href="https://[^"]+" target="_blank" rel="noopener nofollow">', bar)
    assert 'class="key offer-guide"' in html
    for link in spec["offerLinks"]:
        assert f'<a href="{link["url"].replace("&", "&amp;")}" target="_blank" rel="noopener nofollow">{link["label"]}</a>' in html
    catalog = (ROOT / "games.csv").read_text(encoding="utf-8-sig")
    offers = (ROOT / "data" / "published_offers.csv").read_text(encoding="utf-8-sig")
    for needle in (spec["game"], spec["slug"]):
        assert needle not in catalog and needle not in offers


def test_registered_for_build_sitemap_registry_and_hub_without_duplicates():
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    registry = (ROOT / "site-researched-guides.js").read_text(encoding="utf-8")
    hub = (ROOT / "guides.html").read_text(encoding="utf-8")
    for slug in SLUGS:
        spec = spec_of(slug)
        assert spec["file"] in build_public_site.ROOT_FILES
        assert build_public_site.ROOT_FILES.count(spec["file"]) == 1
        assert sitemap.count(f"<loc>https://poigamelab.com/{spec['file']}</loc>") == 1
        assert registry.count(f'"{spec["game"]}": {{') + registry.count(f'  {json.dumps(spec["game"], ensure_ascii=False)}: {{') >= 1
        assert registry.count(f'href: "{spec["file"]}"') == 1
        assert hub.count(f'href="{spec["file"]}"') == 1
        assert hub.count(f"<h2>{spec['registry']['title']}</h2>") == 1


def test_existing_guides_are_not_overwritten_by_this_batch():
    existing = {p.name for p in ROOT.glob("*-guide.html")} - {f"{s}-guide.html" for s in SLUGS}
    assert len(existing) >= 35
    for slug in SLUGS:
        assert f"{slug}-guide.html" not in existing


# ---- audit findings (ChatGPT audit 2026-10-28) ----------------------------------------------------

def test_grand_mafia_totals_match_amefuri_table_and_metadata():
    html = html_of("grand-mafia")
    rows = table_rows(html, "現在の案件条件")
    body, total = rows[:-1], rows[-1]
    assert len(body) == 12
    assert sum(num(r[2]) for r in body) == num(total[2]) == 701980
    assert sum(num(r[3]) for r in body) == num(total[3]) == 70198
    assert all(num(r[2]) == num(r[3]) * 10 for r in body)
    meta = json.loads((BATCH / "work-originals" / "grand-mafia" / "metadata.json").read_text(encoding="utf-8"))
    assert [num(r[2]) for r in body] == [s["points"] for s in meta["verifiedOffer"]["steps"]]
    # the two Tier4 steps are listed separately with their own deadlines
    assert [r[1] for r in body if "Tier4" in r[0]] == ["30日", "60日"]


def test_grand_mafia_deadline_wording_does_not_assert_install_based_60_days():
    html = html_of("grand-mafia")
    text = text_of(html)
    assert "全体期限はインストールから60日以内" not in text
    assert "調査受付も60日以内" not in text
    # click-based 60 days / 50-day investigation window are stated, with the confirmation date
    assert "成果到達期限が「クリックから60日以内」" in text
    assert "成果調査受付期限が「クリックから50日以内」" in text
    assert "2026年10月28日" in text
    # the 51-60 day gap is flagged without asserting what the point site does
    assert "51日目から60日目" in text and "当サイトでは断定できません" in text
    # the start of each Step period is not guessed
    assert "何日目から数えるかは、アメフリiOSの案件ページに明記が見当たりません" in text


def test_grand_mafia_tier4_double_reward_is_not_promised():
    text = text_of(html_of("grand-mafia"))
    assert "両方の報酬が必ず受け取れるとは考えないでください" in text
    assert "両方の報酬が必ず付与されるとは言えません" in text
    assert "19,798円相当" in text and 70198 - 33600 - 16800 == 19798
    assert "T4の完走日数を示す数字ではありません" in text
    for forbidden in ("T4を2回受け取", "T4の報酬が2回", "両方の報酬を受け取れます"):
        assert forbidden not in text


def test_bingo_blitz_keeps_android_and_ios_amounts_apart():
    html = html_of("bingo-blitz")
    text = text_of(html)
    rows = table_rows(html, "Androidで確認した条件")
    body, total = rows[:-1], rows[-1]
    assert len(body) == 15
    assert sum(num(r[2]) for r in body) == num(total[2]) == 27770
    assert sum(num(r[2]) for r in body if "課金" not in r[0]) == 25520
    assert "iOSコースは最大17,770pt＝17,770円相当" in text
    assert "今回確認したiOSコースは17,770円相当です" in text
    assert "最大額（Android・購入条件込み）27,770円相当" in text and "最大額（iOS・購入条件込み）17,770円相当" in text
    # iOS is never described with the Android 27,770 total
    assert not re.search(r"iOS[^。]{0,30}27,770", text)
    assert "通常表示はAndroidが21,600pt、iOSが15,200pt" in text


def test_bingo_blitz_past_examples_are_not_current_completion_days():
    text = text_of(html_of("bingo-blitz"))
    assert "現行コースの最終都市（Androidはキョート、iOSはアルプス）までの完走日数ではありません" in text
    assert "過去のマイアミ3日例を、現行の全条件達成日数へ置き換えないでください" in text
    assert "3日で終わる案件ですか？" in text
    data = json.loads((ROOT / "data" / "guide-experiences" / "bingo-blitz.json").read_text(encoding="utf-8"))
    assert "現行のキョート・アルプスとは目標が異なります" in data["intro"]
    assert "現行コース全額達成の所要日数として扱わないでください" in data["notice"]


def test_bingo_blitz_age_statement_cites_official_sources():
    html = html_of("bingo-blitz")
    text = text_of(html)
    assert "21歳以上向け" in text
    assert re.search(r'21歳以上向け.{0,120}<a class="cite" href="#src-B1">\[B1\]</a><a class="cite" href="#src-B6">\[B6\]</a>', html, flags=re.S)


def test_heroes_reward_table_and_normal_only_examples():
    html = html_of("heroes-vs-crazy-wiggler")
    text = text_of(html)
    rows = table_rows(html, "現在の案件条件")
    body, total = rows[:-1], rows[-1]
    assert len(body) == 12
    assert sum(num(r[1]) for r in body) == num(total[1]) == 11400
    assert sum(num(r[1]) for r in body[:3]) == 50
    assert sum(num(r[1]) for r in body if "ダイヤ" not in r[0]) == 10180
    assert "ノーマル2・6・10の合計は50円相当" in text
    assert "ヘル70まで2日で終わるという意味ではありません" in text
    assert "2日で達成した記録があるのはノーマル10までです" in text
    assert not re.search(r"ヘル(難易度)?70[^。]{0,20}(を|まで)[^。]{0,10}2日で(達成|クリア)", text)
    data = json.loads((ROOT / "data" / "guide-experiences" / "heroes-vs-crazy-wiggler.json").read_text(encoding="utf-8"))
    assert "ヘル70までの目安ではありません" in data["intro"]
    assert "ヘル70の十分な期限内完走例は確認できていません" in data["notice"]


def test_heroes_red_and_blue_diamonds_are_not_mixed_up():
    text = text_of(html_of("heroes-vs-crazy-wiggler"))
    assert "赤いダイヤの指定数量を一括購入する条件です" in text
    assert "青いダイヤの購入は対象外" in text
    assert "赤いダイヤ4,990を一括購入" in text and "赤いダイヤ19,990を一括購入" in text
    assert not re.search(r"青い?ダイヤ[^。]{0,12}(4,990|9,990|19,990)", text)


def test_source_ids_in_work_handoffs_are_not_reused_across_games():
    """Bingo Blitz / Heroes pages must not carry the Grand Mafia G-IDs (handoff.md of both still said [G1])."""
    for slug, bad in (("bingo-blitz", "G"), ("heroes-vs-crazy-wiggler", "G"), ("grand-mafia", "B"), ("grand-mafia", "H")):
        html = html_of(slug)
        assert not re.findall(rf"\[{bad}\d+\]|#src-{bad}\d+|id=\"src-{bad}\d+\"", html), (slug, bad)
    for slug in ("bingo-blitz", "heroes-vs-crazy-wiggler"):
        assert "play.google.com/store/apps/details?hl=ja&amp;id=com.yottagames" not in html_of(slug)


def test_protected_public_data_has_no_rows_for_the_new_guides():
    with open(ROOT / "games.csv", encoding="utf-8-sig", newline="") as fh:
        names = {row["name"] for row in csv.DictReader(fh)}
    for slug in SLUGS:
        assert spec_of(slug)["game"] not in names
    offers = (ROOT / "data" / "published_offers.csv").read_text(encoding="utf-8-sig")
    for needle in ("グランドマフィア", "Bingo Blitz", "Crazy Wiggler"):
        assert needle not in offers
