import importlib.util, json, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("trend",ROOT/"scripts/discover_trending_games.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class TrendV26Tests(unittest.TestCase):
    def test_safe_url_strips_tracking(self):
        self.assertEqual(mod.safe_url("https://x.com/a/status/1?utm_source=x#z"),"https://x.com/a/status/1")
        self.assertEqual(mod.safe_url("javascript:alert(1)"),"")
    def test_score_requires_evidence_and_dedupes(self):
        items=[{"sourceId":"x","sourceType":"social","title":"新作A","url":"https://x.com/1"},
               {"sourceId":"warau","sourceType":"point_site","title":"新作A","url":"https://warau.jp/1"}]
        ext=[{"canonical_name":"新作A","aliases":["新作 A"],"known_game":False,"evidence_indexes":[0,1],"confidence":90},
             {"canonical_name":"幻ゲーム","evidence_indexes":[],"confidence":99}]
        out=mod.score_candidates(ext,items,["Township"])
        self.assertEqual(len(out),1); self.assertEqual(out[0]["game"],"新作A")
        self.assertEqual(out[0]["status"],"要確認"); self.assertGreaterEqual(out[0]["score"],30)
    def test_known_game_never_becomes_new_review(self):
        items=[{"sourceId":"x","sourceType":"social","title":"Township","url":"https://x.com/1"}]
        out=mod.score_candidates([{"canonical_name":"Township","evidence_indexes":[0],"confidence":99}],items,["Township"])
        self.assertTrue(out[0]["knownGame"]); self.assertEqual(out[0]["status"],"既知ゲーム")
    def test_candidate_output_is_explicitly_nonpublishing(self):
        # Contract test: workflow may only commit trend outputs, never game/offer publication files.
        wf=(ROOT/".github/workflows/discover-trending-games.yml").read_text(encoding="utf-8")
        self.assertIn("data/trend_candidates.json data/trend_status.json",wf)
        self.assertNotIn("git add games.csv",wf); self.assertNotIn("git add data/published_offers.csv",wf)
    def test_config_concurrency_and_candidate_only_contract(self):
        cfg=json.loads((ROOT/"config/trend_discovery.json").read_text(encoding="utf-8"))
        self.assertLessEqual(cfg["maxFirecrawlConcurrency"],2)
        src=(ROOT/"scripts/discover_trending_games.py").read_text(encoding="utf-8")
        self.assertIn('"candidateOnly":True',src); self.assertIn('"autoPublish":False',src)

if __name__ == "__main__": unittest.main()
