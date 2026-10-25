import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import select_top_five_new_games as selector


SOURCES = ["moppy", "warau", "coincome", "hapitas", "amefuri", "point_town", "ec_navi", "powl"]


def offer(source, reward, suffix="1", verified=True, url=True):
    return {
        "source": source,
        "url": f"https://{source}.example/offer/{suffix}" if url else "http://unsafe.example/x",
        "platform": "Android",
        "rewardYen": reward,
        "rewardVerified": verified,
        "parserVersion": f"{source}-v1",
        "offerIdentity": suffix,
    }


def group(game, reward_offers, listed=False, key=None):
    verified = [o["rewardYen"] for o in reward_offers if o.get("rewardVerified") is True and type(o.get("rewardYen")) is int and o["rewardYen"] > 0 and str(o.get("url", "")).startswith("https://")]
    return {
        "gameKey": key or selector.norm(game),
        "game": game,
        "listed": listed,
        "sourceCount": len({o["source"] for o in reward_offers}),
        "sources": sorted({o["source"] for o in reward_offers}),
        "offerCount": len(reward_offers),
        "verifiedRewardCount": len(verified),
        "maxVerifiedRewardYen": max(verified) if verified else None,
        "offers": reward_offers,
    }


def snapshot(groups, incomplete=()):
    bad = set(incomplete)
    return {
        "phase": "UNIFIED_EIGHT_SITE_OFFER_SNAPSHOT_V1",
        "checkedAt": "2026-09-17T00:17:00+00:00",
        "publicationAuthorized": False,
        "sourceIds": list(SOURCES),
        "sourceCount": len(SOURCES),
        "sourceHealth": [{"source": sid, "scanComplete": sid not in bad, "catalogComplete": False} for sid in SOURCES],
        "groups": groups,
    }


def test_one_verified_site_is_enough_for_ranking():
    out = selector.build(snapshot([
        group("One Site Game", [offer("warau", 12000)]),
        group("Two Site Game", [offer("moppy", 11000), offer("warau", 9000)]),
    ]))
    assert out["rankingComplete"] is True
    assert out["oneVerifiedSiteEligible"] is True
    assert [x["game"] for x in out["items"]] == ["One Site Game", "Two Site Game"]
    assert out["items"][0]["verifiedSourceCount"] == 1


def test_same_game_uses_highest_verified_reward_without_consuming_multiple_ranks():
    out = selector.build(snapshot([
        group("Game A", [offer("warau", 10500, "a"), offer("moppy", 8000, "b"), offer("coincome", 9200, "c")]),
        group("Game B", [offer("hapitas", 9800)]),
    ]))
    assert out["count"] == 2
    assert out["items"][0]["game"] == "Game A"
    assert out["items"][0]["maxVerifiedRewardYen"] == 10500
    assert out["items"][0]["verifiedSourceCount"] == 3
    assert len([x for x in out["items"] if x["game"] == "Game A"]) == 1


def test_only_top_five_games_are_selected_by_max_reward():
    groups = [group(f"Game {i}", [offer("warau", i * 1000, str(i))]) for i in range(1, 8)]
    out = selector.build(snapshot(groups))
    assert [x["game"] for x in out["items"]] == ["Game 7", "Game 6", "Game 5", "Game 4", "Game 3"]
    assert [x["rank"] for x in out["items"]] == [1, 2, 3, 4, 5]


def test_listed_and_games_csv_games_are_excluded():
    out = selector.build(snapshot([
        group("Already Listed", [offer("warau", 50000)], listed=True),
        group("CSV Listed", [offer("warau", 40000)]),
        group("New Game", [offer("warau", 30000)]),
    ]), known_games={selector.norm("CSV Listed")})
    assert [x["game"] for x in out["items"]] == ["New Game"]


def test_unverified_or_unsafe_reward_is_not_ranked():
    out = selector.build(snapshot([
        group("Unverified", [offer("warau", 50000, verified=False)]),
        group("Unsafe URL", [offer("warau", 45000, url=False)]),
        group("Verified", [offer("warau", 1000)]),
    ]))
    assert [x["game"] for x in out["items"]] == ["Verified"]


def test_incomplete_source_scan_fails_closed_instead_of_claiming_top_five():
    out = selector.build(snapshot([group("Game A", [offer("warau", 99999)])], incomplete={"powl"}))
    assert out["rankingComplete"] is False
    assert out["holdReason"] == "source_scan_incomplete"
    assert out["incompleteSources"] == ["powl"]
    assert out["items"] == []


def test_reward_aggregate_mismatch_fails_closed():
    bad = group("Game A", [offer("warau", 10000)])
    bad["maxVerifiedRewardYen"] = 99999
    with pytest.raises(ValueError, match="snapshot_reward_aggregate_mismatch"):
        selector.build(snapshot([bad]))


def test_duplicate_game_key_fails_closed():
    a = group("Game A", [offer("warau", 1000)], key="same")
    b = group("Game B", [offer("moppy", 2000)], key="same")
    with pytest.raises(ValueError, match="snapshot_duplicate_game_key"):
        selector.build(snapshot([a, b]))


def test_write_is_atomic_and_games_csv_exclusion_works():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        inp = td / "snapshot.json"
        games = td / "games.csv"
        outp = td / "selected.json"
        inp.write_text(json.dumps(snapshot([
            group("Existing", [offer("warau", 20000)]),
            group("Fresh", [offer("moppy", 10000)]),
        ])), encoding="utf-8")
        games.write_text("name,image\nExisting,x.png\n", encoding="utf-8")
        result = selector.write(inp, games, outp)
        saved = json.loads(outp.read_text(encoding="utf-8"))
        assert saved == result
        assert [x["game"] for x in saved["items"]] == ["Fresh"]
        assert not outp.with_suffix(".json.tmp").exists()
