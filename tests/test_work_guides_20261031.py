"""Quality gate for the 2026-10-31 ChatGPT Work batch (Domino Dreams / Arrows / 戦国布武).

The manuscripts in research/new-guides/2026-10-31/work-originals/ are the source of truth. These tests
check that the pages are reproducible from the specs, that body text, offer tables and source IDs were
carried over without rewriting, that the experience data is the Work file unchanged (null stays null),
that the reference-only record is not counted as a current example, and that the pages are registered
guide-only (no catalog / published offer rows, no comparison-page links).
"""
import csv
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from scripts import build_public_site
from scripts.render_cited_guide import render, source_ids, validate
from scripts.render_guide_from_spec import experience_json

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "research" / "new-guides" / "2026-10-31"
ORIG = BATCH / "work-originals"
SLUGS = ("domino-dreams", "arrows", "sengoku-fubu")
FILES = {"domino-dreams": "domino-dreams-guide.html", "arrows": "arrows-guide.html", "sengoku-fubu": "sengoku-fubu-guide.html"}


def _spec(slug):
    return json.loads((BATCH / f"{slug}.json").read_text(encoding="utf-8"))


def _orig(slug, name):
    path = ORIG / slug / name
    return json.loads(path.read_text(encoding="utf-8")) if name.endswith(".json") else path.read_text(encoding="utf-8")


def _html(slug):
    return (ROOT / FILES[slug]).read_text(encoding="utf-8")


def _text(html):
    body = html[html.find("<body"):]
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", body, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", body))


def test_originals_match_work_checksums():
    sums = {}
    for line in (ORIG / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(None, 1)
        sums[name.strip()] = digest
    checked = 0
    for name, digest in sums.items():
        path = ORIG / name
        if name.startswith("held/") or not path.exists():
            continue
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
        checked += 1
    assert checked >= 15
    assert not (ORIG / "held").exists()


@pytest.mark.parametrize("slug", SLUGS)
def test_spec_valid_and_page_reproducible(slug):
    spec = _spec(slug)
    assert validate(spec) == []
    assert _html(slug) == render(spec)
    exp_path = ROOT / "data" / "guide-experiences" / f"{slug}.json"
    assert json.loads(exp_path.read_text(encoding="utf-8")) == experience_json(spec)


@pytest.mark.parametrize("slug", SLUGS)
def test_experience_json_is_work_file_unchanged(slug):
    data = json.loads((ROOT / "data" / "guide-experiences" / f"{slug}.json").read_text(encoding="utf-8"))
    assert data == _orig(slug, "experiences.json")
    for p in data["players"]:
        for m in p["milestones"]:
            assert m["day"] is None or m["day"] > 0  # unknown days stay null, never 0


@pytest.mark.parametrize("slug", SLUGS)
def test_seo_head_from_metadata(slug):
    meta, html = _orig(slug, "metadata.json"), _html(slug)
    assert html.count("<title>") == 1 and f"<title>{meta['seoTitle']} | POIGAME LAB</title>" in html
    assert f'<meta name="description" content="{meta["metaDescription"]}">' in html
    assert f'<link rel="canonical" href="{meta["canonical"]}">' in html
    assert meta["canonical"] == f"https://poigamelab.com/{FILES[slug]}"
    assert html.count("<h1>") == 1
    assert "application/ld+json" not in html  # no generated review/rating markup


@pytest.mark.parametrize("slug", SLUGS)
def test_manuscript_body_carried_over_verbatim(slug):
    article = _orig(slug, "article.md")
    text = _text(_html(slug))
    paras = [ln.strip() for ln in article.splitlines() if ln.strip() and not ln.startswith(("#", "|", "-", "<a id", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."))]
    assert len(paras) >= 25
    for para in paras:
        plain = para.replace("**", "")
        assert plain in text, plain[:60]
    for row in [ln for ln in article.splitlines() if ln.startswith("|") and not ln.startswith("| ---")]:
        for cell in [c.strip() for c in row.strip().strip("|").split("|")]:
            assert cell.replace("**", "") in text, cell


@pytest.mark.parametrize("slug", SLUGS)
def test_offer_table_matches_metadata_steps_and_totals(slug):
    meta = _orig(slug, "metadata.json")["offer"]
    steps = meta["steps"]
    assert sum(s["rewardPt"] for s in steps) == meta["totalDisplayedPt"]
    assert sum(s["rewardPt"] for s in steps if not s["requiresPayment"]) == meta["sumWithoutPurchaseStepsPt"]
    text = _text(_html(slug))
    assert f"{meta['totalDisplayedPt']:,}pt" in text
    for s in steps:
        assert f"{s['rewardPt']:,}" in text


def test_offer_recheck_evidence_matches_manuscripts():
    rec = json.loads((BATCH / "evidence" / "offer-recheck-20261104.json").read_text(encoding="utf-8"))
    by_id = {c["pointId"]: c for c in rec["checks"]}
    assert set(by_id) == {"192689", "207054", "206085", "206086"}
    for c in rec["checks"]:
        meta = _orig(c["slug"], "metadata.json")["offer"]
        assert c["matchesManuscript"] and c["osMatches"]
        assert c["totalPt"] == c["stepSum"] == meta["totalDisplayedPt"]
        assert [s["rewardPt"] for s in c["steps"]] == [s["rewardPt"] for s in meta["steps"]]
        assert all(r["present"] for r in c.get("reviewsStillListed", []))
    assert by_id["206085"]["beginnerBonusExcludedNotice"] and by_id["207054"]["dataTransferExcludedNotice"]
    for slug in SLUGS:
        assert "2026年11月4日（日本時間）に同じ案件ページを再取得" in _text(_html(slug))
        assert "2026年10月31日" in _text(_html(slug))  # original research date stays visible


class _Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.hrefs, self.headings = [], [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "a" and "href" in a:
            self.hrefs.append(a["href"])
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))


@pytest.mark.parametrize("slug", SLUGS)
def test_toc_anchors_citations_and_internal_links_resolve(slug):
    html, spec = _html(slug), _spec(slug)
    p = _Ids()
    p.feed(html)
    assert len(p.ids) == len(set(p.ids))
    ids = set(p.ids)
    toc = re.search(r'<nav class="toc".*?</nav>', html, flags=re.S).group(0)
    targets = re.findall(r'href="#([^"]+)"', toc)
    article_toc = re.findall(r"\]\(#([a-z-]+)\)", _orig(slug, "article.md"))
    assert [t for t in targets if t != "records"] == article_toc
    for t in targets:
        assert t in ids
    assert html.index('class="hero"') < html.index('<nav class="toc"') < html.index('id="condition"') < html.index('id="pace"') < html.index('id="records"')
    for href in p.hrefs:
        if href.startswith("#"):
            assert href[1:] in ids, href
        elif not href.startswith("https://"):
            assert (ROOT / href.split("#")[0].split("?")[0]).is_file(), href
            assert not href.startswith("game.html")
    cited = set(re.findall(r'<a class="cite" href="#src-([A-Z]\d+)">', html))
    assert cited == set(source_ids(spec))
    assert p.headings[0] == 1 and p.headings.count(1) == 1
    for prev, cur in zip(p.headings, p.headings[1:]):
        assert cur <= prev + 1


@pytest.mark.parametrize("slug", SLUGS)
def test_source_list_matches_work_sources(slug):
    html = _html(slug)
    src = {s["id"]: s["url"] for s in _orig(slug, "sources.json")["sources"]}
    for s in _spec(slug)["sources"]:
        assert src[s["id"]] == s["url"]
        assert f'id="src-{s["id"]}"' in html


@pytest.mark.parametrize("slug", SLUGS)
def test_no_internal_wording_and_no_comparison_page(slug):
    html = _html(slug)
    text = _text(html)
    for token in ("調査中", "準備中", "読み込み中", "検索しました", "TODO", "ダミー", "画像準備中", "manuscript", "handoff"):
        assert token not in text, token
    assert "game.html?game=" not in html
    bar = re.search(r'<div class="poigame-context-bar">.*?</div>\s*</div>', html, flags=re.S).group(0)
    assert 'href="offers.html"' not in bar and "https://www.warau.jp/" in bar
    assert "<img" not in html.split("<body>", 1)[1]


def test_registered_guide_only_without_catalog_or_offer_rows():
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    registry = (ROOT / "site-researched-guides.js").read_text(encoding="utf-8")
    hub = (ROOT / "guides.html").read_text(encoding="utf-8")
    catalog = (ROOT / "games.csv").read_text(encoding="utf-8-sig")
    published = (ROOT / "data" / "published_offers.csv").read_text(encoding="utf-8-sig")
    for slug in SLUGS:
        spec = _spec(slug)
        assert spec["file"] in build_public_site.ROOT_FILES
        assert sitemap.count(f"<loc>https://poigamelab.com/{spec['file']}</loc>") == 1
        assert registry.count(f'href: "{spec["file"]}"') == 1
        assert hub.count(f'href="{spec["file"]}"') == 1
        for name in ("Domino", "アローズ", "Arrows", "戦国布武"):
            assert name not in catalog and name not in published


def test_files_do_not_duplicate_existing_guides():
    with open(ROOT / "games.csv", encoding="utf-8-sig", newline="") as fh:
        names = {row.get("game_name") or row.get("name") or "" for row in csv.DictReader(fh)}
    for slug in SLUGS:
        assert _spec(slug)["game"] not in names
    registry = (ROOT / "site-researched-guides.js").read_text(encoding="utf-8")
    assert registry.count("戦国布武") == 2 and registry.count("Domino Dreams") == 2  # key + title


def test_sengoku_reference_record_is_not_counted_as_current_example():
    data = json.loads((ROOT / "data" / "guide-experiences" / "sengoku-fubu.json").read_text(encoding="utf-8"))
    ref = [p for p in data["players"] if str(p.get("dateEligibility", "")).startswith("reference_only")]
    assert [p["id"] for p in ref] == ["D"]
    js = (ROOT / "assets" / "guide-experience.js").read_text(encoding="utf-8")
    assert 'startsWith("reference_only")' in js and "参考記録" in js
