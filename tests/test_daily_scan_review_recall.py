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
    assert daily.MAX_GROUPS == 30
    assert daily.MAX_DETAILS == 120
