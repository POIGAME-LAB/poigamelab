import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_top_five_offers as r


def queue(count=6):
    return {
        "phase": "NEW_GAME_CONTENT_QUEUE_V1",
        "checkedAt": "2026-09-15T01:17:00+09:00",
        "items": [
            {
                "rank": i,
                "game": f"Game {i}",
                "maxObservedRewardYen": 10000 - i,
                "pointSiteEvidence": [
                    {"source": "warau", "url": f"https://www.warau.jp/contents/point/pointEntrance.php?point_id={i}"},
                    {"source": "amefuri", "url": f"https://www.amefri.net/detail/id/{i}"},
                ],
            }
            for i in range(1, count + 1)
        ],
    }


def config():
    return {"minimumVerifiedOffersForAdoption": 2, "minimumVerifiedSourcesForAdoption": 2}


class TestResearchTopFiveOffers(unittest.TestCase):
    def test_research_item_requires_two_point_sites(self):
        row = queue(1)["items"][0]
        item = r.research_item_from_queue(row)
        self.assertEqual(item["game"], "Game 1")
        self.assertEqual(set(item["sources"]), {"warau", "amefuri"})
        row["pointSiteEvidence"] = row["pointSiteEvidence"][:1]
        with self.assertRaisesRegex(ValueError, "below_two"):
            r.research_item_from_queue(row)

    def test_run_is_quarantine_only_and_limited_to_five(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            q = td / "queue.json"; q.write_text(json.dumps(queue()), encoding="utf-8")
            cfg = td / "cfg.json"; cfg.write_text(json.dumps(config()), encoding="utf-8")
            results = td / "results"; results.mkdir()
            adoptions = td / "adoptions.json"; status = td / "status.json"
            old_root, old_results, old_adoptions, old_status = r.ROOT, r.RESULTS, r.ADOPTIONS, r.STATUS
            r.ROOT, r.RESULTS, r.ADOPTIONS, r.STATUS = td, results, adoptions, status
            calls = []
            def research_one(item, env=None):
                calls.append(item["game"])
                payload = {"game": item["game"], "collectorResult": {"verified": {"game": item["game"], "offers": []}}}
                (results / f"{r.research.stable_slug(item['game'])}.json").write_text(json.dumps(payload), encoding="utf-8")
                return {"game": item["game"], "returncode": 0, "resultSaved": True}
            def evaluate(payload, cfg):
                return {"game": payload["game"], "eligible": True, "status": "adoption_ready", "reasons": [], "verifiedSourceCount": 2}
            try:
                with mock.patch.object(r.content_gate, "validate_for_game", return_value={"game": "ok"}):
                    out = r.run(q, td / "content", cfg, research_one=research_one, evaluate=evaluate, env={})
                self.assertEqual(calls, ["Game 1", "Game 2", "Game 3", "Game 4", "Game 5"])
                self.assertEqual(out["adoptionReady"], 5)
                self.assertEqual(out["publicationWrites"], 0)
                doc = json.loads(adoptions.read_text())
                self.assertFalse(doc["autoPublish"])
                self.assertFalse(doc["autoAddGame"])
                self.assertEqual(len(doc["items"]), 5)
            finally:
                r.ROOT, r.RESULTS, r.ADOPTIONS, r.STATUS = old_root, old_results, old_adoptions, old_status

    def test_content_gate_failure_skips_external_research(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            q = td / "queue.json"; q.write_text(json.dumps(queue(1)), encoding="utf-8")
            cfg = td / "cfg.json"; cfg.write_text(json.dumps(config()), encoding="utf-8")
            old_adoptions, old_status = r.ADOPTIONS, r.STATUS
            r.ADOPTIONS, r.STATUS = td / "a.json", td / "s.json"
            try:
                with mock.patch.object(r.content_gate, "validate_for_game", side_effect=r.content_gate.ContentHold("guide_missing")):
                    research_one = mock.Mock()
                    out = r.run(q, td / "content", cfg, research_one=research_one, evaluate=mock.Mock(), env={})
                research_one.assert_not_called()
                self.assertEqual(out["adoptionReady"], 0)
                self.assertEqual(out["held"], 1)
            finally:
                r.ADOPTIONS, r.STATUS = old_adoptions, old_status


if __name__ == "__main__":
    unittest.main()
