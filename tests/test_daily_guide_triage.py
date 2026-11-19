"""Daily guide triage: offline ranking of ALL candidates + bounded first-party probing (network mocked).

Pins the rules that fix the 2026-11-19 shortfall (178 candidates, ~15 examined, 1 article): candidates are judged by
which first-party sites can actually verify them, not only by reward; unreadable pages are recorded as such and
never as "ended"; Amefuri search adds pages only for an identical cleaned name; the research budget is capped.
"""
import json
from pathlib import Path

import pytest

from scripts import daily_guide_candidates as cand
from scripts import daily_guide_triage as tri

FIX = Path(__file__).resolve().parent / "fixtures" / "offer_pages"
DATE = "2026-11-19"


def _page(name):
    return (FIX / name).read_bytes()


def _row(source, url, title, classification="likely_game"):
    return {"source": source, "url": url, "titleHint": title, "classification": classification, "isNewToday": True}


def _cand(game, rows, order=1, likely=True, hint=1000, **extra):
    sources_ = sorted({r["source"] for r in rows})
    kinds = sorted({cand.kind_hint(r["titleHint"]) for r in rows})
    return {"game": game, "key": cand.norm_key(game), "order": order, "rows": rows, "sources": sources_, "kindHints": kinds,
            "osHints": [], "likelyGame": likely, "listingRewardHintYen": hint, "newToday": True, **extra}


MOPPY_SINGLE = ("https://pc.moppy.jp/ad/detail.php?s_id=161455", "Ball Sort Puzzle（レベル300クリア）_iOS 新規アプリインストール後、30日以内にレベル300クリア 700P")
MOPPY_STEPUP = ("https://pc.moppy.jp/ad/detail.php?s_id=161557", "Coin Master - Board Adventure（StepUp）【iOS】 新規アプリインストール後、30日以内に各成果地点到達でクリア 6,055P")
COINCOME_STEPUP = ("https://cimcome.jp/campaigns/details/10842", "iOS_Onet Master: Puzzle & Art『StepUp』 アプリ利用でキャッシュバック 13,950円 8,403円")
WARAU_SKYFLAG = ("https://www.warau.jp/contents/point/pointEntrance.php?point_id=209332", "【SKYFLAG】Onet Master: Puzzle & Art（StepUp） 初回アプリインストール後、【StepUpミッション】をクリア 最大 13,791 pt 通帳記載")


def _write_candidates(tmp_path, cands):
    d = tmp_path / "research" / "daily-guides" / DATE
    d.mkdir(parents=True)
    (tmp_path / "research" / "daily-guides" / "aliases.json").write_text(json.dumps({"aliases": {}}), encoding="utf-8")
    (d / "candidates.json").write_text(json.dumps({"status": "ok", "productionDate": DATE, "candidates": cands,
                                                   "inputs": {"monitor": {"checkedAt": "2026-11-18T22:57:45+00:00"}}}, ensure_ascii=False), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------- stage A (offline)
def test_services_and_non_games_are_set_aside_and_penalised():
    svc = _cand("ホットペッパービューティー", [_row("moppy", "https://pc.moppy.jp/ad/detail.php?s_id=1", "ホットペッパービューティー 美容院予約完了後、予約店舗に来訪 3,300P", "review")], likely=False, hint=3300)
    out = tri.triage_offline(svc)
    assert out["bucket"] == "non_game_or_service" and out["verdict"] == "non_game_or_service" and out["scoreParts"]["serviceOrNonGame"] == -5


def test_a_name_without_game_words_is_unclassified_not_a_non_game():
    ambiguous = tri.triage_offline(_cand("Triple Tile", [_row("kurashiru_reward", "https://www.rewards.kurashiru.com/ads/20309", "Triple Tile", "review")], likely=False, hint=0))
    assert ambiguous["bucket"] == "unclassified" and ambiguous["gameStatus"] == "unconfirmed" and ambiguous["scoreParts"]["serviceOrNonGame"] == 0
    assert ambiguous["verdict"] == "offer_not_probed"


def test_unclassified_names_are_probed_only_after_the_likely_games(tmp_path):
    likely = [_cand(f"G{i}", [_row("moppy", f"https://pc.moppy.jp/ad/detail.php?s_id={i}", MOPPY_SINGLE[1])], order=i, hint=100) for i in range(1, 4)]
    unknown = _cand("Mystery Name", [_row("moppy", "https://pc.moppy.jp/ad/detail.php?s_id=99", "Mystery Name 新規登録 5,000P", "review")], order=0, likely=False, hint=5000)
    root = _write_candidates(tmp_path, [unknown] + likely)
    asked = []

    def fetch(url):
        asked.append(url)
        return 404, b""
    out = tri.build(DATE, root, True, 2, 12, fetch, 0, False)
    assert len(asked) == 2 and not any("s_id=99" in u for u in asked)
    assert [i["game"] for i in out["items"]][-1] == "Mystery Name" and out["unclassifiedCount"] == 1


def test_moppy_stepup_only_is_ranked_below_a_single_condition_game():
    stepup = tri.triage_offline(_cand("Coin Master", [_row("moppy", *MOPPY_STEPUP)], hint=6055))
    single = tri.triage_offline(_cand("Ball Sort", [_row("moppy", *MOPPY_SINGLE)], hint=700))
    assert stepup["paths"][0]["expectedReadable"] is False and stepup["scoreParts"]["noReadablePath"] == -3
    assert single["paths"][0]["expectedReadable"] is True
    assert single["score"] > stepup["score"]  # even with a nine times smaller listing amount


def test_reward_alone_does_not_decide_the_order():
    big_unreadable = tri.triage_offline(_cand("X", [_row("moppy", *MOPPY_STEPUP)], hint=123946))
    small_two_sites = tri.triage_offline(_cand("Y", [_row("coincome", *COINCOME_STEPUP), _row("moppy", *MOPPY_SINGLE)], hint=700))
    assert small_two_sites["score"] > big_unreadable["score"]


def test_multi_site_games_with_readable_pages_come_first():
    both = tri.triage_offline(_cand("Onet Master", [_row("coincome", *COINCOME_STEPUP), _row("warau", *WARAU_SKYFLAG)], hint=13950))
    warau_only = tri.triage_offline(_cand("Onet Master", [_row("warau", *WARAU_SKYFLAG)], hint=13791))
    assert both["scoreParts"]["multiSite"] == 2 and both["score"] > warau_only["score"]
    assert warau_only["paths"][0]["skyflagTagged"] and warau_only["scoreParts"]["skyflagOnly"] == -1


def test_previously_held_and_review_classification_are_penalised_not_dropped():
    held = tri.triage_offline(_cand("Z", [_row("moppy", *MOPPY_SINGLE)], previouslyHeld={"date": "2026-11-05", "reason": "x"}))
    assert held["scoreParts"]["previouslyHeld"] == -2 and held["bucket"] == "game_candidate"
    review = tri.triage_offline(_cand("W", [_row("moppy", *MOPPY_SINGLE, classification="review")], likely=False))
    assert review["scoreParts"]["reviewClassification"] == -1 and review["bucket"] == "game_candidate"


def test_long_listed_offers_outrank_fresh_ones_because_player_records_need_time():
    fresh = tri.triage_offline(_cand("N", [_row("moppy", *MOPPY_SINGLE)], listedDays=0))
    mid = tri.triage_offline(_cand("M", [_row("moppy", *MOPPY_SINGLE)], listedDays=7))
    old = tri.triage_offline(_cand("O", [_row("moppy", *MOPPY_SINGLE)], listedDays=45))
    unknown = tri.triage_offline(_cand("U", [_row("moppy", *MOPPY_SINGLE)]))
    assert [fresh["scoreParts"]["listedFor"], mid["scoreParts"]["listedFor"], old["scoreParts"]["listedFor"], unknown["scoreParts"]["listedFor"]] == [-1, 0, 2, 0]
    assert old["score"] > mid["score"] > fresh["score"]


def test_related_material_is_reusable_but_never_a_reason_to_skip():
    item = tri.triage_offline(_cand("R", [_row("moppy", *MOPPY_SINGLE)], relatedMaterial=[{"kind": "research_dossier", "ref": "x.json"}]))
    assert item["scoreParts"]["reusableMaterial"] == 1 and item["bucket"] == "game_candidate"


def test_offline_run_covers_every_candidate_and_does_no_network(tmp_path, monkeypatch):
    cands = [_cand(f"G{i}", [_row("moppy", f"https://pc.moppy.jp/ad/detail.php?s_id={i}", MOPPY_SINGLE[1])], order=i) for i in range(1, 61)]
    root = _write_candidates(tmp_path, cands)
    monkeypatch.setattr(tri.sources, "_default_fetch", lambda url: (_ for _ in ()).throw(AssertionError("stage A must not touch the network")))
    out = tri.build(DATE, root)
    assert out["candidateCount"] == 60 and len(out["items"]) == 60  # nothing is cut off at ~15
    assert out["stages"]["B"] == "not run" and out["budget"]["requests"] == 0
    assert [i["rank"] for i in out["items"]] == list(range(1, 61))


# ---------------------------------------------------------------- stage B (mocked network)
def _fetcher(pages, log):
    def fetch(url):
        log.append(url)
        return pages[url]
    return fetch


def _build(tmp_path, cands, pages, **kw):
    log = []
    out = tri.build(DATE, _write_candidates(tmp_path, cands), True, fetcher=_fetcher(pages, log), delay=0, **kw)
    return out, log


def test_probe_records_readable_pages_and_stops_at_the_first_one(tmp_path):
    cands = [_cand("Ball Sort", [_row("moppy", *MOPPY_SINGLE), _row("coincome", *COINCOME_STEPUP)])]
    pages = {MOPPY_SINGLE[0]: (200, _page("moppy_single_ball_sort_ios.html")), COINCOME_STEPUP[0]: (404, _page("coincome_stepup_onet.html"))}
    out, log = _build(tmp_path, cands, pages)
    item = out["items"][0]
    assert item["verdict"] == "offer_verified" and len(log) == 1  # one GET is enough to rank the game
    assert item["readableOffers"][0]["totalPt"] == 700 and item["probes"][0]["state"] == "readable"
    assert out["budget"]["requests"] == 1 and out["budget"]["verified"] == 1


def test_unreadable_pages_are_listed_by_state_never_as_ended(tmp_path):
    cands = [_cand("Onet Master", [_row("warau", *WARAU_SKYFLAG)])]
    pages = {WARAU_SKYFLAG[0]: (200, _page("warau_not_viewable.html"))}
    out, log = _build(tmp_path, cands, pages, lookup=False)
    item = out["items"][0]
    assert item["verdict"] == "offer_unreadable" and item["unreadableReasons"] == ["warau:not_viewable:page_not_viewable_publicly"]
    assert item["probes"][0]["totalPt"] is None


def test_failed_fetch_is_an_http_error_not_an_ended_offer(tmp_path):
    cands = [_cand("Ball Sort", [_row("moppy", *MOPPY_SINGLE)])]
    out, _ = _build(tmp_path, cands, {MOPPY_SINGLE[0]: (503, b"")}, lookup=False)
    item = out["items"][0]
    assert item["verdict"] == "offer_unreadable" and item["unreadableReasons"] == ["moppy:http_error:http_503"]


def test_amefuri_search_adds_pages_only_for_an_identical_name(tmp_path):
    cands = [_cand("Onet Master: Puzzle & Art", [_row("warau", *WARAU_SKYFLAG)])]
    search = tri.sources.amefuri_search_url("Onet Master: Puzzle & Art")
    pages = {WARAU_SKYFLAG[0]: (200, _page("warau_not_viewable.html")), search: (200, _page("amefuri_search_onet_master.html")),
             "https://www.amefri.net/detail/id/142696": (200, _page("amefuri_stepup_onet.html"))}
    out, log = _build(tmp_path, cands, pages)
    item = out["items"][0]
    assert [m["offerId"] for m in item["crossSite"]["matches"]] == ["142696"]
    assert [m["offerId"] for m in item["crossSite"]["possibleMatch"]] == ["139857"]  # "Onet Master: Tile Match Puzzle" is another app
    assert "https://www.amefri.net/detail/id/139857" not in log  # a similar name is never fetched, let alone adopted
    assert item["verdict"] == "offer_verified" and item["readableOffers"][0]["offerKey"] == "amefuri:142696"
    assert out["budget"]["requests"] == 3 and out["budget"]["lookups"] == 1


def test_a_failed_exact_match_page_never_falls_through_to_a_similar_name(tmp_path):
    cands = [_cand("Onet Master: Puzzle & Art", [_row("warau", *WARAU_SKYFLAG)])]
    search = tri.sources.amefuri_search_url("Onet Master: Puzzle & Art")
    pages = {WARAU_SKYFLAG[0]: (200, _page("warau_not_viewable.html")), search: (200, _page("amefuri_search_onet_master.html")),
             "https://www.amefri.net/detail/id/142696": (503, b""),
             "https://www.amefri.net/detail/id/139857": (200, _page("amefuri_stepup_onet.html"))}
    out, log = _build(tmp_path, cands, pages)
    assert "https://www.amefri.net/detail/id/139857" not in log
    assert out["items"][0]["verdict"] == "offer_unreadable"
    assert "amefuri:http_error:http_503" in out["items"][0]["unreadableReasons"]


def test_a_site_that_can_verify_the_offer_outranks_one_that_cannot_at_equal_reward():
    readable = tri.triage_offline(_cand("A", [_row("moppy", *MOPPY_SINGLE)], hint=700))
    uncertain = tri.triage_offline(_cand("B", [_row("warau", "https://www.warau.jp/contents/point/pointEntrance.php?point_id=7", "タイルマッチ3D（レベル300クリア） 初回アプリインストール後、レベル300クリア 700 pt")], hint=700))
    unreadable = tri.triage_offline(_cand("C", [_row("moppy", *MOPPY_STEPUP)], hint=700))
    assert readable["score"] > uncertain["score"] > unreadable["score"]


def test_no_amefuri_search_when_a_readable_page_exists_or_the_game_already_has_an_amefuri_page(tmp_path):
    cands = [_cand("Ball Sort", [_row("moppy", *MOPPY_SINGLE)])]
    out, log = _build(tmp_path, cands, {MOPPY_SINGLE[0]: (200, _page("moppy_single_ball_sort_ios.html"))})
    assert not out["items"][0]["crossSite"]["searched"] and len(log) == 1


def test_probe_limit_is_clamped_to_forty_and_stops_at_the_target(tmp_path):
    cands = [_cand(f"G{i}", [_row("moppy", f"https://pc.moppy.jp/ad/detail.php?s_id={1000 + i}", MOPPY_SINGLE[1])], order=i) for i in range(1, 80)]
    pages = {f"https://pc.moppy.jp/ad/detail.php?s_id={1000 + i}": (200, _page("moppy_single_ball_sort_ios.html")) for i in range(1, 80)}
    # every page here is the same fixture, so identity checks are not the point: only the budget is
    for url in list(pages):
        pages[url] = (200, _page("moppy_single_ball_sort_ios.html").replace(b"161455", url.rsplit("=", 1)[1].encode()))
    out, log = _build(tmp_path, cands, pages, probe_limit=500, target_verified=999)
    assert out["budget"]["probeLimit"] == tri.MAX_PROBE_LIMIT == 40 and out["budget"]["probed"] == 40 and len(log) == 40
    out2, log2 = _build(tmp_path / "b", cands, pages, probe_limit=40, target_verified=5) if (tmp_path / "b").mkdir() is None else (None, None)
    assert out2["budget"]["verified"] == 5 and len(log2) == 5  # stops once enough offers were verified


def test_request_cap_is_enforced_and_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(tri, "MAX_REQUESTS", 3)
    cands = [_cand(f"G{i}", [_row("warau", f"https://www.warau.jp/contents/point/pointEntrance.php?point_id={i}", WARAU_SKYFLAG[1])], order=i) for i in range(1, 11)]
    pages = {f"https://www.warau.jp/contents/point/pointEntrance.php?point_id={i}": (200, _page("warau_not_viewable.html")) for i in range(1, 11)}
    out, log = _build(tmp_path, cands, pages, lookup=False, probe_limit=40, target_verified=99)
    assert len(log) == 3 and out["budget"]["capHit"] is True and out["budget"]["requests"] == 3


def test_stale_candidates_produce_nothing_to_triage(tmp_path):
    root = tmp_path
    d = root / "research" / "daily-guides" / DATE
    d.mkdir(parents=True)
    (d / "candidates.json").write_text(json.dumps({"status": "stale_input", "candidates": []}), encoding="utf-8")
    assert tri.build(DATE, root)["items"] == []


def test_after_probing_games_whose_page_shows_user_reviews_come_first_among_verified(tmp_path):
    many = _cand("WithReviews", [_row("moppy", "https://pc.moppy.jp/ad/detail.php?s_id=2001", MOPPY_SINGLE[1])], order=2, hint=100)
    none = _cand("NoReviews", [_row("moppy", "https://pc.moppy.jp/ad/detail.php?s_id=2002", MOPPY_SINGLE[1])], order=1, hint=900000)
    page = _page("moppy_single_ball_sort_ios.html")
    pages = {"https://pc.moppy.jp/ad/detail.php?s_id=2001": (200, page.replace("（0件）".encode(), "（6件）".encode()).replace(b"161455", b"2001")),
             "https://pc.moppy.jp/ad/detail.php?s_id=2002": (200, page.replace(b"161455", b"2002"))}
    out, _ = _build(tmp_path, [many, none], pages, lookup=False)
    assert [i["game"] for i in out["items"]] == ["WithReviews", "NoReviews"]  # despite a 9000x smaller listing amount
    assert out["items"][0]["playerSignal"] == {"firstPartyReviewCount": 6} and out["items"][1]["playerSignal"] == {"firstPartyReviewCount": 0}
    # the signal is a count, not independent players: the verdict never claims an article is possible
    assert out["items"][0]["verdict"] == "offer_verified" and "identityCheckRequired" in out["items"][0]


def test_unreadable_candidates_rank_after_verified_ones_once_probed(tmp_path):
    bad = _cand("Bad", [_row("warau", *WARAU_SKYFLAG)], order=1, hint=999999)
    good = _cand("Good", [_row("moppy", *MOPPY_SINGLE)], order=2, hint=10)
    pages = {WARAU_SKYFLAG[0]: (200, _page("warau_not_viewable.html")), MOPPY_SINGLE[0]: (200, _page("moppy_single_ball_sort_ios.html"))}
    out, _ = _build(tmp_path, [bad, good], pages, lookup=False)
    assert [i["game"] for i in out["items"]] == ["Good", "Bad"]
