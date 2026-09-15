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
            "parserVersion": "coincome-detail-review-v1", "displayedRewardYen": 2000,
            "termsText": "Full terms", "evidenceFingerprint": "fixture"}}


def scan(items, monkeypatch, inspector=inspect, registry=None, **kwargs):
    monkeypatch.setattr(daily.direct, "inspect_detail", inspector)
    return daily.review_scan(items=items, sources=registry or sources(), targets=[], rows=[],
                             checked_at="2026-09-14T16:17:00+00:00",
                             fetcher=lambda *args: ("fixture", args[0]), **kwargs)


def test_single_site_never_qualifies_even_with_many_urls(monkeypatch):
    items = candidates(sites=("a",)) * 10
    result = scan(items, monkeypatch)
    assert result["reviewedGroups"] == result["detailInspectionCalls"] == 0
    assert result["topFiveReviewCandidates"] == []


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
def test_failed_or_ambiguous_second_source_is_held(monkeypatch, failure):
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
    assert not result["results"][0]["candidateEligible"]
    assert result["topFiveReviewCandidates"] == []


@pytest.mark.parametrize("value", [True, -1, 0, "2000", 1.5, None])
def test_noninteger_or_missing_amount_never_ranks(value):
    assert daily.explicit_yen({"state": "parsed", "parserVersion": "coincome-detail-review-v1",
                               "displayedRewardYen": value}) is None


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


def test_detail_budget_is_explicit_and_partial_group_not_ranked(monkeypatch):
    result = scan(candidates(sites=("a", "b", "c")), monkeypatch, max_details=2)
    assert result["detailInspectionCalls"] == 2
    assert result["detailLimitReached"]
    assert result["topFiveReviewCandidates"] == []


def test_disabled_source_and_unsafe_urls_are_not_requested(monkeypatch):
    registry = sources()
    registry["b"]["scheduled_fetch_enabled"] = False
    assert scan(candidates(), monkeypatch, registry=registry)["detailInspectionCalls"] == 0
    items = candidates()
    items[1]["firstPartyCandidateUrl"] = "https://user:pass@b.example/detail?id=1"
    assert scan(items, monkeypatch)["detailInspectionCalls"] == 0


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
