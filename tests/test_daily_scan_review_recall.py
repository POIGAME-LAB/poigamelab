from tests.test_daily_scan_review import candidates, scan


def test_two_site_review_classification_is_retained_for_research(monkeypatch):
    items = candidates("Quiet Kingdom")
    for item in items:
        item["classification"] = "review"
    result = scan(items, monkeypatch)
    assert result["twoSiteListingGroups"] == 1
    assert result["reviewedGroups"] == 1
    assert result["results"][0]["candidateEligible"] is True
    assert result["topFiveReviewCandidates"] == ["Quiet Kingdom"]


def test_explicit_non_game_classification_is_excluded(monkeypatch):
    items = candidates("Card Application")
    for item in items:
        item["classification"] = "likely_non_game"
    result = scan(items, monkeypatch)
    assert result["twoSiteListingGroups"] == 0
    assert result["reviewedGroups"] == 0
    assert result["topFiveReviewCandidates"] == []


def test_default_review_budget_was_expanded_for_reward_ranking():
    import daily_scan_review as daily
    assert daily.MAX_GROUPS == 300
    assert daily.MAX_DETAILS == 1200


def test_ambiguous_pointtown_reward_text_never_ranks_as_yen():
    import daily_scan_review as daily
    evidence = {
        "state": "parsed",
        "parserVersion": "pointtown-detail-review-v1",
        "verifiedCurrentRewardPoints": 160,
        "verifiedCurrentRewardYen": 160,
        "rewardUnit": "PointTown-point",
        "sourcePointRate": "1pt=1JPY",
        "headerText": "対象条件で 160 200 初回利用限定",
    }
    assert daily.explicit_yen(evidence) is None


def test_pointtown_reward_requires_exact_unit_contract():
    import daily_scan_review as daily
    evidence = {
        "state": "parsed",
        "parserVersion": "pointtown-detail-review-v1",
        "verifiedCurrentRewardPoints": 160,
        "verifiedCurrentRewardYen": 160,
        "rewardUnit": "PointTown-point",
        "sourcePointRate": "1pt=1JPY",
        "headerText": "対象条件で 160 初回利用限定",
    }
    assert daily.explicit_yen(evidence) == 160
    evidence["sourcePointRate"] = "unknown"
    assert daily.explicit_yen(evidence) is None


def test_transient_first_party_scan_failure_holds_ranking(monkeypatch):
    import daily_scan_review as daily
    result = scan(candidates("Quiet Kingdom"), monkeypatch)
    discovery = {
        "sourceResults": [
            {"source": "warau", "scanComplete": True, "catalogComplete": True},
            {"source": "amefuri", "scanComplete": False, "catalogComplete": False,
             "fetchErrors": 1},
        ]
    }
    out = daily.apply_discovery_completeness(result, discovery)
    assert out["rankingComplete"] is False
    assert out["sourceScanIncomplete"] is True
    assert out["incompleteDiscoverySources"] == ["amefuri"]
    assert "first_party_discovery_scan_incomplete" in out["rankingHoldReasons"]


def test_intentionally_partial_but_successful_surface_does_not_hold_ranking(monkeypatch):
    import daily_scan_review as daily
    result = scan(candidates("Quiet Kingdom"), monkeypatch)
    discovery = {
        "sourceResults": [
            {"source": "coincome", "scanComplete": True, "catalogComplete": False,
             "fetchErrors": 0},
            {"source": "warau", "scanComplete": True, "catalogComplete": True,
             "fetchErrors": 0},
        ]
    }
    out = daily.apply_discovery_completeness(result, discovery)
    assert out["rankingComplete"] is True
    assert out["sourceScanIncomplete"] is False
    assert out["incompleteDiscoverySources"] == []
    assert out["rankingScope"] == "supported_scanned_first_party_surfaces"


def test_explicit_bounded_powl_cap_is_visible_but_does_not_hold_ranking(monkeypatch):
    import daily_scan_review as daily
    result = scan(candidates("Quiet Kingdom"), monkeypatch)
    discovery = {
        "sourceResults": [
            {"source": "warau", "scanComplete": True, "catalogComplete": True,
             "fetchErrors": 0, "rankingCompletenessRequired": True},
            {"source": "powl", "scanComplete": False, "catalogComplete": False,
             "fetchErrors": 0, "candidateLimitReached": True,
             "contentGuardFailed": False, "rankingCompletenessRequired": False},
        ]
    }
    out = daily.apply_discovery_completeness(result, discovery)
    assert out["rankingComplete"] is True
    assert out["sourceScanIncomplete"] is False
    assert out["incompleteDiscoverySources"] == []
    assert out["expectedPartialDiscoverySources"] == ["powl"]
    assert "first_party_discovery_scan_incomplete" not in out["rankingHoldReasons"]


def test_optional_powl_still_holds_on_real_fetch_failure(monkeypatch):
    import daily_scan_review as daily
    result = scan(candidates("Quiet Kingdom"), monkeypatch)
    discovery = {
        "sourceResults": [
            {"source": "powl", "scanComplete": False, "catalogComplete": False,
             "fetchErrors": 1, "candidateLimitReached": True,
             "contentGuardFailed": False, "rankingCompletenessRequired": False},
        ]
    }
    out = daily.apply_discovery_completeness(result, discovery)
    assert out["rankingComplete"] is False
    assert out["sourceScanIncomplete"] is True
    assert out["incompleteDiscoverySources"] == ["powl"]
    assert out["expectedPartialDiscoverySources"] == []


def test_missing_discovery_summary_fails_closed(monkeypatch):
    import daily_scan_review as daily
    import pytest
    result = scan(candidates("Quiet Kingdom"), monkeypatch)
    with pytest.raises(ValueError, match="discovery_summary_missing"):
        daily.apply_discovery_completeness(result, None)
