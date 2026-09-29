import copy, json, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import new_game_pipeline as p
import collect_editorial_evidence as c

BASE = ROOT / "research/new-games/2026-09-27"
NOW = datetime(2026, 9, 26, 18, tzinfo=timezone.utc)


def package():
    return p.read(BASE / "dossiers/mafia-city.json")


def sign(x):
    x.pop("editorialReview", None)
    x["editorialReview"] = {
        "reviewer": "test reviewer",
        "contentDigest": p.digest(x),
        **dict.fromkeys(
            (
                "amount_identity_os_terms",
                "pace_semantics",
                "specific_strategy",
                "originality",
                "baseline_quality",
            ),
            True,
        ),
    }
    return x


def test_valid_candidate_is_never_published():
    r = p.evaluate(sign(package()), NOW)
    assert r["status"] == "publication_candidate", r
    assert r["publicationAuthorized"] is False


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("platform", "unspecified", "invalid_os"),
        ("rewardYen", float("nan"), "invalid_reward"),
        ("rewardYen", 100, "step_total_mismatch"),
        ("retrievedAt", "2025-09-01", "stale_offer"),
        ("retrievedAt", "2027-09-01", "stale_offer"),
        ("identityReviewed", False, "offer_review_missing"),
        ("url", "javascript:alert(1)", "unsafe_offer_url"),
        ("deadline", "", "missing_deadline"),
        ("parserState", "review_required", "unparsed_offer"),
    ],
)
def test_offer_holds(field, value, reason):
    x = package()
    x["offers"][0][field] = value
    assert any(reason in e for e in p.evaluate(sign(x), NOW)["issues"])


def test_os_and_different_conditions_not_collapsed():
    x = package()
    x["offers"] = [o for o in x["offers"] if o["site"] == "warau"]
    assert len(x["offers"]) == 2
    assert {o["platform"] for o in x["offers"]} == {"iOS", "Android"}
    assert (
        x["offers"][0]["steps"][5]["condition"]
        != x["offers"][1]["steps"][5]["condition"]
    )


def test_existing_game_exclusion():
    regs = p.read(BASE / "registry.json") + [
        dict(slug="tenchi", name="天地英雄伝", aliases=[], gameId="existing")
    ]
    s = p.select(ROOT, regs)
    assert "tenchi" not in {r["slug"] for r in s["candidates"]}
    # mafia-city has since been published, so only four remain candidates.
    assert "mafia-city" not in {r["slug"] for r in s["candidates"]}
    assert len(s["candidates"]) == 4
    assert s["unresolved"]  # Unknown identity does not silently become a game.


def test_fabricated_days_rejected():
    x = package()
    x["progress"][0]["observation"]["days"] = 1
    assert any("progress_unbound" in i for i in p.evaluate(sign(x), NOW)["issues"])


def test_same_author_across_sites_is_not_independent():
    x = package()
    for s in x["sources"]:
        if s["kind"] == "player":
            s["playerKey"] = "same-author"
    assert "independent_progress_below_two" in p.evaluate(sign(x), NOW)["issues"]


def test_snippet_is_not_body():
    x = package()
    x["sources"][0]["access"] = "search_snippet"
    assert any(
        "source_body_unverified" in i for i in p.evaluate(sign(x), NOW)["issues"]
    )


def test_changed_article_invalidates_signoff():
    x = sign(package())
    x["guide"]["strategy"][0]["text"] += "明日必ず達成。"
    assert "editorial_signoff_required" in p.evaluate(x, NOW)["issues"]


def test_old_undated_or_wrong_game_source_rejected():
    for field, value, reason in [
        ("publishedAt", None, "source_date_old_or_unknown"),
        ("gameId", "wrong", "source_game_mismatch"),
    ]:
        x = package()
        x["sources"][0][field] = value
        assert any(reason in i for i in p.evaluate(sign(x), NOW)["issues"])


def test_missing_channel_not_complete():
    x = package()
    x["research"].pop("instagram")
    assert "research_lane_missing:instagram" in p.evaluate(sign(x), NOW)["issues"]


def test_missing_steps_and_duplicate_steps():
    for rows, reason in [
        ([], "invalid_steps"),
        ([package()["offers"][0]["steps"][0]] * 2, "duplicate_steps"),
    ]:
        x = package()
        x["offers"][0]["steps"] = rows
        assert any(reason in i for i in p.evaluate(sign(x), NOW)["issues"])


def test_render_is_static_escaped_no_tracking():
    x = package()
    x["name"] = "<script>alert(1)</script>"
    page = p.render(x, p.evaluate(x, NOW), ROOT)
    assert "<script>alert(1)</script>" not in page
    assert "noindex,nofollow" in page
    assert "googletagmanager" not in page and "adsbygoogle" not in page
    assert "実際の到達ペース" in page and "目次" in page


def test_no_input_or_publication_writes(tmp_path):
    files = [
        "games.csv",
        "data/published_offers.csv",
        "data/new_game_monitor.json",
        "kinoko-guide.html",
        "sitemap.xml",
        "ads.txt",
    ]
    before = {x: (ROOT / x).read_bytes() for x in files}
    p.run(ROOT, BASE, NOW)
    assert before == {x: (ROOT / x).read_bytes() for x in files}


def test_output_outside_quarantine_rejected(tmp_path):
    with pytest.raises(ValueError):
        p.run(ROOT, tmp_path, NOW)


def test_stale_rewards_and_fabricated_pace_not_rendered():
    x = package()
    for o in x["offers"]:
        o["retrievedAt"] = "2020-01-01"
    x["progress"][0]["observation"]["days"] = 12345
    page = p.render(x, p.evaluate(x, NOW), ROOT)
    assert "91,828" not in page and "12345日" not in page
    assert "現在報酬を確定できる案件なし" in page


def test_research_never_enters_public_artifact(tmp_path):
    import build_public_site, tempfile

    with tempfile.TemporaryDirectory(prefix="editorial-test-", dir=ROOT) as out:
        copied = build_public_site.build_public_site(Path(out) / "public")
    assert not any(x.startswith("research/") for x in copied)
    assert not any(
        x.endswith(g + "-guide.html")
        for x in copied
        # mafia-city-guide.html is the separately reviewed live page, not a
        # research preview, so it is intentionally allowed here.
        for g in (
            "grand-mafia",
            "viking-rise",
            "puzzles-chaos",
            "royal-match",
        )
    )


def test_priority_is_explicitly_not_measured_search_demand():
    results = p.run(ROOT, BASE, NOW)
    assert all(x["priority"]["searchDemand"] == "not_measured" for x in results)
    assert [x["priority"]["score"] for x in results] == sorted(
        [x["priority"]["score"] for x in results], reverse=True
    )


def test_fetch_failure_and_duplicate_do_not_clear_data():
    jobs = [
        {
            "slug": "x",
            "game": "x",
            "aliases": [],
            "offerJobs": [
                {
                    "source": "warau",
                    "url": "https://www.warau.jp/contents/point/pointEntrance.php?point_id=1",
                }
            ]
            * 2,
        }
    ]
    calls = []

    def fail(*a, **kw):
        calls.append(1)
        raise OSError("offline")

    out = c.collect(jobs, {"warau": {}}, fetcher=fail)
    # Empty source config is unsupported and no network is attempted.
    assert out["publicationWrites"] == 0
    out = c.collect(jobs, {"warau": {"id": "warau"}}, fetcher=fail)
    assert len(calls) == 1 and out["fetchCalls"] == 1
    assert all(r["state"] == "fetch_error" for r in out["results"][0]["offers"])


def test_budget_exhaustion_is_not_no_offers():
    jobs = [
        {
            "slug": "x",
            "game": "x",
            "aliases": [],
            "offerJobs": [
                {
                    "source": "warau",
                    "url": "https://www.warau.jp/contents/point/pointEntrance.php?point_id=1",
                }
            ],
        }
    ]
    out = c.collect(jobs, {"warau": {"id": "warau"}}, limit=0)
    assert out["results"][0]["offers"][0]["reason"] == "fetch_budget_exhausted"
