import importlib.util, json, unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('trend_v35',ROOT/'scripts/discover_trending_games.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
pspec=importlib.util.spec_from_file_location('promote_v35',ROOT/'scripts/promote_trend_candidates.py')
promote=importlib.util.module_from_spec(pspec); pspec.loader.exec_module(promote)

class SourceCoverageV35Tests(unittest.TestCase):
    def test_config_adds_official_moppy_as_independent_direct_source(self):
        cfg=json.loads((ROOT/'config/trend_discovery.json').read_text())
        by={q['id']:q for q in cfg['queries']}
        m=by['moppy-official-games']
        self.assertEqual(m['sourceType'],'point_site')
        self.assertEqual(m['includeDomains'],['pc.moppy.jp'])
        self.assertEqual(m['directUrls'],['https://pc.moppy.jp/poikatsu-lab/4753-1/'])
        self.assertFalse(m['firecrawlFallback'])

    def test_single_source_model_confidence_cannot_pass_python_confidence_gate(self):
        items=[{'sourceId':'warau-new','sourceType':'point_site','title':'A','url':'https://www.warau.jp/list'}]
        row=mod.score_candidates([{'canonical_name':'Game A','evidence_indexes':[0],'confidence':100}],items,[])[0]
        self.assertEqual(row['sourceCount'],1)
        self.assertEqual(row['confidence'],45)
        self.assertEqual(row['modelConfidence'],100)
        cfg=json.loads((ROOT/'config/trend_discovery.json').read_text())
        ok,reasons=promote.promotion_decision(row,cfg,known=set())
        self.assertFalse(ok)
        self.assertIn('confidence_below_threshold',reasons)
        self.assertIn('insufficient_independent_sources',reasons)

    def test_two_independent_point_sites_get_deterministic_confidence_and_can_promote(self):
        items=[
            {'sourceId':'warau-new','sourceType':'point_site','title':'A','url':'https://www.warau.jp/list'},
            {'sourceId':'moppy-official-games','sourceType':'point_site','title':'B','url':'https://pc.moppy.jp/poikatsu-lab/4753-1/'},
        ]
        row=mod.score_candidates([{'canonical_name':'Game A','evidence_indexes':[0,1],'confidence':0}],items,[])[0]
        self.assertEqual(row['sourceCount'],2)
        self.assertEqual(row['confidence'],80)
        self.assertGreaterEqual(row['score'],60)
        self.assertEqual(row['modelConfidence'],0)
        cfg=json.loads((ROOT/'config/trend_discovery.json').read_text())
        ok,reasons=promote.promotion_decision(row,cfg,known=set())
        self.assertTrue(ok,reasons)

    def test_moppy_direct_success_never_calls_firecrawl(self):
        cfg={'queries':[{
            'id':'moppy-official-games','query':'x','sourceType':'point_site',
            'includeDomains':['pc.moppy.jp'],'directUrls':['https://pc.moppy.jp/poikatsu-lab/4753-1/'],
            'firecrawlFallback':False,
        }]}
        row={'sourceId':'moppy-official-games','sourceType':'point_site','title':'Games','description':'',
             'url':'https://pc.moppy.jp/poikatsu-lab/4753-1/','text':'Official point game article with Game A and sufficient text','retrieval':'direct_http'}
        with patch.object(mod,'direct_fetch_seed',return_value=row), patch.object(mod,'firecrawl_search') as fc, \
             patch.object(mod,'known_games',return_value=[]), patch.object(mod,'extract_names',return_value=[]):
            out=mod.run('expired','gem',cfg)
        fc.assert_not_called()
        self.assertEqual(out['summary']['failedSources'],0)
        self.assertEqual(out['summary']['searchResults'],1)

    def test_moppy_direct_failure_is_fail_soft_without_firecrawl_charge(self):
        cfg={'queries':[{
            'id':'moppy-official-games','query':'x','sourceType':'point_site',
            'includeDomains':['pc.moppy.jp'],'directUrls':['https://pc.moppy.jp/poikatsu-lab/4753-1/'],
            'firecrawlFallback':False,
        }]}
        with patch.object(mod,'direct_fetch_seed',side_effect=RuntimeError('HTTP 503')), patch.object(mod,'firecrawl_search') as fc, \
             patch.object(mod,'known_games',return_value=[]), patch.object(mod,'extract_names',return_value=[]):
            out=mod.run('expired','gem',cfg)
        fc.assert_not_called()
        self.assertEqual(out['summary']['failedSources'],1)
        d=out['diagnostics'][0]
        self.assertIn('503',d['directErrors'][0])
        self.assertFalse(d['firecrawlAttempted'])

    def test_three_sources_raise_confidence_monotonically(self):
        items=[
            {'sourceId':'warau-new','sourceType':'point_site','title':'A','url':'https://www.warau.jp/list'},
            {'sourceId':'moppy-official-games','sourceType':'point_site','title':'B','url':'https://pc.moppy.jp/article'},
            {'sourceId':'coincome-new','sourceType':'point_site','title':'C','url':'https://cimcome.jp/campaigns'},
        ]
        row=mod.score_candidates([{'canonical_name':'Game A','evidence_indexes':[0,1,2],'confidence':1}],items,[])[0]
        self.assertEqual(row['sourceCount'],3)
        self.assertEqual(row['confidence'],90)
        self.assertEqual(row['modelConfidence'],1)

if __name__=='__main__': unittest.main()
