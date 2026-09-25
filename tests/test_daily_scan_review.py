import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import daily_scan_review as daily


def sources():
    return {s: {"id": s, "search_domains": [f"{s}.example"],
                "direct_detail_url_hints": ["/detail"]} for s in ("a", "b", "c")}


def candidates(name="Example Puzzle", sites=("a", "b")):
    return [{"classification": "likely_game", "titleHint": name,
             "source": s, "firstPartyCandidateUrl": f"https://{s}.example/detail?id=1"} for s in sites]


def inspect(url, source, aliases, fetcher):
    fetcher(url, source)
    return {"url": url, "sourceEvidence": {"state": "parsed", "platform": "iOS",
            "parserVersion": "coincome-detail-review-v2", "displayedRewardYen": 2000,
            "termsText": "Full terms", "evidenceFingerprint": "fixture"}}


def scan(items, monkeypatch, inspector=inspect, registry=None, **kwargs):
    monkeypatch.setattr(daily.direct, "inspect_detail", inspector)
    return daily.review_scan(items=items, sources=registry or sources(), targets=[], rows=[],
                             checked_at="2026-09-14T16:17:00+00:00",
                             fetcher=lambda *args: ("fixture", args[0]), **kwargs)


def test_discovery_name_strips_coincome_listing_ui_suffix_only():
    assert daily.discovery_name(
        "iOS_戦国布武：我が天下戦国編【StepUp】 アプリ利用でキャッシュバック 8,650円 5,183円"
    ) == "戦国布武：我が天下戦国編【StepUp】"
    assert daily.discovery_name(
        "iOS_ATLAS:EARTH - お得なキャッシュバック！「StepUp」 アプリ利用でキャッシュバック 8,620円"
    ) == "ATLAS:EARTH - お得なキャッシュバック！「StepUp」"
    assert daily.discovery_name(
        "iOS_Cat Drop: Cute Slide & Match（30日以内にレベル400クリア） アプリ利用でキャッシュバック 160円"
    ) == "Cat Drop: Cute Slide & Match（30日以内にレベル400クリア）"


def test_discovery_name_strips_condition_prefix_without_stripping_branded_title():
    assert daily.discovery_name(
        "【60日間でいずれかのTier4隊員をアンロック】ザ・グランドマフィア"
    ) == "ザ・グランドマフィア"
    assert daily.discovery_name(
        "【85,000円以上を換金する】Freecash"
    ) == "Freecash"
    assert daily.discovery_name("【勝利の女神】NIKKE") == "【勝利の女神】NIKKE"


def test_single_verified_site_stays_discovery_only_and_does_not_spend_ranking_budget(monkeypatch):
    items = candidates(sites=("a",)) * 10
    result = scan(items, monkeypatch)
    assert result["listingGroups"] == 1
    assert result["singleSiteListingGroups"] == 1
    assert result["rankingEligibleGroups"] == 0
    assert result["reviewedGroups"] == result["detailInspectionCalls"] == 0
    assert result["twoSiteListingGroups"] == 0
    assert result["topFiveReviewCandidates"] == []
    assert result["rankingComplete"] is True


def test_same_domain_with_two_source_ids_is_not_two_sites(monkeypatch):
    registry = sources()
    registry["b"]["search_domains"] = ["a.example"]
    items = candidates()
    items[1]["firstPartyCandidateUrl"] = "https://a.example/detail?id=2"
    assert scan(items, monkeypatch, registry=registry)["twoSiteListingGroups"] == 0


def test_two_details_are_candidates_but_not_publication_permission(monkeypatch):
    result = scan(candidates(), monkeypatch)
    row = result["results"][0]
    assert row["candidateEligible"] and row["confirmedSourceCount"] == 2
    assert row["maxObservedRewardYen"] == 2000  # alternatives must not be summed
    assert row["publicationAuthorized"] is False
    assert row["researchStatus"] == "not_started"
    assert set(row["researchQueries"]) == {"web", "x", "instagram", "youtube", "point_site_reviews"}
    assert result["publishedGames"] == result["publicationWrites"] == result["apiCalls"] == 0


@pytest.mark.parametrize("failure", ["exception", "partial", "shell", "redirect", "missing_terms", "missing_os"])
def test_failed_or_ambiguous_second_source_is_retained_for_research(monkeypatch, failure):
    def changed(url, source, aliases, fetcher):
        value = inspect(url, source, aliases, fetcher)
        if source["id"] == "b":
            if failure == "exception":
                raise TimeoutError()
            if failure == "redirect":
                value["url"] = "https://unregistered.example/detail?id=1"
            if failure == "partial":
                value["sourceEvidence"]["state"] = "review_required"
            if failure == "shell":
                value["sourceEvidence"]["downstreamTermsRequired"] = True
            if failure == "missing_terms":
                value["sourceEvidence"]["termsText"] = ""
            if failure == "missing_os":
                value["sourceEvidence"]["platform"] = ""
        return value
    result = scan(candidates(), monkeypatch, inspector=changed)
    row = result["results"][0]
    assert row["listingSourceCount"] == 2
    assert row["verifiedRewardSourceCount"] >= 1
    assert row["candidateEligible"] is True
    assert row["publicationAuthorized"] is False
    assert "fewer_than_two_confirmed_sites" in row["holdReasons"]
    assert result["topFiveReviewCandidates"] == ["Example Puzzle"]


@pytest.mark.parametrize("value", [True, -1, 0, "2000", 1.5, None])
def test_noninteger_or_missing_amount_never_ranks(value):
    assert daily.explicit_yen({"state": "parsed", "parserVersion": "coincome-detail-review-v2",
                               "displayedRewardYen": value}) is None


def test_moppy_v3_verified_yen_can_rank_only_with_complete_first_party_terms():
    evidence = {
        "state": "parsed",
        "parserVersion": "moppy-detail-review-v3",
        "displayedRewardPoints": 3500,
        "verifiedCurrentRewardYen": 3500,
        "rewardUnit": "Moppy-P",
        "sourcePointRate": "1P=1JPY",
        "downstreamTermsRequired": False,
        "publicationAuthorized": False,
    }
    assert daily.explicit_yen(evidence) == 3500

    evidence["downstreamTermsRequired"] = True
    assert daily.explicit_yen(evidence) is None


@pytest.mark.parametrize("field,value", [
    ("displayedRewardPoints", 3499),
    ("verifiedCurrentRewardYen", "3500"),
    ("rewardUnit", "P"),
    ("sourcePointRate", "10P=1JPY"),
])
def test_moppy_v3_ranking_contract_fails_closed(field, value):
    evidence = {
        "state": "parsed",
        "parserVersion": "moppy-detail-review-v3",
        "displayedRewardPoints": 3500,
        "verifiedCurrentRewardYen": 3500,
        "rewardUnit": "Moppy-P",
        "sourcePointRate": "1P=1JPY",
        "downstreamTermsRequired": False,
    }
    evidence[field] = value
    assert daily.explicit_yen(evidence) is None


def test_powl_fractional_yen_contract_is_ranking_only():
    assert daily.explicit_yen({
        "state": "parsed",
        "parserVersion": "powl-detail-review-v1",
        "verifiedCurrentRewardYen": 28641.1,
        "publicationAuthorized": False,
    }) == 28641.1


def test_listing_reward_upper_bound_uses_max_explicit_value_and_fails_open():
    rates = {
        "powl": {"status": "verified", "yenPerPoint": 0.1},
        "unknown": {"status": "unsupported", "yenPerPoint": None},
    }
    assert daily.listing_reward_upper_bound_yen({
        "source": "powl",
        "titleHint": "Game（iOS） 条件28,000ポイント達成 34,000pt",
    }, registry=rates) == 3400
    assert daily.listing_reward_upper_bound_yen({
        "source": "unknown",
        "titleHint": "Game reward 12,345",
    }, registry=rates) is None


def test_points_are_not_assumed_to_be_yen():
    assert daily.explicit_yen({"state": "parsed", "parserVersion": "warau-stepup-v1",
                               "rewardPoints": 70000, "rewardUnit": "pt"}) is None


def test_top_five_are_ranked_by_yen_and_deduplicated(monkeypatch):
    items = sum((candidates(f"Puzzle {i}") for i in range(1, 8)), [])
    for item in items:
        item["firstPartyCandidateUrl"] = item["firstPartyCandidateUrl"].replace("id=1", "id=" + item["titleHint"].split()[-1])
    def priced(url, source, aliases, fetcher):
        value = inspect(url, source, aliases, fetcher)
        value["sourceEvidence"]["displayedRewardYen"] = int(aliases[0].split()[-1]) * 100
        return value
    result = scan(items + items, monkeypatch, inspector=priced)
    assert result["detailInspectionCalls"] == 14
    assert result["topFiveReviewCandidates"] == [f"Puzzle {i}" for i in (7, 6, 5, 4, 3)]


def test_one_offer_under_conflicting_titles_cannot_be_two_games(monkeypatch):
    result = scan(candidates("Puzzle One") + candidates("Puzzle Two"), monkeypatch)
    assert result["twoSiteListingGroups"] == 0


def test_explicit_review_only_source_is_available_without_enabling_publication(monkeypatch):
    registry = sources()
    registry["b"].update(scheduled_fetch_enabled=False, coverage_detail_review_enabled=True,
                         coverage_detail_review_mode="candidate_only")
    result = scan(candidates(), monkeypatch, registry=registry)
    assert result["results"][0]["candidateEligible"]
    assert not result["results"][0]["publicationAuthorized"]


def test_warau_conversion_requires_current_first_party_rate_and_is_fetched_once(monkeypatch):
    registry = sources()
    registry["warau"] = {"id": "warau", "search_domains": ["www.warau.jp"]}
    items = candidates(sites=("a",)) + [{"classification": "likely_game", "titleHint": "Example Puzzle",
        "source": "warau", "firstPartyCandidateUrl": "https://www.warau.jp/contents/point/pointEntrance.php?point_id=12"}]
    def parser(url, source, aliases, fetcher):
        value = inspect(url, source, aliases, fetcher)
        if source["id"] == "warau":
            value["sourceEvidence"].update(parserVersion="warau-stepup-v1", rewardUnit="pt", rewardPoints=3000)
        return value
    monkeypatch.setattr(daily.direct, "inspect_detail", parser)
    calls = []
    def fetch(url, source):
        calls.append(url)
        return "ワラウのポイント交換レートは原則として 1ポイント＝1円 です。", url
    result = daily.review_scan(items=items, sources=registry, targets=[], rows=[], checked_at="fixture", fetcher=fetch)
    assert result["results"][0]["maxObservedRewardYen"] == 3000
    assert calls.count("https://www.warau.jp/help/qa/128/") == 1
    assert result["warauBaseRate"]["confirmed"]
    assert daily.explicit_yen({"state": "parsed", "parserVersion": "warau-stepup-v1", "rewardUnit": "pt",
                               "rewardPoints": 3000}, warau_rate_confirmed=False) is None


def test_warau_rate_accepts_reviewed_first_party_help_redirect(monkeypatch):
    registry = sources()
    registry["warau"] = {"id": "warau", "search_domains": ["www.warau.jp"]}
    items = candidates(sites=("a",)) + [{
        "classification": "likely_game",
        "titleHint": "Example Puzzle",
        "source": "warau",
        "firstPartyCandidateUrl": "https://www.warau.jp/contents/point/pointEntrance.php?point_id=12",
    }]

    def parser(url, source, aliases, fetcher):
        value = inspect(url, source, aliases, fetcher)
        if source["id"] == "warau":
            value["sourceEvidence"].update(
                parserVersion="warau-stepup-v1",
                rewardUnit="pt",
                rewardPoints=3000,
            )
        return value

    monkeypatch.setattr(daily.direct, "inspect_detail", parser)

    def fetch(url, source):
        if url == "https://www.warau.jp/help/qa/128/":
            return (
                "ワラウのポイント交換レートは原則として 1ポイント＝1円 です。",
                "https://www.warau.jp/sp/help/detail/477/",
            )
        return "<p>Example Puzzle iOS 3000 pt</p>", url

    result = daily.review_scan(
        items=items,
        sources=registry,
        targets=[],
        rows=[],
        checked_at="fixture",
        fetcher=fetch,
    )
    assert result["warauBaseRate"]["confirmed"] is True
    assert result["results"][0]["maxObservedRewardYen"] == 3000


def test_detail_budget_is_explicit_and_partial_group_not_ranked(monkeypatch):
    result = scan(candidates(sites=("a", "b", "c")), monkeypatch, max_details=2)
    assert result["detailInspectionCalls"] == 2
    assert result["detailLimitReached"]
    assert result["topFiveReviewCandidates"] == []


def test_disabled_source_and_unsafe_urls_are_not_requested(monkeypatch):
    registry = sources()
    registry["b"]["scheduled_fetch_enabled"] = False
    result = scan(candidates(), monkeypatch, registry=registry)
    assert result["twoSiteListingGroups"] == 0
    assert result["singleSiteListingGroups"] == 1
    assert result["detailInspectionCalls"] == 0

    items = candidates()
    items[1]["firstPartyCandidateUrl"] = "https://user:pass@b.example/detail?id=1"
    result = scan(items, monkeypatch)
    assert result["twoSiteListingGroups"] == 0
    assert result["singleSiteListingGroups"] == 1
    assert result["detailInspectionCalls"] == 0


def setup_refresh(tmp_path, monkeypatch, count=7):
    spec = importlib.util.spec_from_file_location("isolated_daily_direct", ROOT / "scripts/direct_offer_refresh.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "data").mkdir()
    (tmp_path / "config").mkdir()
    for constant, path in {"ROOT": ".", "POLICY": "config/refresh_policy.json",
                           "TARGETS": "config/game_targets.json", "SOURCES": "config/point_sources.json",
                           "PUBLISHED": "data/published_offers.csv", "STATUS": "data/comparison_refresh_status.json",
                           "LEGACY_STATUS": "data/refresh_status.json", "REVIEW": "data/comparison_review_queue.json",
                           "NEW_GAME_QUEUE": "data/new_game_candidate_queue.json",
                           "NEW_GAME_HISTORY": "data/new_game_candidate_history.json",
                           "EXISTING_GAME_QUEUE": "data/existing_game_candidate_queue.json"}.items():
        setattr(module, constant, tmp_path / path)
    module.POLICY.write_text(json.dumps({"comparisonSources": ["a"], "games": {"Puzzle": {"enabled": True}}}))
    module.TARGETS.write_text(json.dumps({"games": [{"game": "Puzzle", "aliases": ["Puzzle"]}]}))
    module.SOURCES.write_text(json.dumps({"sources": list(sources().values())}))
    with module.PUBLISHED.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=module.FIELDS)
        writer.writeheader()
        for i in range(count):
            writer.writerow({"offerKey": str(i), "game": "Puzzle", "site": "b", "reward": "100",
                             "url": f"https://b.example/detail?id={i}", "verified": "true"})
    calls = []
    def fetch(url, source):
        calls.append(url)
        return "<p>Puzzle iOS 999 pt</p>", url
    monkeypatch.setattr(module, "fetch_first_party", fetch)
    return module, calls


def test_all_published_rows_and_sites_are_checked_and_old_values_preserved(tmp_path, monkeypatch):
    module, calls = setup_refresh(tmp_path, monkeypatch)
    original = module.PUBLISHED.read_bytes()
    assert module.main() == 0
    assert len(calls) == 7 and len(set(calls)) == 7
    assert module.PUBLISHED.read_bytes() == original


def test_hook_reuses_cache_for_success_and_failure(tmp_path, monkeypatch):
    module, calls = setup_refresh(tmp_path, monkeypatch, count=1)
    def consume(**kwargs):
        for _ in range(3):
            kwargs["fetcher"]("https://b.example/detail?id=0", sources()["b"])
    assert module.main(after_scan=consume) == 0
    assert len(calls) == 1
    calls.clear()
    def failure(url, source):
        calls.append(url)
        raise TimeoutError()
    monkeypatch.setattr(module, "fetch_first_party", failure)
    def consume_failure(**kwargs):
        for _ in range(3):
            with pytest.raises(TimeoutError):
                kwargs["fetcher"]("https://b.example/detail?id=0", sources()["b"])
    original = module.PUBLISHED.read_bytes()
    assert module.main(after_scan=consume_failure) == 0
    assert len(calls) == 1 and module.PUBLISHED.read_bytes() == original


def test_hook_failure_prevents_publication(tmp_path, monkeypatch):
    module, _ = setup_refresh(tmp_path, monkeypatch, count=1)
    original = module.PUBLISHED.read_bytes()
    def fail(**kwargs):
        raise ValueError("malformed review")
    with pytest.raises(ValueError):
        module.main(after_scan=fail)
    assert module.PUBLISHED.read_bytes() == original


def test_daily_workflow_has_no_paid_api_or_competing_automatic_adopter():
    workflow = (ROOT / ".github/workflows/refresh-verified-offers.yml").read_text()
    assert 'cron: "17 16 * * *"' in workflow
    assert "if: github.ref == 'refs/heads/main'" in workflow
    assert "python scripts/daily_scan_review.py" in workflow
    assert "API_KEY" not in workflow
    for name in ("adopt-high-reward-games.yml", "discover-trending-games.yml"):
        text = (ROOT / ".github/workflows" / name).read_text()
        triggers = text.split("permissions:")[0]
        assert "workflow_run:" not in triggers and "schedule:" not in triggers
    archive = workflow.index("- name: Archive refresh outputs")
    validation = workflow.index("- name: Build Pages artifact")
    commit = workflow.index("- name: Commit compact public outputs")
    assert validation < archive < commit
    assert "validate_daily_publication.py" in workflow[validation:archive]
    assert "git pull --rebase" not in workflow
    assert "git push origin HEAD:main" in workflow
    assert "data/daily_scan_review.json" in workflow[archive:commit]
    assert "git add data/daily_scan_review.json" not in workflow


def test_conservative_upper_bounds_skip_only_groups_that_cannot_reach_top_five(monkeypatch):
    registry = {
        "moppy": {"id": "moppy", "search_domains": ["moppy.example"],
                  "direct_detail_url_hints": ["/detail"]},
        "powl": {"id": "powl", "search_domains": ["powl.example"],
                 "direct_detail_url_hints": ["/detail"],
                 "scheduled_fetch_enabled": False,
                 "coverage_detail_review_enabled": True,
                 "coverage_detail_review_mode": "candidate_only"},
    }
    items = []
    for i in range(1, 11):
        items.extend([
            {"classification": "likely_game",
             "titleHint": f"Ceiling Puzzle {i:02d}（iOS） {i * 1000:,}P",
             "source": "moppy",
             "firstPartyCandidateUrl": f"https://moppy.example/detail?id={i}"},
            {"classification": "likely_game",
             "titleHint": f"Ceiling Puzzle {i:02d}（iOS） {i * 10000:,}pt",
             "source": "powl",
             "firstPartyCandidateUrl": f"https://powl.example/detail?id={i}"},
        ])

    def priced(url, source, aliases, fetcher):
        fetcher(url, source)
        amount = int(aliases[0].split()[-1]) * 1000
        return {"url": url, "sourceEvidence": {
            "state": "parsed", "platform": "iOS",
            "parserVersion": "coincome-detail-review-v2",
            "displayedRewardYen": amount,
            "termsText": "Full terms", "evidenceFingerprint": "fixture",
        }}

    result = scan(items, monkeypatch, inspector=priced, registry=registry)
    assert result["twoSiteListingGroups"] == 10
    assert result["topFiveReviewCandidates"] == [
        "Ceiling Puzzle 10", "Ceiling Puzzle 09", "Ceiling Puzzle 08",
        "Ceiling Puzzle 07", "Ceiling Puzzle 06",
    ]
    assert result["reviewedGroups"] == 5
    assert result["prefilterSkippedGroups"] == 5
    assert result["detailInspectionCalls"] == 10
    assert result["listingUpperBoundUnknownGroups"] == 0
    assert result["rankingComplete"] is True


def test_unknown_listing_bound_fails_open_and_is_reviewed(monkeypatch):
    registry = {
        "point_town": {"id": "point_town", "search_domains": ["point.example"],
                       "direct_detail_url_hints": ["/detail"]},
        "powl": {"id": "powl", "search_domains": ["powl.example"],
                 "direct_detail_url_hints": ["/detail"],
                 "scheduled_fetch_enabled": False,
                 "coverage_detail_review_enabled": True,
                 "coverage_detail_review_mode": "candidate_only"},
    }
    items = [
        {"classification": "likely_game", "titleHint": "Mystery Puzzle（iOS）",
         "source": "point_town", "firstPartyCandidateUrl": "https://point.example/detail?id=1"},
        {"classification": "likely_game", "titleHint": "Mystery Puzzle（iOS） 10pt",
         "source": "powl", "firstPartyCandidateUrl": "https://powl.example/detail?id=1"},
    ]
    result = scan(items, monkeypatch, registry=registry)
    assert result["listingUpperBoundUnknownGroups"] == 1
    assert result["reviewedGroups"] == 1
    assert result["detailInspectionCalls"] == 2
    assert result["prefilterSkippedGroups"] == 0


def test_default_budget_handles_more_than_thirty_two_site_groups(monkeypatch):
    items = []
    for i in range(31):
        for site in ("a", "b"):
            items.append({
                "classification": "likely_game",
                "titleHint": f"Budget Puzzle {i:02d}",
                "source": site,
                "firstPartyCandidateUrl": f"https://{site}.example/detail?id={i}",
            })
    result = scan(items, monkeypatch)
    assert daily.MAX_DETAILS == 768
    assert daily.MAX_GROUPS == 4096
    assert result["twoSiteListingGroups"] == 31
    assert result["rankingEligibleGroups"] == 31
    assert result["singleSiteListingGroups"] == 0
    assert result["reviewedGroups"] == 31
    assert result["detailInspectionCalls"] == 62
    assert result["groupLimitReached"] is False
    assert result["detailLimitReached"] is False
    assert result["rankingComplete"] is True


def _budget_surface(group_count):
    items = []
    for i in range(group_count):
        for site in ("a", "b"):
            items.append({
                "classification": "likely_game",
                "titleHint": f"Budget Ceiling Puzzle {i:03d}",
                "source": site,
                "firstPartyCandidateUrl": f"https://{site}.example/detail?id={i}",
            })
    return items


def test_default_budget_completes_121_two_site_groups_without_more_detail_budget(monkeypatch):
    result = scan(_budget_surface(121), monkeypatch)
    assert result["twoSiteListingGroups"] == 121
    assert result["reviewedGroups"] == 121
    assert result["detailInspectionCalls"] == 242
    assert result["groupLimitReached"] is False
    assert result["detailLimitReached"] is False
    assert result["rankingComplete"] is True


def test_default_budget_covers_observed_558_detail_surface(monkeypatch):
    result = scan(_budget_surface(279), monkeypatch)
    assert result["twoSiteListingGroups"] == 279
    assert result["reviewedGroups"] == 279
    assert result["detailInspectionCalls"] == 558
    assert result["groupLimitReached"] is False
    assert result["detailLimitReached"] is False
    assert result["rankingComplete"] is True


def test_many_single_site_groups_do_not_false_hold_two_site_handoff(monkeypatch):
    items = _budget_surface(158)
    for i in range(944):
        items.append({
            "classification": "likely_game",
            "titleHint": f"Single Site Candidate {i:04d}",
            "source": "a",
            "firstPartyCandidateUrl": f"https://a.example/detail?id=single-{i}",
        })
    result = scan(items, monkeypatch)
    assert result["listingGroups"] == 1102
    assert result["twoSiteListingGroups"] == 158
    assert result["singleSiteListingGroups"] == 944
    assert result["rankingEligibleGroups"] == 158
    assert result["reviewedGroups"] == 158
    assert result["groupLimitReached"] is False
    assert result["rankingComplete"] is True


def test_default_group_budget_no_longer_blocks_current_501_group_scale(monkeypatch):
    # 501 two-site groups require 1,002 details when every listing bound is
    # unknown, so the expensive-detail guard still fails closed first.
    result = scan(_budget_surface(501), monkeypatch)
    assert result["twoSiteListingGroups"] == 501
    assert result["groupLimitReached"] is False
    assert result["groupSafetyCap"] == 4096
    assert result["detailLimitReached"] is True
    assert result["rankingComplete"] is False
    assert result["detailInspectionCalls"] == 768


def test_group_safety_cap_remains_fail_closed_for_pathological_universe(monkeypatch):
    result = scan(_budget_surface(11), monkeypatch, max_groups=10)
    assert result["twoSiteListingGroups"] == 11
    assert result["reviewedGroups"] == 10
    assert result["detailInspectionCalls"] == 20
    assert result["groupSafetyCap"] == 10
    assert result["groupLimitReached"] is True
    assert result["rankingComplete"] is False


def test_default_budget_keeps_margin_above_observed_live_surface():
    # The 2026-09-24 live queue audit measured 667 detail offers across the
    # 158 groups that satisfy the downstream two-site handoff gate.
    assert daily.MAX_DETAILS >= 667
    assert daily.MAX_DETAILS == 768


def test_nightly_rate_policy_is_fail_closed_for_unknown_sources():
    assert daily.point_rate_policy("moppy")["yenPerPoint"] == 1
    assert daily.point_rate_policy("amefuri")["yenPerPoint"] == 0.1
    assert daily.point_rate_policy("kurashiru_reward")["yenPerPoint"] == 0.01
    assert daily.point_rate_policy("powl")["yenPerPoint"] == 0.1
    assert daily.point_rate_policy("powl")["status"] == "verified"
    assert daily.point_rate_policy("not-a-site")["status"] == "unsupported"


def test_one_strictly_verified_reward_source_can_rank(monkeypatch):
    def changed(url, source, aliases, fetcher):
        value = inspect(url, source, aliases, fetcher)
        if source["id"] == "b":
            raise TimeoutError()
        return value
    result = scan(candidates(), monkeypatch, inspector=changed)
    row = result["results"][0]
    assert row["verifiedRewardSourceCount"] == 1
    assert row["candidateEligible"] is True
    assert row["maxObservedRewardYen"] is not None

def test_zero_verified_reward_sources_never_rank(monkeypatch):
    def changed(url, source, aliases, fetcher):
        raise TimeoutError()
    result = scan(candidates(), monkeypatch, inspector=changed)
    row = result["results"][0]
    assert row["verifiedRewardSourceCount"] == 0
    assert row["candidateEligible"] is False
    assert row["maxObservedRewardYen"] is None
    assert "no_verified_reward_source" in row["holdReasons"]



def test_kurashiru_v2_listing_upper_bound_uses_verified_coin_rate():
    registry = {
        "kurashiru_reward": {
            "status": "verified",
            "yenPerPoint": 0.01,
        }
    }
    item = {
        "source": "kurashiru_reward",
        "titleHint": "パズル＆カオス",
        "listingRewardText": (
            "パズル＆カオス センターキャッスルレベル5到達で "
            "MAX 3,140,360 > 3,768,432 コイン"
        ),
    }
    assert daily.listing_reward_upper_bound_yen(item, registry=registry) == 37684.32


def test_kurashiru_v2_explicit_yen_requires_exact_coin_contract():
    evidence = {
        "state": "parsed",
        "parserVersion": "kurashiru-reward-detail-review-v2",
        "verifiedCurrentRewardCoins": 3768432,
        "verifiedCurrentRewardYen": 37684.32,
        "rewardUnit": "Kurashiru-coin",
        "sourcePointRate": "100coin=1JPY",
        "downstreamTermsRequired": False,
    }
    assert daily.explicit_yen(evidence) == 37684.32
    evidence["verifiedCurrentRewardYen"] = 37684.31
    assert daily.explicit_yen(evidence) is None



def test_mikoshi_verified_exchange_rate_joins_yen_ranking():
    source = {
        "id": "mikoshi",
        "search_domains": ["web.mikoshi.jp"],
        "direct_detail_url_hints": ["/v2/skyflag/ads/"],
        "scheduled_fetch_enabled": False,
        "coverage_detail_review_enabled": True,
        "coverage_detail_review_mode": "candidate_only",
    }
    assert daily.direct.source_participates_in_new_game_ranking(source) is True

    registry = {
        "mikoshi": {
            "status": "verified_face_value",
            "yenPerPoint": 1,
        }
    }
    item = {
        "source": "mikoshi",
        "titleHint": "Example Game",
        "listingRewardText": "451,871 MIKOSHIポイント",
    }
    assert daily.listing_reward_upper_bound_yen(item, registry=registry) == 451871

    evidence = {
        "state": "parsed",
        "parserVersion": "mikoshi-skyflag-detail-review-v3",
        "verifiedCurrentRewardPoints": 451871,
        "verifiedCurrentRewardYen": 451871,
        "rewardUnit": "MIKOSHI-point",
        "sourcePointRate": "1MIKOSHI-point=1JPY",
        "downstreamTermsRequired": False,
    }
    assert daily.explicit_yen(evidence) == 451871
    evidence["verifiedCurrentRewardYen"] = 406683.9
    assert daily.explicit_yen(evidence) is None

def test_trima_listing_upper_bound_uses_face_value_but_detail_uses_displayed_yen():
    registry = {
        "trima": {
            "status": "verified_face_value",
            "yenPerPoint": 0.01,
        }
    }
    item = {
        "source": "trima",
        "titleHint": "商品整理ゲーム：3Dパズル",
        "listingRewardText": "44,000 マイル",
    }
    assert daily.listing_reward_upper_bound_yen(item, registry=registry) == 440

    evidence = {
        "state": "parsed",
        "parserVersion": "trima-detail-review-v1",
        "displayedRewardMiles": 44000,
        "displayedRewardYen": 366,
        "verifiedCurrentRewardYen": 366,
        "rewardUnit": "Trima-mile",
        "sourcePointRate": "first-party-displayed-yen-equivalent-exchange-fee-included",
        "downstreamTermsRequired": False,
    }
    assert daily.explicit_yen(evidence) == 366



def test_nifty_live_diagnostic_20260925():
    """Temporary live diagnostic for Nifty Point Club app/game offer surfaces."""
    import json as _json
    import re as _re
    from html import unescape as _unescape
    from urllib.error import HTTPError as _HTTPError
    from urllib.parse import urljoin as _urljoin
    from urllib.request import Request as _Request, urlopen as _urlopen

    ua = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
        "Mobile/15E148 Safari/604.1"
    )

    def fetch(url, accept="text/html,application/xhtml+xml"):
        req = _Request(url, headers={
            "User-Agent": ua,
            "Accept": accept,
            "Accept-Language": "ja,en-US;q=0.8,en;q=0.5",
        })
        try:
            with _urlopen(req, timeout=20) as r:
                data = r.read(5_000_000)
                return {
                    "ok": True,
                    "status": getattr(r, "status", None),
                    "final": r.geturl(),
                    "contentType": r.headers.get("Content-Type"),
                    "text": data.decode("utf-8", "replace"),
                }
        except _HTTPError as exc:
            return {
                "ok": False,
                "status": exc.code,
                "error": "HTTPError",
                "text": exc.read(500_000).decode("utf-8", "replace"),
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": type(exc).__name__ + ":" + str(exc)[:180],
                "text": "",
            }

    urls = [
        "https://api.point.nifty.com/",
        "https://api.point.nifty.com/service/",
        "https://api.point.nifty.com/service/app/",
        "https://api.point.nifty.com/service/appli/",
        "https://api.point.nifty.com/app/",
        "https://api.point.nifty.com/apps/",
        "https://api.point.nifty.com/robots.txt",
        "https://api.point.nifty.com/sitemap.xml",
    ]
    pages = []
    scripts = []
    for url in urls:
        r = fetch(url)
        raw = r.get("text", "")
        hrefs = sorted(set(_re.findall(r'href=["\\\']([^"\\\']+)', raw)))
        srcs = sorted(set(_re.findall(r'<script[^>]+src=["\\\']([^"\\\']+)', raw)))
        scripts.extend(_urljoin(r.get("final") or url, x) for x in srcs)
        interesting_links = []
        for href in hrefs:
            absolute = _urljoin(r.get("final") or url, href)
            low = absolute.lower()
            if any(k in low for k in (
                "app", "appli", "game", "offer", "reward", "campaign",
                "service/detail", "skyflag", "smaad", "mychips"
            )):
                interesting_links.append(absolute)
        visible = _re.sub(r"(?is)<(?:script|style|noscript|svg)\\b[^>]*>.*?</(?:script|style|noscript|svg)>", " ", raw)
        visible = _re.sub(r"(?s)<[^>]+>", " ", visible)
        visible = _re.sub(r"\\s+", " ", _unescape(visible)).strip()
        pages.append({
            "url": url,
            "final": r.get("final"),
            "ok": r.get("ok"),
            "status": r.get("status"),
            "contentType": r.get("contentType"),
            "bytes": len(raw.encode("utf-8")),
            "interestingLinks": interesting_links[:120],
            "keywords": {k: (k in visible) for k in [
                "アプリで貯める", "アプリ", "ゲーム", "SKYFLAG", "SmaAD", "案件"
            ]},
            "excerpt": visible[:2200],
        })

    bundle_contexts = []
    seen = set()
    for su in scripts:
        if su in seen or len(bundle_contexts) >= 100:
            continue
        seen.add(su)
        if not any(host in su for host in ("point.nifty.com", "lifemedia.jp")):
            continue
        r = fetch(su, "*/*")
        body = r.get("text", "")
        for needle in (
            "アプリで貯める", "skyflag", "smaad", "offerwall", "/api/",
            "service/detail", "application", "app/", "campaign"
        ):
            start = 0
            while len(bundle_contexts) < 100:
                pos = body.lower().find(needle.lower(), start)
                if pos < 0:
                    break
                bundle_contexts.append({
                    "script": su,
                    "needle": needle,
                    "context": body[max(0, pos-650):pos+1600],
                })
                start = pos + len(needle)

    assert False, "NIFTY_LIVE_DIAGNOSTIC=" + _json.dumps({
        "pages": pages,
        "scriptCount": len(set(scripts)),
        "bundleContexts": bundle_contexts,
    }, ensure_ascii=False, sort_keys=True)
