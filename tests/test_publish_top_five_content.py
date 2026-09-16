import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publish_top_five_content as p


def queue():
    return {"phase": "NEW_GAME_CONTENT_QUEUE_V1", "checkedAt": "2026-09-15T01:17:00+09:00",
            "items": [{"rank": 1, "game": "Game 1"}, {"rank": 2, "game": "Game 2"}]}


def adoptions():
    return {"phase": "TOP_FIVE_CONTENT_ADOPTION_GATE_V1", "sourceQueueCheckedAt": "2026-09-15T01:17:00+09:00",
            "items": [
                {"game": "Game 1", "eligible": True, "status": "adoption_ready", "verifiedSourceCount": 2},
                {"game": "Game 2", "eligible": False, "status": "hold", "verifiedSourceCount": 1},
            ]}


def setup(td):
    root = Path(td)
    (root / "data").mkdir(); (root / "config").mkdir(); (root / "content").mkdir(); (root / "results").mkdir()
    (root / "games.csv").write_text("name,image\nTownship,old.png\n", encoding="utf-8")
    (root / "data/published_offers.csv").write_text("offerKey,game,site,provider,reward,condition,platform,type,deadline,updatedAt,url,sourceUrl,verified\n", encoding="utf-8")
    for name in ("game_targets.json", "refresh_policy.json", "trend_discovery.json"):
        (root / "config" / name).write_text("{}", encoding="utf-8")
    (root / "site-guides.js").write_text("window.POIGAME_GUIDES=Object.freeze({});\n", encoding="utf-8")
    (root / "sitemap.xml").write_text("<urlset></urlset>", encoding="utf-8")
    q = root / "q.json"; q.write_text(json.dumps(queue()), encoding="utf-8")
    a = root / "a.json"; a.write_text(json.dumps(adoptions()), encoding="utf-8")
    return root, q, a


class TestPublishTopFiveContent(unittest.TestCase):
    def test_stale_bundle_is_rejected(self):
        bad = adoptions(); bad["sourceQueueCheckedAt"] = "old"
        with self.assertRaisesRegex(ValueError, "stale"):
            p.validate_handoff(queue(), bad)

    def test_outside_game_is_rejected(self):
        bad = adoptions(); bad["items"].append({"game": "Other", "eligible": True, "status": "adoption_ready"})
        with self.assertRaisesRegex(ValueError, "outside_queue"):
            p.validate_handoff(queue(), bad)

    def test_bridge_marks_missing_v30_result_as_hold(self):
        rows = p.bridge_rows(adoptions(), {"results": [{"game": "Game 1", "adopted": True}]})
        self.assertEqual(rows[0]["status"], "adopted")
        self.assertEqual(rows[1]["status"], "hold")
        self.assertIn("v30_result_missing", rows[1]["v30"]["reasons"])

    def test_run_orchestrates_api_free_adoption_refresh_and_registry(self):
        with tempfile.TemporaryDirectory() as td:
            root, q, a = setup(td)
            def fake_v30(**kwargs):
                rows = list(csv.DictReader((root / "games.csv").open(encoding="utf-8")))
                with (root / "games.csv").open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=["name", "image"]); writer.writeheader(); writer.writerows(rows)
                    writer.writerow({"name": "Game 1", "image": "assets/game-art/game-1-auto.svg"})
                return {"adopted": 1, "held": 0, "results": [{"game": "Game 1", "adopted": True}]}
            paths = {name: root / name for name in ("status.json", "v30.json", "bridge.json", "refresh.json", "registry.json")}
            with mock.patch.object(p.v30, "run", side_effect=fake_v30), \
                 mock.patch.object(p.enable_refresh, "run", return_value={"enabledNow": 1}), \
                 mock.patch.object(p.registry, "run", return_value={"registered": 1}):
                out = p.run(q, a, root / "results", root / "content", root=root,
                            status_path=paths["status.json"], v30_status_path=paths["v30.json"],
                            bridge_path=paths["bridge.json"], refresh_status_path=paths["refresh.json"],
                            registry_path=paths["registry.json"], guides_js=root / "site-guides.js", sitemap=root / "sitemap.xml")
            self.assertEqual(out["apiCalls"], 0)
            self.assertEqual(out["adopted"], 1)
            self.assertEqual(out["addedGames"], ["Game 1"])
            self.assertEqual(out["refreshEnabledNow"], 1)
            self.assertTrue(paths["bridge.json"].is_file())


if __name__ == "__main__":
    unittest.main()
