import importlib.util, json, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('trend_v32',ROOT/'scripts/discover_trending_games.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class DiscoveryRecoveryV32Tests(unittest.TestCase):
    def test_point_site_fallbacks_are_first_party(self):
        cfg=json.loads((ROOT/'config/trend_discovery.json').read_text())
        by={q['id']:q for q in cfg['queries']}
        self.assertIn('warau.jp',by['warau-new']['fallbackUrls'][0])
        self.assertIn('cimcome.jp',by['coincome-new']['fallbackUrls'][0])

    def test_fallback_runs_only_after_search_failure_or_zero(self):
        cfg={'maxResultsPerQuery':8,'queries':[{'id':'warau-new','query':'x','sourceType':'point_site','fallbackUrls':['https://www.warau.jp/list']}]}
        with patch.object(mod,'firecrawl_search',return_value=[]), patch.object(mod,'firecrawl_scrape_seed',return_value={'sourceId':'warau-new','sourceType':'point_site','title':'A','description':'','url':'https://www.warau.jp/list','text':'Game A'}), patch.object(mod,'known_games',return_value=[]), patch.object(mod,'extract_names',return_value=[]):
            out=mod.run('fc','gem',cfg)
        self.assertEqual(out['summary']['failedSources'],0)
        self.assertEqual(out['summary']['searchResults'],1)
        self.assertEqual(out['diagnostics'][0]['fallbackResults'],1)

    def test_successful_search_does_not_spend_fallback_call(self):
        cfg={'maxResultsPerQuery':8,'queries':[{'id':'warau-new','query':'x','sourceType':'point_site','fallbackUrls':['https://www.warau.jp/list']}]}
        raw=[{'url':'https://www.warau.jp/a','title':'A','description':'','markdown':'Game A'}]
        with patch.object(mod,'firecrawl_search',return_value=raw), patch.object(mod,'firecrawl_scrape_seed') as fb, patch.object(mod,'known_games',return_value=[]), patch.object(mod,'extract_names',return_value=[]):
            mod.run('fc','gem',cfg)
        fb.assert_not_called()

    def test_failed_search_and_failed_fallback_remains_failed(self):
        cfg={'maxResultsPerQuery':8,'queries':[{'id':'warau-new','query':'x','sourceType':'point_site','fallbackUrls':['https://www.warau.jp/list']}]}
        with patch.object(mod,'firecrawl_search',side_effect=RuntimeError('search down')), patch.object(mod,'firecrawl_scrape_seed',side_effect=RuntimeError('scrape down')), patch.object(mod,'known_games',return_value=[]), patch.object(mod,'extract_names',return_value=[]):
            out=mod.run('fc','gem',cfg)
        self.assertEqual(out['summary']['failedSources'],1)
        self.assertIn('searchError',out['diagnostics'][0])
        self.assertTrue(out['diagnostics'][0]['fallbackErrors'])

    def test_recovered_point_site_can_create_independent_evidence(self):
        items=[{'sourceId':'x-poikatsu','sourceType':'social','title':'Game A','url':'https://x.com/1'}, {'sourceId':'warau-new','sourceType':'point_site','title':'Game A','url':'https://www.warau.jp/list'}]
        out=mod.score_candidates([{'canonical_name':'Game A','evidence_indexes':[0,1],'confidence':90}],items,[])[0]
        self.assertEqual(out['sourceCount'],2)
        self.assertGreaterEqual(out['score'],60)
        self.assertIn('point_site',{e['sourceType'] for e in out['evidence']})

if __name__=='__main__': unittest.main()
