"""Every game shown on the site is checked by the daily refresh (operator decision 2026-11-24)."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_catalog_game_is_in_the_daily_policy_and_targets():
    catalog = [r["name"] for r in csv.DictReader((ROOT / "games.csv").open(encoding="utf-8"))]
    policy = json.loads((ROOT / "config/refresh_policy.json").read_text(encoding="utf-8"))["games"]
    targets = {t["game"]: t for t in json.loads((ROOT / "config/game_targets.json").read_text(encoding="utf-8"))["games"]}
    assert [g for g in catalog if g not in policy] == []
    assert [g for g in catalog if g not in targets] == []
    for game in catalog:
        assert policy[game]["enabled"] is True
        assert game in targets[game]["aliases"]
