import importlib.util, json, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("promote",ROOT/"scripts/promote_trend_candidates.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
CFG={"minimumScoreForResearch":60,"minimumConfidenceForResearch":70,"minimumSourcesForResearch":2,"requirePointSiteEvidenceForResearch":True}

def candidate(game="新作A", score=80, confidence=90, source_count=2, evidence=None, known=False, aliases=None):
    return {"game":game,"aliases":aliases or [],"knownGame":known,"score":score,"confidence":confidence,
            "sourceCount":source_count,"sourceTypeCount":2,"evidence":evidence if evidence is not None else [
                {"sourceId":"x","sourceType":"social","title":"A","url":"https://x.com/1"},
                {"sourceId":"warau","sourceType":"point_site","title":"A","url":"https://warau.jp/1"}]}

class PromotionV27Tests(unittest.TestCase):
    def test_strong_candidate_promotes_without_api(self):
        out=mod.build_research_queue({"generatedAt":"t0","candidates":[candidate()]},CFG,known=set(),now="t1")
        self.assertEqual(out["summary"]["collectorReady"],1); self.assertEqual(out["apiCalls"],0)
        self.assertTrue(out["items"][0]["collectorReady"]); self.assertFalse(out["autoPublish"])
    def test_social_only_does_not_promote(self):
        c=candidate(evidence=[{"sourceId":"x","sourceType":"social","title":"A","url":"https://x.com/1"}])
        out=mod.build_research_queue({"candidates":[c]},CFG,known=set(),now="t")
        self.assertEqual(out["summary"]["collectorReady"],0)
        self.assertIn("no_point_site_evidence",out["rejected"][0]["reasons"])
    def test_low_score_confidence_or_sources_rejected(self):
        for c, reason in [(candidate(score=59),"score_below_threshold"),(candidate(confidence=69),"confidence_below_threshold"),(candidate(source_count=1),"insufficient_independent_sources")]:
            out=mod.build_research_queue({"candidates":[c]},CFG,known=set(),now="t")
            self.assertIn(reason,out["rejected"][0]["reasons"])
    def test_known_alias_cannot_promote_even_if_ai_misses_flag(self):
        c=candidate(game="タウンシップ",aliases=["Township"],known=False)
        ok,reasons=mod.promotion_decision(c,CFG,known={"township"})
        self.assertFalse(ok); self.assertIn("known_game",reasons)
    def test_dedupes_and_preserves_first_promoted_timestamp(self):
        trend={"generatedAt":"t2","candidates":[candidate(),candidate(score=70)]}
        prev={"items":[{"game":"新作A","firstPromotedAt":"t0"}]}
        out=mod.build_research_queue(trend,CFG,previous=prev,known=set(),now="t2")
        self.assertEqual(len(out["items"]),1); self.assertEqual(out["items"][0]["firstPromotedAt"],"t0")
    def test_workflow_runs_promotion_and_only_commits_nonpublication_outputs(self):
        wf=(ROOT/".github/workflows/discover-trending-games.yml").read_text()
        self.assertIn("python scripts/promote_trend_candidates.py",wf)
        self.assertIn("data/research_queue.json",wf)
        self.assertNotIn("git add games.csv",wf); self.assertNotIn("git add data/published_offers.csv",wf)
    def test_config_has_cost_guards(self):
        cfg=json.loads((ROOT/"config/trend_discovery.json").read_text())
        self.assertGreaterEqual(cfg["minimumSourcesForResearch"],2)
        self.assertTrue(cfg["requirePointSiteEvidenceForResearch"])

if __name__ == "__main__": unittest.main()
