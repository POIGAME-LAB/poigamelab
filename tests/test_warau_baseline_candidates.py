import copy
import csv
import importlib.util
import json
from pathlib import Path

import pytest

import published_offer_contract as contract

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "warau_candidate_generator",
    ROOT / "scripts" / "generate_warau_baseline_candidates.py",
)
generator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(generator)


def make_row(game, offer_id, platform, reward):
    url = f"https://www.warau.jp/contents/point/pointEntrance.php?point_id={offer_id}"
    row = dict.fromkeys(generator.direct.FIELDS, "")
    row.update(
        offerKey=f"{game}|warau|{platform}|{url}",
        game=game,
        site="warau",
        provider="",
        reward=str(reward),
        condition="reviewed summary",
        platform=platform,
        type="StepUp",
        deadline="45日以内",
        updatedAt="2026-09-03",
        url=url,
        sourceUrl=url,
        verified="true",
    )
    return row


def make_evidence(offer_id, platform, reward):
    payload = {
        "offerId": str(offer_id),
        "name": "テストゲーム",
        "platform": platform,
        "rewardPoints": reward,
        "rewardUnit": "pt",
        "steps": [
            {"condition": "レベル5到達", "rewardPoints": reward},
        ],
        "termsText": "獲得条件 注意事項 獲得対象外",
    }
    import hashlib
    fingerprint = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "state": "parsed",
        "parserVersion": "warau-stepup-v1",
        **payload,
        "evidenceFingerprint": fingerprint,
    }


def test_build_candidate_is_unapproved_and_binds_full_published_row():
    row = make_row("メメントモリ", "205975", "Android", 12050)
    evidence = make_evidence("205975", "Android", 12050)
    candidate = generator.build_candidate(row, evidence, "2026-09-03")

    assert candidate["approved"] is False
    assert candidate["source"] == "warau"
    assert candidate["rewardPoints"] == 12050
    assert candidate["stepCount"] == 1
    assert candidate["evidenceFingerprint"] == evidence["evidenceFingerprint"]
    assert candidate["publishedRowFingerprint"] == generator.direct.published_row_fingerprint(row)
    assert candidate["unitConversion"] == {
        "sourceUnit": "pt",
        "targetUnit": "JPY",
        "yenPerPoint": 1,
        "evidenceUrl": "https://www.warau.jp/help/qa/128/",
    }


@pytest.mark.parametrize("mutation,reason", [
    ({"reward": "12051"}, "published_reward_mismatch"),
    ({"platform": "iOS"}, "published_platform_mismatch"),
    ({"verified": "false"}, "published_row_not_verified_warau"),
    ({"sourceUrl": "https://www.warau.jp/contents/point/pointEntrance.php?point_id=999999"},
     "published_identity_mismatch"),
])
def test_build_candidate_rejects_mismatched_published_baseline(mutation, reason):
    row = make_row("メメントモリ", "205975", "Android", 12050)
    row.update(mutation)
    evidence = make_evidence("205975", "Android", 12050)
    with pytest.raises(ValueError, match=reason):
        generator.build_candidate(row, evidence, "2026-09-03")


def test_generate_candidates_reads_only_requested_warau_targets(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()

    games = ["メメントモリ", "ホワイトアウト・サバイバル"]
    rows = [
        make_row("メメントモリ", "205975", "Android", 12050),
        make_row("メメントモリ", "206035", "iOS", 12050),
        make_row("ホワイトアウト・サバイバル", "205389", "Android", 12500),
        make_row("ホワイトアウト・サバイバル", "205390", "iOS", 12500),
    ]

    targets = {
        "games": [
            {
                "game": "メメントモリ",
                "aliases": ["MementoMori"],
                "known_urls_by_source": {"warau": [rows[0]["url"], rows[1]["url"]]},
            },
            {
                "game": "ホワイトアウト・サバイバル",
                "aliases": ["Whiteout Survival"],
                "known_urls_by_source": {"warau": [rows[2]["url"], rows[3]["url"]]},
            },
        ]
    }
    sources = {
        "sources": [{
            "id": "warau",
            "search_domains": ["warau.jp", "www.warau.jp", "ssl.warau.jp"],
        }]
    }
    (tmp_path / "config" / "game_targets.json").write_text(
        json.dumps(targets, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "config" / "point_sources.json").write_text(
        json.dumps(sources, ensure_ascii=False), encoding="utf-8"
    )
    published = tmp_path / "data" / "published_offers.csv"
    with published.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=generator.direct.FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    before = published.read_bytes()

    requested = []

    def fetch(url, source):
        requested.append(url)
        return "<synthetic>", url

    def inspect(raw, requested_url, final_url, aliases):
        offer_id = generator.direct.warau_offer_id(requested_url)
        row = next(item for item in rows
                   if generator.direct.warau_offer_id(item["url"]) == offer_id)
        return make_evidence(offer_id, row["platform"], int(row["reward"]))

    monkeypatch.setattr(generator.direct, "inspect_warau_offer", inspect)
    result = generator.generate_candidates(
        games=games,
        fetcher=fetch,
        root=tmp_path,
        checked_on="2026-09-03",
    )

    assert result["complete"] is True
    assert result["candidateCount"] == 4
    assert result["failureCount"] == 0
    assert all(item["approved"] is False for item in result["candidates"])
    assert requested == [row["url"] for row in rows]
    assert published.read_bytes() == before
    assert not (tmp_path / "config" / "approved_offer_baselines.json").exists()


def test_generate_candidates_fails_closed_on_one_changed_offer(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    row = make_row("メメントモリ", "205975", "Android", 12050)
    (tmp_path / "config" / "game_targets.json").write_text(json.dumps({
        "games": [{
            "game": "メメントモリ",
            "known_urls_by_source": {"warau": [row["url"]]},
        }]
    }, ensure_ascii=False))
    (tmp_path / "config" / "point_sources.json").write_text(json.dumps({
        "sources": [{
            "id": "warau",
            "search_domains": ["warau.jp", "www.warau.jp", "ssl.warau.jp"],
        }]
    }))
    with (tmp_path / "data" / "published_offers.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=generator.direct.FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)

    monkeypatch.setattr(
        generator.direct,
        "inspect_warau_offer",
        lambda *args: make_evidence("205975", "Android", 13000),
    )
    result = generator.generate_candidates(
        games=["メメントモリ"],
        fetcher=lambda url, source: ("<synthetic>", url),
        root=tmp_path,
        checked_on="2026-09-03",
    )

    assert result["complete"] is False
    assert result["candidateCount"] == 0
    assert result["failureCount"] == 1
    assert result["failures"][0]["reason"] == "published_reward_mismatch"


# ---------------------------------------------------------------------------------------------
# ID-independent published-offer contract (tests/published_offer_contract.py). Point-site
# campaigns end and are re-issued under new IDs, so published rows are validated by invariants
# instead of one day's IDs: normal, ended, re-issued-ID and malformed data are all covered.
# Kept in this file because it is part of the CI step that guards the daily refresh.
# ---------------------------------------------------------------------------------------------

WARAU = "https://www.warau.jp/contents/point/pointEntrance.php?point_id="


def warau_row(offer, game="メメントモリ", platform="Android", reward="12050", **overrides):
    url = f"{WARAU}{offer}"
    row = {
        "offerKey": f"{game}|warau|{platform}|{url}",
        "game": game, "site": "warau", "provider": "", "reward": reward,
        "condition": "新規アプリインストール後、StepUpミッションをクリア",
        "platform": platform, "type": "StepUp",
        "deadline": "インストール日から起算して30日以内",
        "updatedAt": "2026-10-20", "url": url, "sourceUrl": url, "verified": "true",
    }
    row.update(overrides)
    return row


# Offers confirmed ended on the source (Warau error page / Hapitas "この広告は終了しています")
# and retired by the daily refresh after three consecutive reads, 2026-10-18 .. 2026-10-20.
RETIRED = [("warau", i) for i in (
    "204645", "204643", "204984", "204983", "205557", "206425", "206460", "206488",
    "205975", "206500", "206035", "206501", "177971",
    "207406", "207049", "188016", "205982", "206037", "191401", "191400")] + [
    ("hapitas", "102450"), ("hapitas", "102451")]


# ---- real repository data -------------------------------------------------------------

def test_real_published_rows_satisfy_the_contract():
    rows = contract.load_rows()
    assert rows, "published_offers.csv must not be empty"
    assert contract.rows_problems(rows) == []


def test_retired_offers_are_not_republished():
    assert contract.retired_problems(contract.load_rows(), RETIRED) == []


# ---- normal / ended / re-issued -----------------------------------------------------------

def test_pinned_offer_listed_with_unchanged_identity_is_valid():
    rows = [warau_row("205975")]
    assert contract.pin_problems(rows, [contract.pin("warau", "205975", "メメントモリ", "Android")]) == []


def test_reward_change_of_a_listed_offer_is_not_a_failure():
    rows = [warau_row("205975", reward="13000")]
    assert contract.pin_problems(rows, [contract.pin("warau", "205975", "メメントモリ", "Android")]) == []


def test_ended_offer_that_left_no_row_is_valid():
    assert contract.pin_problems([], [contract.pin("warau", "205975", "メメントモリ", "Android")]) == []
    other = [warau_row("207637", game="Township", platform="iOS", reward="22540")]
    assert contract.pin_problems(other, [contract.pin("warau", "205975", "メメントモリ", "Android")]) == []


def test_offer_reissued_under_a_new_id_passes_and_the_new_row_is_still_validated():
    pins = [contract.pin("warau", "205975", "メメントモリ", "Android")]
    reissued = [warau_row("207991")]
    assert contract.pin_problems(reissued, pins) == []
    assert contract.rows_problems(reissued) == []
    broken = [warau_row("207991", reward="12050.5")]
    assert any(p.startswith("reward_not_positive_integer") for p in contract.rows_problems(broken))


def test_all_pinned_offers_ended_and_replaced_is_valid():
    pins = [contract.pin("warau", i, "メメントモリ", p) for i, p in (("205975", "Android"), ("206035", "iOS"))]
    rows = [warau_row("208101", platform="Android"), warau_row("208102", platform="iOS")]
    assert contract.pin_problems(rows, pins) == []
    assert contract.listed(rows, pins) == []


# ---- malformed data -----------------------------------------------------------------------

def codes(problems):
    return {p.split(":", 1)[0] for p in problems}


@pytest.mark.parametrize("override,expected", [
    ({"reward": "12050.5"}, "reward_not_positive_integer"),
    ({"reward": "0"}, "reward_not_positive_integer"),
    ({"reward": "-5"}, "reward_not_positive_integer"),
    ({"reward": "abc"}, "reward_not_positive_integer"),
    ({"verified": "false"}, "not_verified"),
    ({"platform": "Windows"}, "platform_invalid"),
    ({"updatedAt": "2026/10/20"}, "updatedAt_not_a_date"),
    ({"url": "http://www.warau.jp/contents/point/pointEntrance.php?point_id=205975"}, "url_not_https"),
    ({"condition": ""}, "missing"),
    ({"deadline": " "}, "missing"),
])
def test_malformed_row_is_reported(override, expected):
    row = warau_row("205975", **override)
    assert expected in codes(contract.row_problems(row)), override


def test_offerkey_and_url_must_name_the_same_campaign():
    row = warau_row("205975", url=f"{WARAU}999999")
    assert "offerKey_url_id_mismatch" in codes(contract.row_problems(row))


def test_url_without_a_campaign_id_is_reported_for_warau_and_hapitas():
    assert "url_without_offer_id" in codes(contract.row_problems(
        warau_row("1", url="https://www.warau.jp/contents/point/category",
                  offerKey="メメントモリ|warau|Android|https://www.warau.jp/contents/point/category")))


def test_offerkey_identity_must_match_game_site_and_platform():
    row = warau_row("205975", platform="iOS", offerKey=warau_row("205975")["offerKey"])
    assert "offerKey_identity_mismatch" in codes(contract.row_problems(row))


def test_duplicates_are_reported():
    a = warau_row("205975")
    assert "duplicate_offerKey" in codes(contract.rows_problems([a, copy.deepcopy(a)]))
    dup_id = warau_row("205975", platform="iOS")  # same campaign ID, different offerKey
    assert "duplicate_offer_id" in codes(contract.rows_problems([a, dup_id]))


def test_pinned_offer_whose_identity_changed_is_reported():
    pins = [contract.pin("warau", "205975", "メメントモリ", "Android")]
    assert "pinned_offer_game_changed" in codes(contract.pin_problems([warau_row("205975", game="Township")], pins))
    changed_platform = warau_row("205975", platform="iOS")
    assert "pinned_offer_platform_changed" in codes(contract.pin_problems([changed_platform], pins))


def test_pinned_offer_listed_twice_or_corrupt_is_reported():
    pins = [contract.pin("warau", "205975", "メメントモリ", "Android")]
    twice = [warau_row("205975"), warau_row("205975", offerKey="x|warau|Android|" + WARAU + "205975")]
    assert "pinned_offer_listed_more_than_once" in codes(contract.pin_problems(twice, pins))
    assert "not_verified" in codes(contract.pin_problems([warau_row("205975", verified="false")], pins))


def test_a_retired_offer_that_reappears_is_reported():
    rows = [warau_row("205975")]
    assert contract.retired_problems(rows, [("warau", "205975")]) == ["retired_offer_republished:warau:205975"]
    assert contract.retired_problems(rows, [("warau", "206035")]) == []
    assert contract.retired_problems([], RETIRED) == []


def test_missing_columns_are_reported_not_raised():
    row = warau_row("205975")
    del row["verified"]
    assert "missing" in codes(contract.row_problems(row))
