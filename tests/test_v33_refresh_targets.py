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

    assert by_name["ATLAS: EARTH"]["known_urls_by_source"] == {
        "coincome": ["https://cimcome.jp/campaigns/details/9663"]
    }
    for name in V33_GAMES - {"ATLAS: EARTH"}:
        assert by_name[name]["known_urls_by_source"] == {}
