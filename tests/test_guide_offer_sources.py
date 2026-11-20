"""Offer-page adapters for the daily guide routine (Warau / Amefuri / COINCOME / Moppy), no network.

Fixtures in tests/fixtures/offer_pages/ are the essential regions of real public pages fetched on 2026-11-19
(scripts, styles and navigation removed, markup otherwise untouched). The tests pin the rules that decide whether
an offer may back an article table: every state explicit, units never mixed, an unreadable page never read as
"ended" / "0 pt", single-condition offers represented as one condition with one reward.
"""
from pathlib import Path

import pytest

from scripts import guide_offer_sources as src

FIX = Path(__file__).resolve().parent / "fixtures" / "offer_pages"


def _page(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _parse(site, offer_id, name, **kw):
    return src.parse_offer_page(site, offer_id, _page(name), **kw)


# ---------------------------------------------------------------- URL registry
@pytest.mark.parametrize("url,expected", [
    ("https://www.amefri.net/detail/id/142696", ("amefuri", "142696")),
    ("https://amefri.net/detail/id/1", ("amefuri", "1")),
    ("https://cimcome.jp/campaigns/details/10842", ("coincome", "10842")),
    ("https://pc.moppy.jp/ad/detail.php?s_id=160625&track_ref=category", ("moppy", "160625")),
    ("https://pc.moppy.jp/ad/detail.php?site_id=160625", ("moppy", "160625")),
    ("https://www.warau.jp/contents/point/pointEntrance.php?point_id=209342&pl=pc_categoryService", ("warau", "209342")),
])
def test_registered_offer_urls_are_recognised(url, expected):
    assert src.site_and_offer_id(url) == expected


@pytest.mark.parametrize("url", [
    "http://www.amefri.net/detail/id/142696",              # not https
    "https://evil.example.com/detail/id/142696",           # not a registered host
    "https://www.amefri.net.evil.example/detail/id/1",     # look-alike host
    "https://user:pw@www.amefri.net/detail/id/1",          # credentials in the URL
    "https://www.amefri.net/item_list?word=x",             # a listing, not an offer
    "https://pc.moppy.jp/ad/detail.php",                   # no id
    "ftp://cimcome.jp/campaigns/details/1", "", None,
])
def test_unregistered_or_malformed_urls_are_refused(url):
    assert src.site_and_offer_id(url) is None
    with pytest.raises(ValueError):
        src.record(url, fetcher=lambda u: (_ for _ in ()).throw(AssertionError("no request may be made")))


# ---------------------------------------------------------------- Amefuri (10pt = 1 yen)
def test_amefuri_stepup_reads_every_step_and_converts_at_the_printed_rate():
    ev = _parse("amefuri", "142696", "amefuri_stepup_onet.html")
    assert ev["state"] == "readable" and ev["live"] and ev["kind"] == "stepup" and ev["os"] == "iOS"
    assert ev["gameName"] == "Onet Master: Puzzle & Art"
    assert ev["pointUnit"] == "pt" and ev["yenPerPoint"] == 0.1 and ev["rateVerified"]
    assert len(ev["steps"]) == 14 and ev["steps"][0] == {"condition": "レベル5クリア", "rewardPt": 50, "rewardYen": 5, "deadlineDays": 30}
    assert ev["steps"][-1] == {"condition": "レベル20000クリア", "rewardPt": 64370, "rewardYen": 6437, "deadlineDays": 30}
    assert ev["totalPt"] == 137790 and ev["totalYen"] == 13779 and ev["stepSumMatchesTotal"]
    assert ev["deadlineDays"] == 30 and ev["deadlineBasis"] == "install"
    # "Ptアップ": a boosted amount is recorded as temporary; the page states no end date and none is invented
    assert ev["temporaryIncrease"] == {"regularYen": 8407, "increasedYen": 13779, "until": None, "endDateStated": False}


def test_amefuri_single_condition_is_one_condition_one_reward_and_ignores_the_label_legend():
    ev = _parse("amefuri", "140250", "amefuri_single_boku.html")
    # the fixture ends with the page's label legend, which lists "多段階" for every reader; it must not make this a StepUp
    assert "labelArea__item--stepup" in _page("amefuri_single_boku.html")
    assert ev["state"] == "readable" and ev["kind"] == "single" and ev["os"] == "iOS"
    assert ev["steps"] == [{"condition": "レベル40到達", "rewardPt": 9840, "rewardYen": 984, "deadlineDays": 30}]
    assert ev["totalPt"] == 9840 and ev["totalYen"] == 984 and ev["deadlineDays"] == 30 and ev["deadlineBasis"] == "click"
    assert ev["temporaryIncrease"]["regularYen"] == 600 and ev["temporaryIncrease"]["increasedYen"] == 984


def test_amefuri_without_the_printed_rate_is_not_converted():
    raw = _page("amefuri_stepup_onet.html").replace("10pt＝1円", "").replace("10pt=1円", "")
    ev = src.parse_offer_page("amefuri", "142696", raw)
    assert ev["state"] == "parse_failed" and ev["unavailableReason"] == "rate_not_verified" and not ev["live"]


def test_amefuri_step_sum_that_differs_from_the_displayed_total_is_not_readable():
    raw = _page("amefuri_stepup_onet.html").replace("64,370", "64,380")
    ev = src.parse_offer_page("amefuri", "142696", raw)
    assert ev["state"] == "parse_failed" and ev["unavailableReason"] == "step_sum_differs_from_displayed_total"


def test_amefuri_canonical_of_another_offer_is_an_identity_mismatch():
    ev = src.parse_offer_page("amefuri", "999", _page("amefuri_stepup_onet.html"))
    assert ev["state"] == "identity_mismatch" and not ev["live"]


# ---------------------------------------------------------------- COINCOME (yen shown directly; live pages arrive with HTTP 404)
def test_coincome_stepup_sums_to_the_current_displayed_amount():
    ev = _parse("coincome", "10842", "coincome_stepup_onet.html")
    assert ev["state"] == "readable" and ev["kind"] == "stepup" and ev["os"] == "iOS"
    assert ev["pointUnit"] == "円" and ev["yenPerPoint"] == 1
    assert len(ev["steps"]) == 14 and ev["totalYen"] == 13950 and ev["stepSumMatchesTotal"]
    assert ev["deadlineDays"] == 30
    assert ev["temporaryIncrease"] == {"regularYen": 8403, "increasedYen": 13950, "until": None, "endDateStated": False}


def test_coincome_single_condition():
    ev = _parse("coincome", "10850", "coincome_single_yuusha.html")
    assert ev["state"] == "readable" and ev["kind"] == "single" and ev["os"] == "iOS"
    assert ev["steps"] == [{"condition": "ノーマルのステージ40クリア", "rewardPt": 340, "rewardYen": 340, "deadlineDays": 30}]
    assert ev["deadlineDays"] == 30


def test_coincome_error_page_is_not_found_not_zero_yen():
    ev = _parse("coincome", "9782", "coincome_notfound.html")
    assert ev["state"] == "not_found" and not ev["live"] and ev["totalYen"] is None and ev["steps"] == []


def test_coincome_live_page_with_http_404_is_read_by_its_body():
    body = _page("coincome_single_yuusha.html").encode()
    ev = src.record("https://cimcome.jp/campaigns/details/10850", fetcher=lambda u: (404, body))
    assert ev["httpStatus"] == 404 and ev["state"] == "readable" and ev["kind"] == "single"


# ---------------------------------------------------------------- Moppy (1P = 1 yen; StepUp steps are not public)
def test_moppy_single_condition_with_os_in_the_title():
    ev = _parse("moppy", "161455", "moppy_single_ball_sort_ios.html")
    assert ev["state"] == "readable" and ev["kind"] == "single" and ev["os"] == "iOS" and ev["osSource"] == "title"
    assert ev["pointUnit"] == "P" and ev["yenPerPoint"] == 1
    assert ev["steps"] == [{"condition": "新規アプリインストール後、30日以内にレベル300クリアで条件達成となります。", "rewardPt": 700, "rewardYen": 700, "deadlineDays": 30}]
    assert ev["deadlineDays"] == 30


def test_moppy_page_that_does_not_state_the_os_keeps_os_unknown():
    ev = _parse("moppy", "160625", "moppy_single_tile_triple.html")
    assert ev["state"] == "readable" and ev["os"] is None and ev["osSource"] is None  # never guessed
    assert ev["totalPt"] == 2375 and ev["deadlineDays"] == 30 and ev["deadlineBasis"] == "click"
    assert "レベル1100を完成" in ev["conditionText"]


@pytest.mark.parametrize("name,oid,reward,days,fragment", [
    ("moppy_single_rok.html", "162444", 11400, 15, "任意のレベルIV部隊をアンロック"),
    ("moppy_single_screw_bullets.html", "162245", 1300, 30, "レベル500到達"),
])
def test_moppy_single_condition_formats(name, oid, reward, days, fragment):
    ev = _parse("moppy", oid, name)
    assert ev["state"] == "readable" and ev["kind"] == "single"
    assert ev["totalPt"] == reward and ev["deadlineDays"] == days and fragment in ev["conditionText"]


def test_moppy_stepup_without_public_steps_can_never_back_a_table():
    ev = _parse("moppy", "161557", "moppy_stepup_coin_master.html")
    assert ev["kind"] == "stepup" and ev["state"] == "steps_not_public" and ev["live"] is False
    assert ev["steps"] == [] and not ev["stepSumMatchesTotal"]
    assert ev["unavailableReason"] == "stepup_steps_behind_point_get_page"
    assert src.ARTICLE_READY_STATES == ("readable",)


def test_moppy_page_without_a_printed_yen_rate_is_not_converted():
    raw = _page("moppy_single_ball_sort_ios.html").replace("1P＝1円", "").replace("1P=1円", "")
    ev = src.parse_offer_page("moppy", "161455", raw)
    assert ev["state"] == "parse_failed" and ev["unavailableReason"] == "rate_not_verified"


# ---------------------------------------------------------------- Warau
def test_warau_single_condition_header():
    ev = _parse("warau", "209379", "warau_single_tile_match.html")
    assert ev["state"] == "readable" and ev["kind"] == "single" and ev["os"] == "iOS"
    assert ev["steps"] == [{"condition": "レベル300クリア", "rewardPt": 320, "rewardYen": 320}]
    assert ev["deadlineDays"] == 14 and ev["gameName"] == "タイルマッチ3D：トリプルマスター"


def test_warau_not_viewable_page_is_neither_ended_nor_zero():
    ev = _parse("warau", "209332", "warau_not_viewable.html")
    assert ev["state"] == "not_viewable" and ev["unavailableReason"] == "page_not_viewable_publicly"
    assert ev["live"] is False and ev["totalPt"] is None and ev["steps"] == []


# ---------------------------------------------------------------- HTTP handling: the status alone never decides
@pytest.mark.parametrize("code,state", [(0, "http_error"), (403, "http_error"), (429, "http_error"), (500, "http_error"), (503, "http_error")])
def test_transport_failures_are_http_errors_not_ended(code, state):
    ev = src.record("https://www.amefri.net/detail/id/142696", fetcher=lambda u: (code, b""))
    assert ev["state"] == state and ev["live"] is False and ev["totalPt"] is None
    assert ev["unavailableReason"] == f"http_{code}"


def test_short_404_on_a_non_coincome_site_is_not_found():
    ev = src.record("https://pc.moppy.jp/ad/detail.php?s_id=1", fetcher=lambda u: (404, b"<html>not found</html>"))
    assert ev["state"] == "not_found" and ev["live"] is False


def test_record_stamps_retrieval_time_and_hash():
    body = _page("moppy_single_tile_triple.html").encode()
    ev = src.record("https://pc.moppy.jp/ad/detail.php?site_id=160625", fetcher=lambda u: (200, body))
    assert ev["offerKey"] == "moppy:160625" and len(ev["responseSha256"]) == 64 and ev["retrievedAt"].endswith("+00:00")


# ---------------------------------------------------------------- Amefuri name search (cross-site lookup)
def test_amefuri_search_lists_same_named_but_different_apps_separately():
    rows = src.parse_amefuri_search(_page("amefuri_search_onet_master.html"))
    assert [(r["offerId"], r["gameName"]) for r in rows] == [
        ("142696", "Onet Master: Puzzle & Art"), ("139857", "Onet Master: Tile Match Puzzle")]
    assert src.amefuri_search_url("Onet Master") == "https://www.amefri.net/item_list?word=Onet%20Master"


def test_amefuri_search_failure_returns_nothing():
    assert src.lookup_amefuri("x", fetcher=lambda u: (503, b"")) == []


@pytest.mark.parametrize("title,expected", [
    ("iOS_Onet Master: Puzzle & Art『StepUp』", "Onet Master: Puzzle & Art"),
    ("Onet Master: Puzzle &amp;amp; Art（多段階）【iOS】", "Onet Master: Puzzle & Art"),
    ("Ball Sort Puzzle：ボールソーティングパズル(レベル300クリア)_iOS", "Ball Sort Puzzle：ボールソーティングパズル"),
    ("ボクと惑星農園（レベル40到達）（iOS）", "ボクと惑星農園"),
    ("LINE：ジグソーパズル", "LINE：ジグソーパズル"),
])
def test_clean_game_name(title, expected):
    assert src.clean_game_name(title) == expected


# ---------------------------------------------------------------- evidence CLI (--url mode, network mocked)
def _cli(monkeypatch, tmp_path, pages, extra_args=()):
    import json

    from scripts import daily_guide_evidence as evid

    monkeypatch.setattr(evid, "ROOT", tmp_path)
    monkeypatch.setattr(evid.time, "sleep", lambda s: None)
    monkeypatch.setattr(src, "_default_fetch", lambda url: pages[url])
    code = evid.main(["--date", "2026-11-19", "--slug", "demo", *extra_args])
    out = json.loads((tmp_path / "research" / "daily-guides" / "2026-11-19" / "evidence" / "demo-offers.json").read_text(encoding="utf-8"))
    return code, out


def test_cli_url_mode_records_each_site_with_its_own_unit(monkeypatch, tmp_path):
    pages = {"https://www.amefri.net/detail/id/142696": (200, _page("amefuri_stepup_onet.html").encode()),
             "https://cimcome.jp/campaigns/details/10842": (404, _page("coincome_stepup_onet.html").encode())}
    code, out = _cli(monkeypatch, tmp_path, pages, [a for u in pages for a in ("--url", u)])
    assert code == 0 and out["schemaVersion"] == 2 and out["site"] == "multi" and out["sites"] == ["amefuri", "coincome"]
    by = {c["offerKey"]: c for c in out["checks"]}
    assert by["amefuri:142696"]["pointUnit"] == "pt" and by["amefuri:142696"]["totalYen"] == 13779
    assert by["coincome:10842"]["pointUnit"] == "円" and by["coincome:10842"]["totalYen"] == 13950  # a different amount: never merged
    assert all(c["state"] == "readable" and c["live"] and c["responseSha256"] for c in out["checks"])


def test_cli_exit_code_is_nonzero_when_any_offer_is_not_readable(monkeypatch, tmp_path):
    pages = {"https://pc.moppy.jp/ad/detail.php?s_id=161557": (200, _page("moppy_stepup_coin_master.html").encode()),
             "https://pc.moppy.jp/ad/detail.php?s_id=161455": (200, _page("moppy_single_ball_sort_ios.html").encode())}
    code, out = _cli(monkeypatch, tmp_path, pages, [a for u in pages for a in ("--url", u)])
    assert code == 2
    states = {c["offerKey"]: c["state"] for c in out["checks"]}
    assert states == {"moppy:161557": "steps_not_public", "moppy:161455": "readable"}


def test_cli_requires_an_offer_to_record(monkeypatch, tmp_path):
    from scripts import daily_guide_evidence as evid

    with pytest.raises(SystemExit):
        evid.main(["--date", "2026-11-19", "--slug", "demo"])


# ---------------------------------------------------------------- Moppy review count (a signal, never a player count)
def test_moppy_review_count_is_read_from_the_page_tab():
    assert _parse("moppy", "161455", "moppy_single_ball_sort_ios.html")["reviewCount"] == 0
    raw = _page("moppy_single_ball_sort_ios.html").replace("（0件）", "（7件）")
    ev = src.parse_offer_page("moppy", "161455", raw)
    assert ev["reviewCount"] == 7 and ev["state"] == "readable"
    assert "review" not in " ".join(ev["termNotes"]) if ev.get("termNotes") else True  # review text is never stored


def test_moppy_page_without_the_review_tab_has_unknown_review_count():
    raw = _page("moppy_single_ball_sort_ios.html").replace("クチコミ", "xx")
    assert src.parse_offer_page("moppy", "161455", raw)["reviewCount"] is None


# ---------------------------------------------------------------- deadlines: every wording seen on real pages
def test_moppy_deadline_counted_from_mission_participation():
    ev = _parse("moppy", "159535", "moppy_single_mission60.html")
    assert ev["state"] == "readable" and ev["kind"] == "single"
    assert ev["deadlineDays"] == 60 and ev["deadlineBasis"] == "mission"
    assert [s["deadlineDays"] for s in ev["steps"]] == [60]


def test_moppy_deadline_counted_from_click():
    ev = _parse("moppy", "160405", "moppy_single_click7.html")
    assert ev["state"] == "readable" and ev["deadlineDays"] == 7 and ev["deadlineBasis"] == "click"


def test_amefuri_mission_deadline_of_60_days():
    ev = _parse("amefuri", "128434", "amefuri_mission60.html")
    assert ev["state"] == "readable" and ev["deadlineDays"] == 60 and ev["deadlineBasis"] == "mission"


def test_amefuri_one_day_deadline_is_kept_as_one_day():
    ev = _parse("amefuri", "142151", "amefuri_single_click1.html")
    assert ev["state"] == "readable" and ev["kind"] == "single" and ev["deadlineDays"] == 1


def test_amefuri_global_deadline_applies_to_every_step():
    ev = _parse("amefuri", "142430", "amefuri_stepup_global_click.html")
    assert ev["state"] == "readable" and ev["deadlineDays"] == 30
    assert {s["deadlineDays"] for s in ev["steps"]} == {30}


def test_amefuri_per_step_deadlines_are_read_from_each_step():
    ev = _parse("amefuri", "142379", "amefuri_stepup_per_step_deadlines.html")
    assert ev["state"] == "readable" and ev["kind"] == "stepup" and len(ev["steps"]) == 24
    by_condition = {s["condition"]: s["deadlineDays"] for s in ev["steps"]}
    assert by_condition["1日以内に村レベル20をクリア"] == 1
    assert by_condition["5日以内に村レベル45をクリア"] == 5
    assert by_condition["20日以内に村レベル150をクリア"] == 20
    assert by_condition["村レベル2をクリア"] == 30
    assert ev["deadlineDays"] is None                      # steps differ, so there is no single offer-level number
    assert sum(s["rewardPt"] for s in ev["steps"]) == ev["totalPt"] == 66020 and ev["totalYen"] == 6602


def test_conflicting_deadline_numbers_make_the_page_unreadable_not_guessed():
    html = _page("amefuri_single_click1.html")
    assert "成果受付期限　　：広告クリックから1日以内" in html
    # the page's own condition block now states 1 day in one place and 7 days in another
    html = html.replace("成果受付期限　　：広告クリックから1日以内", "成果受付期限　　：広告クリックから1日以内<br />\n成果受付期限　　：広告クリックから7日以内", 1)
    ev = src.parse_offer_page("amefuri", "142151", html)
    assert ev["state"] == "parse_failed" and ev["unavailableReason"] == "deadline_ambiguous"


def test_page_without_any_deadline_is_not_readable():
    html = _page("amefuri_single_click1.html")
    import re
    html = re.sub(r"\d+日以内", "", html)
    ev = src.parse_offer_page("amefuri", "142151", html)
    assert ev["state"] == "parse_failed"


def test_read_deadlines_rejects_two_numbers_for_one_condition():
    steps = [{"condition": "村レベル20をクリア", "rewardPt": 10}]
    text = "・5日以内に村レベル20をクリア\n・9日以内に村レベル20をクリア"
    assert src.read_deadlines(text, steps)["state"] == "ambiguous"


# ---------------------------------------------------------------- Warau: increase WITHOUT a printed end date (PR #353 audit)
def test_warau_increase_without_an_end_date_is_recorded_not_dropped():
    """2026-11-20 official page: ``<del>1,700pt</del> →最大 2,000pt`` with no "○年○月○日まで". The old detector required the
    date and therefore recorded ``temporaryIncrease: None`` ("no increase") for point_id 178209 / 178210."""
    ev = _parse("warau", "178209", "warau_stepup_undated_increase.html")
    assert ev["state"] == "readable" and ev["kind"] == "stepup" and ev["os"] == "iOS"
    assert ev["totalPt"] == 2000 and [s["rewardPt"] for s in ev["steps"]] == [50, 120, 270, 1560]
    assert ev["temporaryIncrease"] == {"regularPt": 1700, "increasedPt": 2000, "until": None, "endDateStated": False}


def test_warau_increase_with_a_printed_end_date_keeps_that_date():
    unit = '<span class="entrance-ptItem_PtInfo-unit">pt</span>'
    raw = _page("warau_stepup_undated_increase.html")
    assert raw.count(unit) >= 1
    dated = raw.replace(unit, unit + "<span> 2026年12月01日まで</span>", 1)
    assert src.parse_offer_page("warau", "178209", dated)["temporaryIncrease"] == {
        "regularPt": 1700, "increasedPt": 2000, "until": "2026年12月01日"}


def test_warau_page_without_a_price_change_has_no_increase():
    raw = _page("warau_stepup_undated_increase.html")
    raw = raw.replace("<del>1,700pt</del>", "").replace("→", "").replace('<span class="entrance-ptItem_PtInfo-max">最大</span>', "")
    assert src.parse_offer_page("warau", "178209", raw)["temporaryIncrease"] is None


def test_another_offers_price_change_in_the_recommendation_list_is_not_this_offers_increase():
    raw = _page("warau_stepup_undated_increase.html")
    raw = raw.replace("<del>1,700pt</del>", "").replace("→", "").replace('<span class="entrance-ptItem_PtInfo-max">最大</span>', "")
    other = "<div>こんな広告もおすすめ</div><div>別ゲーム（StepUp）</div><div>3,000pt</div><div> →</div><div>最大</div><div>3,500</div><div>pt</div>"
    assert src.parse_offer_page("warau", "178209", raw + other)["temporaryIncrease"] is None


def test_warau_single_condition_page_with_a_price_change_is_not_read_as_plain():
    """Fail closed: a single-condition page that shows a price change must not become a plain 'one condition, one reward'."""
    raw = _page("warau_single_tile_match.html")
    plain = '<span class="entrance-ptItem_PtInfo-point">320</span><span class="entrance-ptItem_PtInfo-unit">pt</span>'
    assert plain in raw
    changed = raw.replace(plain, '<del>200pt</del> →<span class="entrance-ptItem_PtInfo-max">最大</span>' + plain, 1)
    ev = src.parse_offer_page("warau", "209300", changed)
    assert ev["state"] == "parse_failed" and ev["unavailableReason"] == "offer_structure_not_found"
