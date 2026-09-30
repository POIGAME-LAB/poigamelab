import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

V33_GAMES = {
    "ATLAS: EARTH",
    "ファミリーファームの冒険",
    "クロンダイクの冒険",
    "Merge Help: ホームデザインパズル",
    "マジックジグソーパズル",
}


def test_every_enabled_refresh_policy_game_has_a_refresh_target():
    policy = json.loads((ROOT / "config" / "refresh_policy.json").read_text(encoding="utf-8"))
    targets = json.loads((ROOT / "config" / "game_targets.json").read_text(encoding="utf-8"))

    enabled = {name for name, cfg in policy["games"].items() if cfg.get("enabled") is True}
    target_names = {item["game"] for item in targets["games"]}

    assert enabled <= target_names
    assert V33_GAMES <= target_names


def test_v33_targets_have_safe_aliases_and_only_reviewed_atlas_offer_url():
    targets = json.loads((ROOT / "config" / "game_targets.json").read_text(encoding="utf-8"))
    by_name = {item["game"]: item for item in targets["games"]}

    for name in V33_GAMES:
        target = by_name[name]
        assert name in target["aliases"]

    # Only offer URLs whose first-party page was reviewed may be registered.
    # 2026-09-29: the Warau pages were opened with the production parser and
    # matched game, OS and StepUp terms (Klondike's steps match games.csv;
    # "Warm Family" is the iOS title documented in merge-help-guide.html).
    warau = "https://www.warau.jp/contents/point/pointEntrance.php?point_id="
    reviewed = {
        "ATLAS: EARTH": {"coincome": ["https://cimcome.jp/campaigns/details/9663"]},
        "クロンダイクの冒険": {"warau": [warau + "205043", warau + "205042"]},
        "Merge Help: ホームデザインパズル": {"warau": [warau + "207045", warau + "207041"]},
    }
    for name in V33_GAMES:
        assert by_name[name]["known_urls_by_source"] == reviewed.get(name, {})
