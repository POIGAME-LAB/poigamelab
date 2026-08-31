import importlib.util,json,os,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bridge',ROOT/'scripts/research_offer_bridge.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class CP:
    def __init__(self,code=0): self.returncode=code
class V28Tests(unittest.TestCase):
    def test_select_only_ready_and_limit(self):
        q={'items':[{'game':'A','collectorReady':True,'status':'collector_ready'},{'game':'B','collectorReady':True,'status':'collector_ready'},{'game':'C','collectorReady':False,'status':'collector_ready'}]}
        self.assertEqual([x['game'] for x in mod.select_items(q,1)],['A'])
    def test_unicode_slugs_do_not_collapse(self):
        a=mod.stable_slug('新作ゲームA'); b=mod.stable_slug('新作ゲームB')
        self.assertIn('-',a); self.assertNotEqual(a,b)
    def test_collector_supports_external_target_without_editing_registry(self):
        text=(ROOT/'scripts/collect_games.py').read_text()
        self.assertIn('--target-json',text); self.assertIn("target={'game'",text)
    def test_quarantine_gate_skips_publisher(self):
        text=(ROOT/'scripts/firecrawl_township_probe.py').read_text()
        self.assertIn('POIGAMELAB_PUBLISH_MODE',text); self.assertIn('publish_mode == "quarantine"',text)
    def test_workflow_caps_research_and_commits_quarantine_only(self):
        w=(ROOT/'.github/workflows/discover-trending-games.yml').read_text()
        self.assertIn('RESEARCH_MAX_GAMES: "1"',w); self.assertIn('python scripts/research_offer_bridge.py',w)
        self.assertIn('data/research_results/',w); self.assertNotIn('git add data/published_offers.csv',w)
    def test_bridge_does_not_modify_publication_or_registry_by_design(self):
        text=(ROOT/'scripts/research_offer_bridge.py').read_text()
        self.assertNotIn("write_text", '\n'.join(x for x in text.splitlines() if 'published_offers' in x or 'game_targets' in x))
        self.assertIn("env['POIGAMELAB_PUBLISH_MODE']='quarantine'",text)
    def test_no_ready_items_makes_zero_runner_calls(self):
        with tempfile.TemporaryDirectory() as d:
            q=Path(d)/'q.json'; q.write_text(json.dumps({'items':[]}),encoding='utf-8'); calls=[]
            out=mod.run(q,max_games=1,runner=lambda *a,**k:calls.append(a) or CP())
            self.assertEqual(out['selected'],0); self.assertEqual(calls,[]); self.assertTrue(out['success'])
if __name__=='__main__': unittest.main()
