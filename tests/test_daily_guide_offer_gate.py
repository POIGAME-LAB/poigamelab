"""Daily gate: offer table vs same-day evidence for Amefuri / COINCOME / Moppy offers and single-condition offers.

``build_daily_guides.offer_table_errors`` is fed evidence produced by the real adapters from the page fixtures, so the
gate is exercised on exactly the records the routine will write. Positive cases prove a faithful table passes;
negative cases prove each rule rejects the tampering it exists for (units, OS, kind, boost disclosure, deadline).
"""
import copy
from pathlib import Path

import pytest

from scripts import build_daily_guides as bdg
from scripts import guide_offer_sources as src

FIX = Path(__file__).resolve().parent / "fixtures" / "offer_pages"
DATE = "2026-11-19"


def _ev(site, offer_id, name):
    ev = src.parse_offer_page(site, offer_id, (FIX / name).read_text(encoding="utf-8"))
    assert ev["state"] == "readable", ev
    return ev


def _evidence(*checks, when=DATE):
    return {"checkedAtJst": f"{when}T09:30:00+09:00", "checks": list(checks)}


def _offer(ev, *, payment=lambda cond: False):
    """Metadata offer table row for an evidence record (what the routine writes into metadata.json)."""
    steps = [{"condition": s["condition"], "rewardPt": s["rewardPt"], "deadlineDays": ev["deadlineDays"],
              "requiresPayment": payment(s["condition"])} for s in ev["steps"]]
    return {"offerKey": ev["offerKey"], "site": ev["site"], "kind": ev["kind"], "os": ev["os"], "url": ev["url"],
            "steps": steps, "totalDisplayedPt": ev["totalPt"],
            "sumWithoutPurchaseStepsPt": sum(s["rewardPt"] for s in steps if not s["requiresPayment"])}


def _errors(offers, ev, article, *, page_links=None, previous=None, when=DATE, recheck=False):
    meta = {"offers": offers, "previousOffers": previous or []}
    page = {"offerLinks": [{"url": o["url"]} for o in offers] if page_links is None else page_links}
    cited = {o["url"] for o in offers}
    return bdg.offer_table_errors(meta, page, ev, article, cited, DATE, when, recheck)


# articles contain exactly the strings a faithful manuscript carries
MOPPY_ARTICLE = ("条件：新規アプリインストール後、30日以内にレベル300クリア。報酬は700P。ページにOSの記載はありません。")
AMEFURI_ARTICLE = ("アメフリは10ptが1円です。合計137,790pt（13,779円）。" + "".join(f"{s}pt " for s in (
    "50", "50", "50", "200", "410", "630", "950", "1,280", "1,600", "1,920", "5,140", "19,310", "41,830", "64,370")) +
    "現在は増額中ですが、増額の終了日はページに記載がありません。")


# ---------------------------------------------------------------- single-condition offers
def test_single_condition_moppy_offer_passes_with_its_own_unit():
    ev = _ev("moppy", "161455", "moppy_single_ball_sort_ios.html")  # OS stated in the title
    assert _errors([_offer(ev)], _evidence(ev), "条件：レベル300クリア。報酬は700P。") == []


def test_single_condition_page_without_os_requires_the_disclosure():
    ev = _ev("moppy", "160625", "moppy_single_tile_triple.html")
    assert ev["os"] is None
    article = "条件：レベル1100を完成。報酬は2,375P。"
    assert any(e.startswith("os_not_stated_on_page_but_not_disclosed") for e in _errors([_offer(ev)], _evidence(ev), article))
    assert _errors([_offer(ev)], _evidence(ev), article + "ページにOSの記載はありません。") == []
    wrong = _offer(ev)
    wrong["os"] = "iOS"  # claiming an OS the page never stated
    assert any(e.startswith("offer_os_mismatch") for e in _errors([wrong], _evidence(ev), article + "OSの記載"))


def test_single_offer_must_be_exactly_one_condition():
    ev = _ev("moppy", "161455", "moppy_single_ball_sort_ios.html")
    offer = _offer(ev)
    offer["steps"] = offer["steps"] * 2
    offer["totalDisplayedPt"] *= 2
    offer["sumWithoutPurchaseStepsPt"] *= 2
    errs = _errors([offer], _evidence(ev), "700P")
    assert any(e.startswith("single_offer_must_have_exactly_one_condition") for e in errs)


def test_a_stepup_table_cannot_be_declared_for_a_single_offer_or_the_reverse():
    single = _ev("moppy", "161455", "moppy_single_ball_sort_ios.html")
    offer = _offer(single)
    offer["kind"] = "stepup"
    assert any(e.startswith("offer_kind_mismatch") for e in _errors([offer], _evidence(single), "700P"))
    stepup = _ev("amefuri", "142696", "amefuri_stepup_onet.html")
    offer = _offer(stepup)
    offer["kind"] = "single"
    assert any(e.startswith("offer_kind_mismatch") for e in _errors([offer], _evidence(stepup), AMEFURI_ARTICLE))


def test_amount_must_be_written_in_the_sites_own_unit():
    ev = _ev("moppy", "161455", "moppy_single_ball_sort_ios.html")
    errs = _errors([_offer(ev)], _evidence(ev), "条件：レベル300クリア。報酬は700pt。")  # Moppy points are "P", not "pt"
    assert any(e.startswith("step_reward_not_in_article") for e in errs) and any(e.startswith("offer_total_not_in_article") for e in errs)
    ev = _ev("coincome", "10850", "coincome_single_yuusha.html")
    boost = "現在は増額中で、増額の終了日はページに記載がありません。"  # COINCOME shows a boosted amount (base 200 -> 340)
    assert _errors([_offer(ev)], _evidence(ev), "ステージ40クリアで340円。" + boost) == []
    assert _errors([_offer(ev)], _evidence(ev), "ステージ40クリアで340pt。" + boost)  # COINCOME shows yen, not points


def test_deadline_in_the_table_must_equal_the_page():
    ev = _ev("moppy", "161455", "moppy_single_ball_sort_ios.html")
    offer = _offer(ev)
    offer["steps"][0]["deadlineDays"] = 60
    assert any(e.startswith("step_deadline_differs_from_evidence") for e in _errors([offer], _evidence(ev), "700P"))
    offer["steps"][0]["deadlineDays"] = None
    assert any(e.startswith("step_deadline_missing") for e in _errors([offer], _evidence(ev), "700P"))


# ---------------------------------------------------------------- Amefuri StepUp (10pt = 1 yen, boosted, no end date)
def test_amefuri_stepup_passes_with_rate_yen_total_and_boost_disclosure():
    ev = _ev("amefuri", "142696", "amefuri_stepup_onet.html")
    assert _errors([_offer(ev)], _evidence(ev), AMEFURI_ARTICLE) == []


@pytest.mark.parametrize("remove,expected", [
    ("13,779円", "yen_equivalent_not_in_article"),
    ("アメフリは10ptが1円です。", "point_rate_not_disclosed"),
    ("現在は増額中ですが、増額の終了日はページに記載がありません。", "temporary_increase_not_disclosed"),
    ("137,790pt（", "offer_total_not_in_article"),
    ("64,370pt ", "step_reward_not_in_article"),
])
def test_amefuri_stepup_rejects_each_missing_disclosure(remove, expected):
    ev = _ev("amefuri", "142696", "amefuri_stepup_onet.html")
    article = AMEFURI_ARTICLE.replace(remove, "")
    assert any(e.startswith(expected) for e in _errors([_offer(ev)], _evidence(ev), article)), expected


def test_boost_without_an_end_date_must_not_be_presented_as_permanent():
    ev = _ev("amefuri", "142696", "amefuri_stepup_onet.html")
    article = AMEFURI_ARTICLE.replace("増額", "アップ")
    assert any(e.startswith("temporary_increase_not_disclosed") for e in _errors([_offer(ev)], _evidence(ev), article))


def test_boost_with_a_stated_end_date_needs_that_date():
    ev = _ev("amefuri", "142696", "amefuri_stepup_onet.html")
    ev = copy.deepcopy(ev)
    ev["temporaryIncrease"] = {"regularYen": 8407, "increasedYen": 13779, "until": "2026年12月1日", "endDateStated": True}
    assert any(e.startswith("temporary_increase_not_disclosed") for e in _errors([_offer(ev)], _evidence(ev), AMEFURI_ARTICLE))
    assert _errors([_offer(ev)], _evidence(ev), AMEFURI_ARTICLE + "2026年12月1日まで。") == []


def test_rate_must_be_verified_on_the_page_for_non_warau_sites():
    ev = copy.deepcopy(_ev("amefuri", "142696", "amefuri_stepup_onet.html"))
    ev["rateVerified"] = False
    assert any(e.startswith("point_rate_not_verified_on_page") for e in _errors([_offer(ev)], _evidence(ev), AMEFURI_ARTICLE))


# ---------------------------------------------------------------- unreadable evidence can never pass
@pytest.mark.parametrize("site,oid,name", [("moppy", "161557", "moppy_stepup_coin_master.html")])
def test_steps_not_public_evidence_cannot_back_a_table(site, oid, name):
    ev = src.parse_offer_page(site, oid, (FIX / name).read_text(encoding="utf-8"))
    assert ev["state"] == "steps_not_public"
    offer = {"offerKey": ev["offerKey"], "site": site, "kind": "stepup", "os": ev["os"], "url": ev["url"], "steps": [],
             "totalDisplayedPt": 6055, "sumWithoutPurchaseStepsPt": 0}
    assert any(e.startswith("offer_not_live_in_evidence") for e in _errors([offer], _evidence(ev), "6,055P"))


def test_warau_not_viewable_evidence_cannot_back_a_table():
    ev = src.parse_offer_page("warau", "209332", (FIX / "warau_not_viewable.html").read_text(encoding="utf-8"))
    offer = {"offerKey": "warau:209332", "pointId": "209332", "os": "iOS", "url": ev["url"], "steps": [], "totalDisplayedPt": 1, "sumWithoutPurchaseStepsPt": 0}
    assert any(e.startswith("offer_not_live_in_evidence:209332") for e in _errors([offer], _evidence(ev), "1pt"))


def test_offer_missing_from_evidence_is_rejected():
    ev = _ev("moppy", "161455", "moppy_single_ball_sort_ios.html")
    other = _ev("coincome", "10850", "coincome_single_yuusha.html")
    assert any(e.startswith("offer_not_live_in_evidence") for e in _errors([_offer(ev)], _evidence(other), "700P"))


def test_evidence_must_come_from_the_batch_date():
    ev = _ev("moppy", "161455", "moppy_single_ball_sort_ios.html")
    errs = _errors([_offer(ev)], _evidence(ev, when="2026-11-18"), "700P", when="2026-11-18")
    assert "offer_evidence_not_from_batch_date" in errs


def test_two_sites_for_one_game_are_checked_independently():
    amefuri = _ev("amefuri", "142696", "amefuri_stepup_onet.html")
    coincome = _ev("coincome", "10842", "coincome_stepup_onet.html")
    article = AMEFURI_ARTICLE + "COINCOME 13,950円 " + "".join(f"{s['rewardPt']:,}円 " for s in coincome["steps"]) + "増額中 終了日"
    ev = _evidence(amefuri, coincome)
    assert _errors([_offer(amefuri), _offer(coincome)], ev, article) == []
    tampered = _offer(coincome)
    tampered["steps"][3]["rewardPt"] += 1
    errs = _errors([_offer(amefuri), tampered], ev, article)
    assert any(e.startswith("offer_steps_differ_from_evidence:coincome:10842") for e in errs)


# ---------------------------------------------------------------- legacy Warau entries keep their old behaviour
def test_legacy_warau_evidence_and_metadata_still_use_point_ids():
    legacy_check = {"pointId": "209342", "live": True, "os": "iOS", "steps": [{"condition": "レベル3到達", "rewardPt": 100}],
                    "totalPt": 100, "stepSumMatchesTotal": True, "httpStatus": 200}
    offer = {"pointId": "209342", "os": "iOS", "url": "https://www.warau.jp/x", "totalDisplayedPt": 100, "sumWithoutPurchaseStepsPt": 100,
             "steps": [{"condition": "レベル3到達", "rewardPt": 100, "deadlineDays": 10, "requiresPayment": False}]}
    meta = {"offers": [offer]}
    errs = bdg.offer_table_errors(meta, {"offerLinks": [{"url": offer["url"]}]}, _evidence(legacy_check), "100pt", {offer["url"]}, DATE, DATE, False)
    assert errs == []
    assert bdg.offer_key(offer) == "warau:209342" and bdg.offer_label(offer) == "209342"
