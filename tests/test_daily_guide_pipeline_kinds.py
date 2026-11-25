"""End-to-end gate (manuscript -> gate -> spec -> render validation) for non-Warau and single-condition offers.

A synthetic, clearly fictional package ("サンプルパズル（テスト用）") is built around evidence parsed from the real
page fixtures. Nothing is written to the repository: ``check_batch`` only reads the package. The quality bars the
routine promised to keep - at least three player records, two independent current players, nothing older than 5
years and nothing older than 1 year unless its condition is today's condition, readable offer evidence only - are asserted here so that supporting new offer shapes cannot loosen them.
"""
import copy
import json
import re
from pathlib import Path

import pytest

from scripts import build_daily_guides as bdg
from scripts import guide_offer_sources as src

FIX = Path(__file__).resolve().parent / "fixtures" / "offer_pages"
DATE = "2026-11-19"
SLUG = "sample-puzzle"
GAME = "サンプルパズル（テスト用）"
OFFER_SOURCE = "M1"


def _evidence(site, offer_id, name):
    ev = src.parse_offer_page(site, offer_id, (FIX / name).read_text(encoding="utf-8"))
    ev["retrievedAt"] = f"{DATE}T00:30:00+00:00"
    ev["httpStatus"] = 200
    return ev


def _players(posted=("2026-10-03", "2026-10-21", "2026-11-02"), authors=("筆者A", "筆者B", "筆者C")):
    out = []
    for i, (when, author) in enumerate(zip(posted, authors)):
        url = f"https://blog{i}.example.com/entry/{i}"
        out.append({"id": "ABC"[i], "label": f"プレイヤー{'ABC'[i]}", "status": "completed", "summary": f"{10 + i}日目に条件達成",
                    "milestones": [{"day": 10 + i, "label": "条件達成"}], "sources": [url],
                    "sourceDetails": [author, when, "記録"], "postedOn": when, "checkedAt": DATE})
    return out


def _filler(n=70):
    return "".join(f"検証用の説明文{i}：この段落はテスト用に条件、期限、反映時期、撤退の目安をそれぞれ別の言い回しで確認します。" for i in range(n))


def _article(ev, extra=""):
    unit = ev["pointUnit"]
    rows = "\n".join(f"| {s['condition']} | {s.get('deadlineDays') or ev['deadlineDays']}日以内 | {s['rewardPt']:,}{unit} | なし |" for s in ev["steps"])
    sections = {
        "condition": f"## 案件条件と報酬\n\n{ev['siteLabel']}の案件ページを直接取得しました。[M1]\n\n| 条件 | 期限 | 報酬 | 課金 |\n| --- | ---: | ---: | --- |\n{rows}\n\n{extra}\n\n合計は{ev['totalPt']:,}{unit}です。[M1]",
        "pace": "## 実際の到達ペース\n\nA・B・Cの記録を並べます。[M2][M3][M4]\n\n| プレイヤー | 到達日数 |\n| --- | ---: |\n| A | 10日 |\n| B | 11日 |\n| C | 12日 |",
        "outlook": "## 難易度と見通し\n\n実例では10〜12日でした。個人差があります。[M2]",
        "early": "## 序盤\n\n" + _filler(8) + "[M2]",
        "middle": "## 中盤\n\n" + _filler(8) + "[M3]",
        "late": "## 終盤\n\n" + _filler(8) + "[M4]",
        "stop": "## 課金の損得と撤退ライン\n\n課金は任意です。" + _filler(8) + "[M2]",
        "tracking": "## ポイント反映の注意\n\n" + _filler(8) + "[M1]",
        "faq": "## よくある質問\n\n### 何日かかりますか\n\n実例では10〜12日です。[M2]",
    }
    toc = [("condition", "案件条件と報酬"), ("pace", "実際の到達ペース"), ("outlook", "難易度と見通し"), ("early", "序盤"), ("middle", "中盤"),
           ("late", "終盤"), ("stop", "課金の損得と撤退ライン"), ("tracking", "ポイント反映の注意"), ("faq", "よくある質問"), ("sources", "出典")]
    title = "サンプルパズル ポイ活攻略｜条件と到達日数の実例（テスト用）"
    lines = [f"# {title}", "", f"{GAME}は、テスト用に作った架空のパズルゲームです。案件条件と実例を確認します。[M1][M2][M3]", "",
             f"実例では10〜12日で条件に届いています。到達を保証するものではありません。[M2][M4]", "", "## 目次", ""]
    lines += [f"{i}. [{label}](#{sid})" for i, (sid, label) in enumerate(toc, 1)] + [""]
    for sid, _ in toc[:-1]:
        lines += [f'<a id="{sid}"></a>', sections[sid], ""]
    lines += ['<a id="sources"></a>', "## 出典", "", f"- [M1：{ev['siteLabel']}の案件ページ]({ev['url']})",
              "- [M2：プレイ記録A](https://blog0.example.com/entry/0)", "- [M3：プレイ記録B](https://blog1.example.com/entry/1)",
              "- [M4：プレイ記録C](https://blog2.example.com/entry/2)", "", "出典の確認日はいずれも2026年11月19日です。"]
    return title, "\n".join(lines) + "\n" + _filler(40)


def _pays(step):
    return bool(re.search(r"購入|課金|パック|パス", step["condition"]))


def _write(tmp_path, ev, *, players=None, extra="", mutate=None):
    batch = tmp_path / "research" / "daily-guides" / DATE
    pkg = batch / SLUG
    (batch / "evidence").mkdir(parents=True)
    pkg.mkdir(parents=True)
    title, article = _article(ev, extra)
    (pkg / "article.md").write_text(article, encoding="utf-8")
    offer = {"offerKey": ev["offerKey"], "site": ev["site"], "kind": ev["kind"], "os": ev["os"], "url": ev["url"],
             "steps": [{"condition": s["condition"], "rewardPt": s["rewardPt"], "deadlineDays": s.get("deadlineDays") or ev["deadlineDays"], "requiresPayment": _pays(s)}
                       for s in ev["steps"]],
             "totalDisplayedPt": ev["totalPt"], "temporaryIncrease": ev.get("temporaryIncrease"), "sumWithoutPurchaseStepsPt": sum(s["rewardPt"] for s in ev["steps"] if not _pays(s))}
    meta = {"slug": SLUG, "game": GAME, "seoTitle": title, "metaDescription": "サンプルパズル（テスト用）の案件条件と、実例の到達日数を整理した検証用のページです。ゲートの動作確認に使います。",
            "proposedPage": f"{SLUG}-guide.html", "canonical": f"https://poigamelab.com/{SLUG}-guide.html", "status": "manuscript_complete", "offers": [offer]}
    sources = [{"id": "M1", "title": "案件ページ", "url": ev["url"], "type": "point_site", "checkedAt": DATE},
               *[{"id": f"M{i + 2}", "title": f"記録{'ABC'[i]}", "url": f"https://blog{i}.example.com/entry/{i}", "type": "blog", "checkedAt": DATE} for i in range(3)]]
    (pkg / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (pkg / "sources.json").write_text(json.dumps({"sources": sources}, ensure_ascii=False), encoding="utf-8")
    (pkg / "experiences.json").write_text(json.dumps({"schemaVersion": 1, "game": GAME, "updatedAt": DATE, "title": "実プレイヤーの記録", "intro": "公開記録", "notice": "個人差", "footnote": "検証用",
                                                       "players": players if players is not None else _players()}, ensure_ascii=False), encoding="utf-8")
    (pkg / "page.json").write_text(json.dumps({"heroStats": [{"label": "期限", "value": "30日"}], "offerLinks": [{"label": "案件ページ", "url": ev["url"]}],
                                               "registry": {"label": "攻略を読む →", "description": "検証用の説明です。"}, "related": []}, ensure_ascii=False), encoding="utf-8")
    evidence = {"checkedAtJst": f"{DATE}T09:30:00+09:00", "checks": [ev]}
    (batch / "evidence" / f"{SLUG}-offers.json").write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    if mutate:
        mutate(batch, pkg)
    return batch


def _check(batch):
    return bdg.check_batch(batch)[SLUG]


# ---------------------------------------------------------------- positive: new offer shapes pass end to end
def test_single_condition_moppy_offer_with_unknown_os_passes_end_to_end(tmp_path):
    ev = _evidence("moppy", "160625", "moppy_single_tile_triple.html")
    assert ev["kind"] == "single" and ev["os"] is None
    batch = _write(tmp_path, ev, extra="ページにOSの記載はありません。")
    assert _check(batch) == []


def test_single_condition_coincome_offer_passes_with_boost_disclosure(tmp_path):
    ev = _evidence("coincome", "10850", "coincome_single_yuusha.html")
    batch = _write(tmp_path, ev, extra="現在は増額中で、増額の終了日はページに記載がありません。")
    assert _check(batch) == []


def test_amefuri_stepup_offer_passes_with_rate_and_boost_disclosure(tmp_path):
    ev = _evidence("amefuri", "142696", "amefuri_stepup_onet.html")
    extra = "アメフリは10ptが1円です（合計13,779円）。現在は増額中で、増額の終了日はページに記載がありません。"
    batch = _write(tmp_path, ev, extra=extra)
    assert _check(batch) == []


def test_stepup_with_per_step_deadlines_passes_when_each_step_carries_its_own_number(tmp_path):
    ev = _evidence("amefuri", "142379", "amefuri_stepup_per_step_deadlines.html")
    assert ev["deadlineDays"] is None and {s["deadlineDays"] for s in ev["steps"]} == {1, 5, 20, 30}
    inc = ev["temporaryIncrease"]
    extra = "アメフリは10ptが1円です（合計6,602円）。" + ("現在は増額中で、増額の終了日はページに記載がありません。" if inc else "")
    assert _check(_write(tmp_path, ev, extra=extra)) == []


def test_a_step_deadline_that_differs_from_the_page_is_refused(tmp_path):
    ev = _evidence("amefuri", "142379", "amefuri_stepup_per_step_deadlines.html")
    extra = "アメフリは10ptが1円です（合計6,602円）。" + ("現在は増額中で、増額の終了日はページに記載がありません。" if ev["temporaryIncrease"] else "")

    def mutate(batch, pkg):
        meta = json.loads((pkg / "metadata.json").read_text(encoding="utf-8"))
        # the one-day step is written up as a 30-day step: the page says 1 day
        meta["offers"][0]["steps"] = [dict(s, deadlineDays=30) if s["deadlineDays"] == 1 else s for s in meta["offers"][0]["steps"]]
        (pkg / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    errs = _check(_write(tmp_path, ev, extra=extra, mutate=mutate))
    assert any(e.startswith("step_deadline_differs_from_evidence") for e in errs), errs


# ---------------------------------------------------------------- the promised quality bars are unchanged
def test_a_missing_disclosure_fails_the_whole_package(tmp_path):
    ev = _evidence("moppy", "160625", "moppy_single_tile_triple.html")
    assert any(e.startswith("os_not_stated_on_page_but_not_disclosed") for e in _check(_write(tmp_path, ev)))


def test_unreadable_offer_evidence_fails_the_package(tmp_path):
    ev = _evidence("moppy", "161557", "moppy_stepup_coin_master.html")
    assert ev["state"] == "steps_not_public"
    batch = _write(tmp_path, copy.deepcopy(ev) | {"steps": [{"condition": "x", "rewardPt": 1, "rewardYen": 1}], "deadlineDays": 30, "pointUnit": "P"})
    assert any(e.startswith("offer_not_live_in_evidence") for e in _check(batch))


@pytest.mark.parametrize("players,expected", [
    (_players()[:2], "experience_needs_3_players"),
    (_players(authors=("同じ人", "同じ人", "同じ人")), "needs_2_independent_current_players"),
    (_players(posted=("2025-01-03", "2025-02-21", "2025-03-02")), "old_player_record_needs_recordCondition"),
    (_players(posted=("2021-01-03", "2021-02-21", "2021-03-02")), "player_record_older_than_5_years"),
])
def test_player_record_bars_are_not_loosened(tmp_path, players, expected):
    ev = _evidence("moppy", "160625", "moppy_single_tile_triple.html")
    errs = _check(_write(tmp_path, ev, players=players, extra="ページにOSの記載はありません。"))
    assert any(e.startswith(expected) for e in errs), errs


def test_more_than_five_articles_in_one_day_is_still_refused(tmp_path):
    ev = _evidence("moppy", "160625", "moppy_single_tile_triple.html")
    batch = _write(tmp_path, ev, extra="ページにOSの記載はありません。")
    for i in range(6):
        d = batch / f"extra-{i}"
        d.mkdir()
        (d / "metadata.json").write_text(json.dumps({"status": "manuscript_complete"}), encoding="utf-8")
    assert any(e.startswith("more_than_5_articles_in_one_day") for e in bdg.check_batch(batch)["_batch"])


# ---------------------------------------------------------------- 5-year rule (operator decision 2026-11-26)
def _old_players(condition, unchanged=True):
    players = _players(posted=("2023-05-03", "2024-02-21", "2025-03-02"))
    for p in players:
        p["recordCondition"] = condition
        p["conditionUnchanged"] = unchanged
    return players


def _player_errors(errs):
    return [e for e in errs if "player" in e]


def test_old_records_count_when_they_reached_todays_condition(tmp_path):
    ev = _evidence("moppy", "160625", "moppy_single_tile_triple.html")
    condition = ev["steps"][0]["condition"]
    errs = _check(_write(tmp_path, ev, players=_old_players(condition), extra="ページにOSの記載はありません。"))
    assert _player_errors(errs) == [], errs


def test_old_records_with_a_different_condition_are_not_counted(tmp_path):
    ev = _evidence("moppy", "160625", "moppy_single_tile_triple.html")
    errs = _check(_write(tmp_path, ev, players=_old_players("レベル999に到達（旧条件）"), extra="ページにOSの記載はありません。"))
    assert any(e.startswith("old_player_record_condition_differs_from_current_offer") for e in errs), errs
    assert "needs_2_independent_current_players" in errs


def test_old_records_need_an_explicit_unchanged_check(tmp_path):
    ev = _evidence("moppy", "160625", "moppy_single_tile_triple.html")
    condition = ev["steps"][0]["condition"]
    errs = _check(_write(tmp_path, ev, players=_old_players(condition, unchanged=False), extra="ページにOSの記載はありません。"))
    assert any(e.startswith("old_player_record_needs_conditionUnchanged") for e in errs), errs
