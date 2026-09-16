import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import enable_adopted_refresh as e


class T(unittest.TestCase):
    def fixture(self, td, published_sites=("warau", "coincome"), status="adopted"):
        td = Path(td)
        (td / "games.csv").write_text(
            "name,image,condition,days,difficulty,overview,tips,featured,addedDate\n"
            "新作ゲーム,,指定条件クリア,調査中,調査中,,,false,2026-09-14\n",
            encoding="utf-8",
        )
        with (td / "published.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["game", "site", "verified"])
            w.writeheader()
            for site in published_sites:
                w.writerow({"game": "新作ゲーム", "site": site, "verified": "true"})
        (td / "policy.json").write_text(
            json.dumps({
                "minimumConfirmedSourcesForComparison": 2,
                "games": {"新作ゲーム": {"enabled": False, "adoptedBy": "V30"}},
            }),
            encoding="utf-8",
        )
        row = {
            "game": "新作ゲーム",
            "status": status,
            "v29": {"eligible": True, "verifiedSourceCount": 2},
            "v30": {"adopted": True, "publishedOfferCount": 2},
        }
        (td / "bridge.json").write_text(json.dumps({"results": [row]}), encoding="utf-8")
        return td

    def runx(self, td):
        return e.run(
            td / "bridge.json",
            td / "policy.json",
            td / "published.csv",
            td / "games.csv",
            td / "status.json",
        )

    def test_enables_only_strict_adopted_game_with_two_published_sources(self):
        with tempfile.TemporaryDirectory() as x:
            td = self.fixture(x)
            out = self.runx(td)
            self.assertEqual(out["enabledNow"], 1)
            cfg = json.loads((td / "policy.json").read_text(encoding="utf-8"))
            self.assertTrue(cfg["games"]["新作ゲーム"]["enabled"])
            self.assertEqual(cfg["games"]["新作ゲーム"]["autoEnabledBy"], "POST_ADOPTION_REFRESH_V1")

    def test_holds_when_independent_published_sources_are_insufficient(self):
        with tempfile.TemporaryDirectory() as x:
            td = self.fixture(x, published_sites=("warau",))
            out = self.runx(td)
            self.assertEqual(out["enabledNow"], 0)
            self.assertEqual(out["held"], 1)
            cfg = json.loads((td / "policy.json").read_text(encoding="utf-8"))
            self.assertFalse(cfg["games"]["新作ゲーム"]["enabled"])

    def test_non_adopted_rows_are_ignored(self):
        with tempfile.TemporaryDirectory() as x:
            td = self.fixture(x, status="hold")
            out = self.runx(td)
            self.assertEqual(out["eligibleAdoptions"], 0)
            cfg = json.loads((td / "policy.json").read_text(encoding="utf-8"))
            self.assertFalse(cfg["games"]["新作ゲーム"]["enabled"])

    def test_legacy_api_adoption_is_manual_only(self):
        text = (ROOT / ".github/workflows/adopt-high-reward-games.yml").read_text(encoding="utf-8")
        self.assertNotIn("workflow_run:", text)
        self.assertNotIn("schedule:", text)
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("if: github.event_name == 'workflow_dispatch'", text)
        self.assertIn("python scripts/enable_adopted_refresh.py", text)



if __name__ == "__main__":
    unittest.main()
