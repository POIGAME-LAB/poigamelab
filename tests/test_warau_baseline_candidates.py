import csv
import importlib.util
import json
from pathlib import Path

import pytest

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
