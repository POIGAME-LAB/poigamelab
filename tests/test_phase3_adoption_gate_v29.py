import importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('adopt',ROOT/'scripts/evaluate_research_adoption.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
CFG={'minimumVerifiedOffersForAdoption':2,'minimumVerifiedSourcesForAdoption':2}

def offer(source='warau',strict=True):
    checks={k:True for k in mod.REQUIRED_CHECKS}
    if not strict: checks['reward_consistent']=False
    return {'registered_source':source,'auto_publish_ready':True,'deterministic_checks':checks}
def payload(offers=None,complete=True,degraded=None):
    return {'game':'新作','quarantine':True,'autoPublish':False,'collectorResult':{'verified':{'game':'新作','offers':offers or []},'health':{'collectionComplete':complete,'degradedReasons':degraded or []}}}

class V29Tests(unittest.TestCase):
    def test_two_strict_sources_pass(self):
        d=mod.evaluate(payload([offer('warau'),offer('coincome')]),CFG)
        self.assertTrue(d['eligible']); self.assertEqual(d['status'],'adoption_ready')
    def test_one_source_fails_even_with_two_offers(self):
        d=mod.evaluate(payload([offer('warau'),offer('warau')]),CFG)
        self.assertFalse(d['eligible']); self.assertIn('insufficient_verified_sources',d['reasons'])
    def test_incomplete_or_degraded_never_passes(self):
        for p in [payload([offer('warau'),offer('coincome')],False),payload([offer('warau'),offer('coincome')],True,['warau:search_failed'])]:
            self.assertFalse(mod.evaluate(p,CFG)['eligible'])
    def test_weak_publishable_offer_blocks_adoption(self):
        d=mod.evaluate(payload([offer('warau'),offer('coincome',False)]),CFG)
        self.assertFalse(d['eligible']); self.assertIn('publishable_offer_missing_strict_checks',d['reasons'])
    def test_not_quarantined_fails(self):
        p=payload([offer('warau'),offer('coincome')]); p['quarantine']=False
        self.assertIn('not_quarantined',mod.evaluate(p,CFG)['reasons'])
    def test_run_is_api_free_and_candidate_only(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); r=base/'r'; r.mkdir(); (r/'x.json').write_text(json.dumps(payload([offer('warau'),offer('coincome')])),encoding='utf-8')
            cfg=base/'c.json'; cfg.write_text(json.dumps(CFG)); out=base/'out.json'
            result=mod.run(r,out,cfg)
            self.assertEqual(result['apiCalls'],0); self.assertFalse(result['autoPublish']); self.assertFalse(result['autoAddGame'])
    def test_workflow_runs_gate_and_never_commits_publication(self):
        w=(ROOT/'.github/workflows/discover-trending-games.yml').read_text()
        self.assertIn('python scripts/evaluate_research_adoption.py',w); self.assertIn('data/adoption_candidates.json',w)
        self.assertNotIn('git add games.csv',w); self.assertNotIn('git add data/published_offers.csv',w)
    def test_research_state_is_preserved_when_evidence_unchanged(self):
        import importlib.util
        sp=importlib.util.spec_from_file_location('promote_v29',ROOT/'scripts/promote_trend_candidates.py'); pm=importlib.util.module_from_spec(sp); sp.loader.exec_module(pm)
        c={'game':'新作','aliases':[],'knownGame':False,'score':80,'confidence':90,'sourceCount':2,'sourceTypeCount':2,'evidence':[{'sourceId':'x','sourceType':'social','url':'https://x.com/a'},{'sourceId':'warau','sourceType':'point_site','url':'https://warau.jp/a'}]}
        fp=pm.candidate_fingerprint(c); prev={'items':[{'game':'新作','status':'research_complete','collectorReady':False,'candidateFingerprint':fp,'firstPromotedAt':'t0','lastResearchAt':'t1'}]}
        cfg={'minimumScoreForResearch':60,'minimumConfidenceForResearch':70,'minimumSourcesForResearch':2,'requirePointSiteEvidenceForResearch':True}
        q=pm.build_research_queue({'candidates':[c]},cfg,previous=prev,known=set(),now='t2')
        self.assertEqual(q['items'][0]['status'],'research_complete'); self.assertFalse(q['items'][0]['collectorReady']); self.assertEqual(q['summary']['collectorReady'],0)
    def test_changed_evidence_requeues(self):
        import importlib.util
        sp=importlib.util.spec_from_file_location('promote_v29b',ROOT/'scripts/promote_trend_candidates.py'); pm=importlib.util.module_from_spec(sp); sp.loader.exec_module(pm)
        c={'game':'新作','aliases':[],'knownGame':False,'score':80,'confidence':90,'sourceCount':2,'sourceTypeCount':2,'evidence':[{'sourceId':'x','sourceType':'social','url':'https://x.com/new'},{'sourceId':'warau','sourceType':'point_site','url':'https://warau.jp/a'}]}
        prev={'items':[{'game':'新作','status':'research_complete','collectorReady':False,'candidateFingerprint':'old','firstPromotedAt':'t0'}]}
        cfg={'minimumScoreForResearch':60,'minimumConfidenceForResearch':70,'minimumSourcesForResearch':2,'requirePointSiteEvidenceForResearch':True}
        q=pm.build_research_queue({'candidates':[c]},cfg,previous=prev,known=set(),now='t2')
        self.assertEqual(q['items'][0]['status'],'collector_ready'); self.assertTrue(q['items'][0]['collectorReady'])
if __name__=='__main__': unittest.main()
