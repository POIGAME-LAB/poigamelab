import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "append_offer_history",
    ROOT / "scripts" / "append_offer_history.py",
)
history = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(history)


def write_published(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "offerKey", "game", "site", "provider", "reward", "condition",
        "platform", "type", "deadline", "updatedAt", "url", "sourceUrl", "verified"
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def row(game, site, platform, reward, offer_key=None, verified="true"):
    return {
        "offerKey": offer_key or f"{game}|{site}|{platform}|x",
        "game": game,
        "site": site,
        "provider": "",
        "reward": str(reward),
        "condition": "x",
        "platform": platform,
        "type": "StepUp",
        "deadline": "",
        "updatedAt": "2026-09-04",
        "url": "https://example.test/",
        "sourceUrl": "https://example.test/",
        "verified": verified,
    }


def test_canonical_groups_uses_highest_verified_reward_per_game_site_platform():
    groups = history.canonical_groups([
        row("Game", "site", "iOS", 100),
        row("Game", "site", "iOS", 120, offer_key="higher"),
        row("Game", "site", "Android", 90),
        row("Game", "other", "iOS", 999, verified="false"),
    ])
    assert groups == [
        {
            "game": "Game",
            "site": "site",
            "platform": "Android",
            "reward": 90,
            "offerKey": "Game|site|Android|x",
        },
        {
            "game": "Game",
            "site": "site",
            "platform": "iOS",
            "reward": 120,
            "offerKey": "higher",
        },
    ]


def test_append_snapshot_skips_unchanged_and_appends_reward_change(tmp_path):
    published = tmp_path / "published.csv"
    history_file = tmp_path / "history.csv"
    write_published(published, [
        row("Game", "site", "iOS", 100),
        row("Game", "site", "Android", 90),
    ])

    first = history.append_snapshot(
        published, history_file, "2026-09-01T00:00:00Z"
    )
    assert first["appended"] is True
    first_bytes = history_file.read_bytes()

    unchanged = history.append_snapshot(
        published, history_file, "2026-09-02T00:00:00Z"
    )
    assert unchanged == {
        "appended": False,
        "reason": "unchanged",
        "groupCount": 2,
    }
    assert history_file.read_bytes() == first_bytes

    write_published(published, [
        row("Game", "site", "iOS", 125),
        row("Game", "site", "Android", 90),
    ])
    changed = history.append_snapshot(
        published, history_file, "2026-09-03T00:00:00Z"
    )
    assert changed["appended"] is True

    rows = history.read_csv(history_file)
    assert len(rows) == 4
    assert [r["observedAt"] for r in rows] == [
        "2026-09-01T00:00:00Z",
        "2026-09-01T00:00:00Z",
        "2026-09-03T00:00:00Z",
        "2026-09-03T00:00:00Z",
    ]


def test_repository_history_backfill_contains_known_whiteout_change():
    rows = history.read_csv(ROOT / "data" / "offer_history.csv")
    whiteout_warau_android = [
        int(r["reward"])
        for r in rows
        if r["game"] == "ホワイトアウト・サバイバル"
        and r["site"] == "warau"
        and r["platform"] == "Android"
    ]
    assert 11500 in whiteout_warau_android
    assert 12500 in whiteout_warau_android

    observed = sorted({r["observedAt"] for r in rows})
    assert observed[0].startswith("2026-08-31")
    assert len(observed) >= 6
