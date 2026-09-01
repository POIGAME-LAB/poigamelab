import importlib.util, json, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
promote=load("promote_v43","scripts/promote_trend_candidates.py")
bridge=load("bridge_v43","scripts/research_offer_bridge.py")
CFG={"minimumScoreForResearch":60,"minimumConfidenceForResearch":70,"minimumSourcesForResearch":2,"requirePointSiteEvidenceForResearch":True,"researchLogicVersion":"V41-mobile-direct"}

def candidate():
    return {"game":"ホワイトアウト・サバイバル","aliases":[],"score":80,"confidence":80,"sourceCount":2,"sourceTypeCount":1,"evidence":[{"sourceId":"warau","sourceType":"point_site","url":"https://warau.jp/a"},{"sourceId":"moppy","sourceType":"point_site","url":"https://pc.moppy.jp/b"}]}

class CP:
    returncode=0

class V43Tests(unittest.TestCase):
    def test_logic_change_requeues_unchanged_completed_candidate_once(self):
        c=candidate(); fp=promote.candidate_fingerprint(c)
        prev={"items":[{"game":c["game"],"status":"research_complete","collectorReady":False,"candidateFingerprint":fp,"lastResearchLogicVersion":"V39-card-context","lastResearchAt":"t0"}]}
        q=promote.build_research_queue({"candidates":[c]},CFG,previous=prev,known=set(),now="t1")
        item=q["items"][0]
        self.assertTrue(item["collectorReady"]); self.assertEqual(item["status"],"collector_ready")
        self.assertEqual(item["recheckReason"],"research_logic_changed")
        self.assertEqual(item["researchLogicVersion"],"V41-mobile-direct")
    def test_legacy_completed_row_without_version_requeues_once_after_v43_deploy(self):
        c=candidate(); fp=promote.candidate_fingerprint(c)
        prev={"items":[{"game":c["game"],"status":"research_complete","collectorReady":False,"candidateFingerprint":fp,"lastResearchAt":"t0"}]}
        q=promote.build_research_queue({"candidates":[c]},CFG,previous=prev,known=set(),now="t1")
        item=q["items"][0]
        self.assertTrue(item["collectorReady"]); self.assertEqual(item["recheckReason"],"research_logic_changed")

    def test_same_logic_does_not_repeat_research(self):
        c=candidate(); fp=promote.candidate_fingerprint(c)
        prev={"items":[{"game":c["game"],"status":"research_complete","collectorReady":False,"candidateFingerprint":fp,"lastResearchLogicVersion":"V41-mobile-direct","lastResearchAt":"t0"}]}
        q=promote.build_research_queue({"candidates":[c]},CFG,previous=prev,known=set(),now="t1")
        item=q["items"][0]
        self.assertFalse(item["collectorReady"]); self.assertEqual(item["status"],"research_complete"); self.assertIsNone(item["recheckReason"])
    def test_changed_candidate_still_requeues_independently_of_logic(self):
        c=candidate()
        prev={"items":[{"game":c["game"],"status":"research_complete","collectorReady":False,"candidateFingerprint":"old","lastResearchLogicVersion":"V41-mobile-direct"}]}
        q=promote.build_research_queue({"candidates":[c]},CFG,previous=prev,known=set(),now="t1")
        self.assertTrue(q["items"][0]["collectorReady"]); self.assertIsNone(q["items"][0]["recheckReason"])
    def test_bridge_records_completed_logic_version(self):
        with tempfile.TemporaryDirectory() as d:
            qpath=Path(d)/"q.json"
            q={"items":[{"game":"A","aliases":["A"],"status":"collector_ready","collectorReady":True,"researchLogicVersion":"V41-mobile-direct","recheckReason":"research_logic_changed"}]}
            qpath.write_text(json.dumps(q),encoding="utf-8")
            old_result=bridge.ROOT/'data'/'a_firecrawl_result.json'
            def runner(*a,**k):
                old_result.write_text(json.dumps({"health":{"publishableCount":0,"collectionComplete":False,"degradedReasons":["test"]}}),encoding="utf-8")
                return CP()
            old_queue=bridge.QUEUE
            saved_result=bridge.RESULTS/'a.json'
            try:
                bridge.QUEUE=qpath
                bridge.run(qpath,max_games=1,runner=runner)
                saved=json.loads(qpath.read_text())['items'][0]
                self.assertEqual(saved['lastResearchLogicVersion'],'V41-mobile-direct'); self.assertIsNone(saved['recheckReason'])
            finally:
                bridge.QUEUE=old_queue
                old_result.unlink(missing_ok=True); saved_result.unlink(missing_ok=True)
    def test_config_declares_research_logic_version(self):
        cfg=json.loads((ROOT/'config/trend_discovery.json').read_text())
        self.assertTrue(cfg['researchLogicVersion'])

if __name__=='__main__': unittest.main()
