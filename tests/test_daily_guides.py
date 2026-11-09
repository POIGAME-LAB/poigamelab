"""Quality gate for every daily new-guide batch in research/daily-guides/<date>/ (routine-produced).

For each completed article the page must be reproducible from the manuscript package, the offer table must
equal the same-day first-party evidence (every Step, total, payment flag, deadline), the experience data must
be the package file unchanged (unknown days stay null, never 0), and the page must be registered guide-only
(no catalog / published-offer rows, no comparison-page links). The negative tests prove the gate rejects
tampered packages, so a passing batch cannot be produced by editing facts to fit.
"""
import copy
import csv
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest

from scripts import build_daily_guides as bdg
from scripts import build_public_site, daily_guide_candidates as cand, daily_guide_evidence as evid
from scripts.render_cited_guide import render, source_ids
from scripts.render_guide_from_spec import experience_json

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "research" / "daily-guides"
BATCHES = sorted(p for p in DAILY.glob("20*-*-*") if p.is_dir())
ARTICLES = [(b, s) for b in BATCHES for s in bdg.completed_slugs(b)]
IDS = [f"{b.name}/{s}" for b, s in ARTICLES]


def _j(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _text(html):
    body = html[html.find("<body"):]
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", body, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", body))


def test_batches_exist_and_have_selection_reports():
    assert BATCHES, "no daily batch committed"
    for b in BATCHES:
        sel = _j(b / "selection.json")
        assert sel["productionDate"] == b.name
        assert sel["completedCount"] == len(bdg.completed_slugs(b)) <= 5
        assert sel["publicationAuthorized"] is False
        assert (b / "REPORT.md").is_file() and (b / "candidates.json").is_file()
        done = {d["slug"] for d in sel["decisions"] if d["decision"] == "completed"}
        assert done == set(bdg.completed_slugs(b))
        for d in sel["decisions"]:
            assert d["decision"] in {"completed", "held", "excluded"} and d.get("reason")


@pytest.mark.parametrize("batch,slug", ARTICLES, ids=IDS)
def test_gate_passes_and_page_reproducible(batch, slug):
    assert bdg.gate(batch, slug) == []
    spec = bdg.build_spec(batch, slug)
    assert _j(batch / slug / "spec.json") == spec
    assert (ROOT / spec["file"]).read_text(encoding="utf-8") == render(spec)
    exp = _j(ROOT / "data" / "guide-experiences" / f"{slug}.json")
    assert exp == experience_json(spec)
    assert {k: v for k, v in exp.items() if k not in ("schemaVersion", "game")} == {
        k: v for k, v in _j(batch / slug / "experiences.json").items() if k not in ("schemaVersion", "game")}
    for p in exp["players"]:
        for m in p["milestones"]:
            assert m["day"] is None or m["day"] > 0


@pytest.mark.parametrize("batch,slug", ARTICLES, ids=IDS)
def test_offer_table_equals_same_day_evidence(batch, slug):
    meta = _j(batch / slug / "metadata.json")
    ev = {c["pointId"]: c for c in _j(bdg.evidence_path(batch, slug))["checks"]}
    text = _text((ROOT / meta["proposedPage"]).read_text(encoding="utf-8"))
    for o in meta["offers"]:
        c = ev[o["pointId"]]
        assert c["httpStatus"] == 200 and c["live"] and c["stepSumMatchesTotal"]
        assert [(s["condition"], s["rewardPt"]) for s in o["steps"]] == [(s["condition"], s["rewardPt"]) for s in c["steps"]]
        assert sum(s["rewardPt"] for s in o["steps"]) == o["totalDisplayedPt"] == c["totalPt"]
        assert sum(s["rewardPt"] for s in o["steps"] if not s["requiresPayment"]) == o["sumWithoutPurchaseStepsPt"]
        assert f"{o['totalDisplayedPt']:,}pt" in text
        for s in o["steps"]:
            assert f"{s['rewardPt']:,}pt" in text
        if c.get("temporaryIncrease"):
            assert c["temporaryIncrease"]["until"] in text  # a boosted amount is always disclosed as temporary
    for prev in meta.get("previousOffers", []):
        c = ev[prev["pointId"]]
        assert c["live"] is False and c["unavailableReason"]  # shown as no longer available on the latest check
        assert prev["pointId"] not in {o["pointId"] for o in meta["offers"]}
        assert f"{prev['totalDisplayedPt']:,}pt" not in text  # an old amount is never presented as current


@pytest.mark.parametrize("batch,slug", ARTICLES, ids=IDS)
def test_seo_head_and_manuscript_carried_over(batch, slug):
    meta = _j(batch / slug / "metadata.json")
    html = (ROOT / meta["proposedPage"]).read_text(encoding="utf-8")
    assert html.count("<title>") == 1 and f"<title>{meta['seoTitle']} | POIGAME LAB</title>" in html
    assert f'<meta name="description" content="{meta["metaDescription"]}">' in html
    assert f'<link rel="canonical" href="{meta["canonical"]}">' in html
    assert html.count("<h1>") == 1 and "application/ld+json" not in html
    article = (batch / slug / "article.md").read_text(encoding="utf-8")
    text = _text(html)
    paras = [ln.strip() for ln in article.splitlines() if ln.strip() and not re.match(r"(#|\||- |<a id|\d+\. )", ln)]
    assert len(paras) >= 20
    for para in paras:
        assert para.replace("**", "") in text, para[:60]


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


@pytest.mark.parametrize("batch,slug", ARTICLES, ids=IDS)
def test_toc_citations_and_internal_links_resolve(batch, slug):
    spec = _j(batch / slug / "spec.json")
    html = (ROOT / spec["file"]).read_text(encoding="utf-8")
    p = _Ids()
    p.feed(html)
    assert len(p.ids) == len(set(p.ids))
    toc = re.search(r'<nav class="toc".*?</nav>', html, flags=re.S).group(0)
    for t in re.findall(r'href="#([^"]+)"', toc):
        assert t in p.ids
    for href in p.hrefs:
        if href.startswith("#"):
            assert href[1:] in p.ids, href
        elif not href.startswith("https://"):
            assert (ROOT / href.split("#")[0].split("?")[0]).is_file(), href
        assert not href.startswith("game.html")
    assert set(re.findall(r'<a class="cite" href="#src-([A-Z]\d+)">', html)) == set(source_ids(spec))
    assert p.headings[0] == 1 and p.headings.count(1) == 1
    for prev, cur in zip(p.headings, p.headings[1:]):
        assert cur <= prev + 1
    for token in ("調査中", "準備中", "読み込み中", "TODO", "ダミー", "manuscript", "handoff", "candidates.json"):
        assert token not in _text(html)
    assert "<img" not in html.split("<body>", 1)[1]


def test_registered_guide_only_without_catalog_or_offer_rows():
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    registry = (ROOT / "site-researched-guides.js").read_text(encoding="utf-8")
    hub = (ROOT / "guides.html").read_text(encoding="utf-8")
    with open(ROOT / "games.csv", encoding="utf-8-sig", newline="") as fh:
        catalog = {cand.norm_key(r["name"]) for r in csv.DictReader(fh)}
    published = (ROOT / "data" / "published_offers.csv").read_text(encoding="utf-8-sig")
    for batch, slug in ARTICLES:
        meta = _j(batch / slug / "metadata.json")
        f = meta["proposedPage"]
        assert f in build_public_site.ROOT_FILES
        assert sitemap.count(f"<loc>https://poigamelab.com/{f}</loc>") == 1
        assert registry.count(f'href: "{f}"') == 1
        assert hub.count(f'href="{f}"') == 1
        assert cand.norm_key(meta["game"]) not in catalog
        for o in meta["offers"]:
            assert o["url"] not in published


def test_no_game_is_produced_twice_across_batches():
    seen = {}
    for batch, slug in ARTICLES:
        key = cand.norm_key(_j(batch / slug / "metadata.json")["game"])
        assert key not in seen, (slug, seen.get(key))
        seen[key] = f"{batch.name}/{slug}"


# ---------------------------------------------------------------- negative gate tests (tampering is caught)
@pytest.fixture
def tmp_batch(tmp_path):
    if not ARTICLES:
        pytest.skip("no article")
    batch, slug = ARTICLES[0]
    dst = tmp_path / batch.name
    shutil.copytree(batch, dst)
    return dst, slug


def _edit(path, fn):
    data = _j(path)
    fn(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_gate_rejects_reward_not_matching_evidence(tmp_batch):
    b, slug = tmp_batch
    _edit(b / slug / "metadata.json", lambda m: m["offers"][0]["steps"][-1].update(rewardPt=m["offers"][0]["steps"][-1]["rewardPt"] + 100))
    errs = bdg.gate(b, slug)
    assert any(e.startswith("offer_steps_differ_from_evidence") for e in errs)
    assert any(e.startswith("offer_total_mismatch") for e in errs)


def test_gate_rejects_unflagged_purchase_and_missing_deadline(tmp_batch):
    b, slug = tmp_batch

    def tamper(m):
        for s in m["offers"][0]["steps"]:
            if s["requiresPayment"]:
                s["requiresPayment"] = False
                break
        m["offers"][0]["steps"][0]["deadlineDays"] = None
    _edit(b / slug / "metadata.json", tamper)
    errs = bdg.gate(b, slug)
    assert any(e.startswith("purchase_step_not_flagged") for e in errs)
    assert any(e.startswith("step_deadline_missing") for e in errs)


def test_gate_rejects_stale_evidence_and_dead_offer(tmp_batch):
    b, slug = tmp_batch
    for rc in (b / "evidence").glob(f"{slug}-offers-recheck-*.json"):
        rc.unlink()  # fall back to the production-day evidence
    _edit(b / "evidence" / f"{slug}-offers.json", lambda e: (e.update(checkedAtJst="2026-01-01T09:00:00+09:00"), e["checks"][0].update(live=False)))
    errs = bdg.gate(b, slug)
    assert "offer_evidence_not_from_batch_date" in errs
    assert any(e.startswith("offer_not_live_in_evidence") for e in errs)


def test_gate_rejects_day_zero_old_records_and_too_few_players(tmp_batch):
    b, slug = tmp_batch

    def tamper(x):
        x["players"][0]["milestones"][0]["day"] = 0
        for p in x["players"]:
            p["postedOn"] = "2024-01-01"
    _edit(b / slug / "experiences.json", tamper)
    errs = bdg.gate(b, slug)
    assert any(e.startswith("player_day_zero") for e in errs)
    assert any(e.startswith("player_record_older_than_365_days") for e in errs)
    assert "needs_2_independent_current_players" in errs


def test_gate_rejects_undisclosed_boost_and_promises(tmp_batch):
    b, slug = tmp_batch
    art = b / slug / "article.md"
    art.write_text(art.read_text(encoding="utf-8").replace("当サイト自身がプレイした結果ではありません。", "必ずもらえる金額です。"), encoding="utf-8")
    pid = _j(b / slug / "metadata.json")["offers"][0]["pointId"]
    # a temporary increase on the latest evidence must be disclosed with its end date
    _edit(bdg.evidence_path(b, slug), lambda e: next(c for c in e["checks"] if c["pointId"] == pid).update(
        temporaryIncrease={"regularPt": 1, "increasedPt": 2, "until": "2099年1月1日"}))
    errs = bdg.gate(b, slug)
    assert "forbidden_claim:必ずもらえる" in errs
    assert f"temporary_increase_not_disclosed:{pid}" in errs


def test_gate_uses_latest_recheck_evidence(tmp_batch):
    b, slug = tmp_batch
    latest = bdg.evidence_path(b, slug)
    assert latest.name.startswith(f"{slug}-offers")
    if latest.name == f"{slug}-offers.json":
        pytest.skip("no pre-publication re-check in this batch")
    # a current offer that the latest re-check shows as ended must fail, even if the old file had it live
    meta = _j(b / slug / "metadata.json")
    pid = meta["offers"][0]["pointId"]
    _edit(latest, lambda e: next(c for c in e["checks"] if c["pointId"] == pid).update(live=False, steps=[], totalPt=None))
    assert f"offer_not_live_in_evidence:{pid}" in bdg.gate(b, slug)


def test_gate_rejects_previous_offer_presented_as_current(tmp_batch):
    b, slug = tmp_batch
    meta = _j(b / slug / "metadata.json")
    if not meta.get("previousOffers"):
        pytest.skip("no previous offers recorded")
    prev = meta["previousOffers"][0]
    _edit(b / slug / "page.json", lambda pg: pg["offerLinks"].append({"label": "旧", "url": prev["url"]}))
    _edit(bdg.evidence_path(b, slug), lambda e: next(c for c in e["checks"] if c["pointId"] == prev["pointId"]).update(live=True))
    errs = bdg.gate(b, slug)
    assert f"previous_offer_linked_as_current:{prev['pointId']}" in errs
    assert f"previous_offer_not_shown_unavailable_in_latest_evidence:{prev['pointId']}" in errs


def test_gate_rejects_uncited_offer_and_seo_mismatch(tmp_batch):
    b, slug = tmp_batch
    _edit(b / slug / "metadata.json", lambda m: m.update(seoTitle=m["seoTitle"] + "！", canonical="https://poigamelab.com/x.html"))
    errs = bdg.gate(b, slug)
    assert "h1_must_equal_seoTitle" in errs and "canonical_mismatch" in errs


# ---------------------------------------------------------------- evidence parser (no network)
OFFER_HTML = """<title>テスト（StepUp）でポイントを貯める｜ワラウ</title>
<div>■獲得条件</div><div>新規アプリインストール後、StepUpミッションの各達成条件をクリア</div>
<div>1,000pt</div><div> →</div><div>最大</div><div>1,100</div><div>pt</div><div> 2026年11月07日まで</div>
<div>iOS</div><div>達成条件</div><div>獲得pt</div>
<div>30日以内にレベル10到達</div><div>100</div><div>pt</div>
<div>30日以内に300円パック購入</div><div>1,000</div><div>pt</div>
<div>累計 </div><div>1,100</div><div>pt</div><div>広告主：Example Studio</div>
<div>クチコミ</div><div>ねこ</div><div>さん (女性・30代)</div><div>2026/10/01</div><div>見出し</div><div>(4.0)</div><div>本文に購入の話</div><div>このクチコミは</div>"""


def test_evidence_parser_reads_steps_total_boost_and_reviews():
    d = evid.parse_offer(OFFER_HTML)
    assert d["live"] and d["os"] == "iOS" and d["advertiser"] == "Example Studio"
    assert d["steps"] == [{"condition": "30日以内にレベル10到達", "rewardPt": 100}, {"condition": "30日以内に300円パック購入", "rewardPt": 1000}]
    assert d["totalPt"] == d["stepSum"] == 1100 and d["stepSumMatchesTotal"]
    assert d["temporaryIncrease"] == {"regularPt": 1000, "increasedPt": 1100, "until": "2026年11月07日"}
    assert d["reviewIndex"] == [{"name": "ねこ", "attribute": "女性・30代", "date": "2026-10-01", "title": "見出し"}]
    assert all("本文" not in n for n in d["termNotes"])  # review bodies are never copied


def test_evidence_parser_records_end_notice_without_reading_related_cards():
    raw = ("<title>掲載終了のご案内｜ワラウ</title><p>広告にアクセスすることができませんでした</p><p>▼関連のサービスをご利用ください▼</p>"
           '<a href="/contents/point/pointEntrance.php?point_id=201563&pl=endEntrance">ミステリータウン</a><p>10,510</p><p>pt</p><p>iOS</p>'
           '<a href="/contents/point/pointEntrance.php?point_id=207823&amp;pl=endEntranceSimilar">別ゲーム</a>')
    d = evid.parse_offer(raw)
    assert d["live"] is False and d["unavailableReason"] == "listing_end_notice_shown"
    assert d["relatedPointIds"] == ["201563"]  # the "similar ads" list is not the same game
    assert d["os"] is None and d["steps"] == [] and d["totalPt"] is None  # the related card's OS/amount is not this offer's


def test_evidence_parser_never_reads_unavailable_page_as_zero():
    d = evid.parse_offer("<title>ワラウ</title><p>こちらのページは表示できません</p>")
    assert d["live"] is False and d["unavailableReason"] == "page_not_viewable_publicly"
    assert d["steps"] == [] and d["totalPt"] is None and not d["stepSumMatchesTotal"]


# ---------------------------------------------------------------- candidate selection (no network)
def _mini_root(tmp_path, checked="2026-11-04T21:56:46+00:00"):
    (tmp_path / "data").mkdir()
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "config" / "point_value_rates.json", tmp_path / "config")
    (tmp_path / "games.csv").write_text("name,image\nTownship,x\n", encoding="utf-8")
    (tmp_path / "foo-guide.html").write_text("<h1>既存ゲーム ポイ活攻略</h1>", encoding="utf-8")
    (tmp_path / "research" / "daily-guides").mkdir(parents=True)
    (tmp_path / "research" / "daily-guides" / "aliases.json").write_text(
        json.dumps({"aliases": {"Township": ["タウンシップ"]}}, ensure_ascii=False), encoding="utf-8")
    queue = {"checkedAt": checked, "rankingComplete": True, "count": 1, "items": [
        {"rank": 1, "game": "Freecash", "maxObservedRewardYen": 39560, "verifiedRewardSourceCount": 1,
         "pointSiteEvidence": [{"source": "amefuri", "url": "https://example.com/1", "rewardYen": 39560}]}]}
    items = [
        {"titleHint": "【SKYFLAG】新作パズル（StepUp） 初回アプリインストール後 最大 12,000 pt iOS", "source": "warau", "classification": "likely_game", "isNewToday": True, "firstPartyCandidateUrl": "https://example.com/a"},
        {"titleHint": "新作パズル（StepUp） 最大 9,000 pt Android", "source": "warau", "classification": "likely_game", "isNewToday": True, "firstPartyCandidateUrl": "https://example.com/b"},
        {"titleHint": "NEW 別ゲーム 50,000pt 30日以内に到達", "source": "gendama", "classification": "likely_game", "isNewToday": True, "firstPartyCandidateUrl": "https://example.com/c"},
        {"titleHint": "既存ゲーム（StepUp） 最大 99,999 pt iOS", "source": "warau", "classification": "likely_game", "isNewToday": False, "firstPartyCandidateUrl": "https://example.com/d"},
        {"titleHint": "タウンシップ（Lv20） 3,000P", "source": "moppy", "classification": "likely_game", "isNewToday": False, "firstPartyCandidateUrl": "https://example.com/e"},
        {"titleHint": "クレジットカード発行 20,000P", "source": "moppy", "classification": "likely_non_game", "isNewToday": True, "firstPartyCandidateUrl": "https://example.com/f"},
    ]
    monitor = {"checkedAt": checked, "items": items, "counts": {}, "displayLimits": {}}
    (tmp_path / "data" / "new_game_content_queue.json").write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "data" / "new_game_monitor.json").write_text(json.dumps(monitor, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_candidates_fail_closed_on_previous_day_data(tmp_path):
    root = _mini_root(tmp_path, checked="2026-11-03T21:56:46+00:00")
    out = cand.build("2026-11-05", root)
    assert out["status"] == "stale_input" and out["candidates"] == []


def test_candidates_group_rank_and_exclude(tmp_path):
    out = cand.build("2026-11-05", _mini_root(tmp_path))
    assert out["status"] == "ok"
    names = [c["game"] for c in out["candidates"]]
    assert names[0] == "新作パズル" and names.count("新作パズル") == 1  # iOS/Android rows grouped
    top = out["candidates"][0]
    assert top["listingRewardHintYen"] == 12000 and top["osHints"] == ["Android", "iOS"]
    assert "別ゲーム" in names
    assert next(c for c in out["candidates"] if c["game"] == "別ゲーム")["listingRewardHintYen"] is None  # gendama pt is not 1:1
    reasons = {(e["game"], e["reason"]) for e in out["excluded"]}
    assert ("Freecash", "aggregator_or_reward_wall_not_a_single_game") in reasons
    assert ("既存ゲーム", "already_covered") in reasons
    assert ("タウンシップ", "already_covered") in reasons  # editor-reviewed alias of a catalog game
    assert any(r == "scan_classified_likely_non_game" for _, r in reasons)


def test_candidates_exclude_open_pull_request_games(tmp_path):
    out = cand.build("2026-11-05", _mini_root(tmp_path), extra_exclude=["新作パズル"])
    assert "新作パズル" not in [c["game"] for c in out["candidates"]]


def test_candidate_name_normalisation():
    assert cand.display_name("【SKYFLAG】【注意事項必読】Monster Hunter Outlanders（StepUp） 初回") == "Monster Hunter Outlanders"
    assert cand.display_name("iOS_モーマンタイム【StepUp】 アプリ利用でキャッシュバック") == "モーマンタイム【StepUp】"
    assert cand.norm_key("ミステリータウン：マージゲーム - Mystery Town") == cand.norm_key("ミステリータウン:マージゲーム－Mystery Town")
