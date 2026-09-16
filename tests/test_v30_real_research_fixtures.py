import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import adopt_verified_games as v30


READY = ["War of Towers", "パズル＆コンクエスト"]


def test_previous_v30_valueerror_fixtures_now_adopt_offline():
    # This is a no-network regression using the exact quarantined research files
    # that reached V29 adoption_ready before V30 failed with ValueError.
    with tempfile.TemporaryDirectory() as raw:
        td = Path(raw)
        for source, target in [
            (ROOT / "games.csv", td / "games.csv"),
            (ROOT / "config/game_targets.json", td / "targets.json"),
            (ROOT / "config/refresh_policy.json", td / "refresh.json"),
            (ROOT / "data/published_offers.csv", td / "published.csv"),
        ]:
            shutil.copy2(source, target)
        cfg = json.loads((ROOT / "config/trend_discovery.json").read_text(encoding="utf-8"))
        # This regression isolates the historical V30 serialization/publisher bug.
        # The new content package gate has its own tests and remains enabled in production.
        cfg.setdefault("productionAdoption", {})["requiresContentPackage"] = False
        (td / "cfg.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        (td / "adopt.json").write_text(json.dumps({
            "items": [{"game": game, "eligible": True, "status": "adoption_ready"} for game in READY]
        }, ensure_ascii=False), encoding="utf-8")

        out = v30.run(
            adoptions_path=td / "adopt.json",
            results_dir=ROOT / "data/research_results",
            games_path=td / "games.csv",
            targets_path=td / "targets.json",
            refresh_path=td / "refresh.json",
            published_path=td / "published.csv",
            status_path=td / "status.json",
            config_path=td / "cfg.json",
        )
        decisions = {row["game"]: row for row in out["results"]}
        assert set(READY) <= decisions.keys()
        assert all(decisions[game]["adopted"] is True for game in READY)

        games = list(csv.DictReader((td / "games.csv").open(encoding="utf-8", newline="")))
        header = list(games[0].keys())
        assert "provisionalReward" in header and "provisionalSource" in header
        assert all(any(row["name"] == game for row in games) for game in READY)

        offers = list(csv.DictReader((td / "published.csv").open(encoding="utf-8", newline="")))
        adopted_offers = [row for row in offers if row["game"] in READY]
        assert adopted_offers
        assert all(row["site"] != "unknown" for row in adopted_offers)
