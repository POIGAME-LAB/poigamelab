import importlib.util, io, json, unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('trend_v34',ROOT/'scripts/discover_trending_games.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class FakeResponse:
    def __init__(self, body, content_type='text/html; charset=utf-8'):
        self.body=body.encode('utf-8') if isinstance(body,str) else body
        self.headers=Message(); self.headers['Content-Type']=content_type
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n=-1): return self.body if n < 0 else self.body[:n]

class DirectHttpV34Tests(unittest.TestCase):
    def test_config_has_two_first_party_direct_sources(self):
        cfg=json.loads((ROOT/'config/trend_discovery.json').read_text())
        by={q['id']:q for q in cfg['queries']}
        self.assertIn('warau.jp',by['warau-new']['directUrls'][0])
        self.assertIn('category_id=290',by['warau-new']['directUrls'][0])
        self.assertIn('cimcome.jp',by['coincome-new']['directUrls'][0])
        self.assertIn('_category_id=21',by['coincome-new']['directUrls'][0])

    def test_direct_fetch_strips_scripts_and_extracts_title(self):
        html='<html><head><title>案件一覧</title><style>.x{}</style></head><body><h1>新着ゲーム</h1><script>SECRET()</script><p>Game Alpha StepUp 1000pt 条件達成でポイント獲得できる新着ゲーム案件です</p></body></html>'
        item={'id':'warau-new','sourceType':'point_site','includeDomains':['warau.jp']}
        with patch.object(mod,'urlopen',return_value=FakeResponse(html)):
            row=mod.direct_fetch_seed(item,'https://www.warau.jp/list')
        self.assertEqual(row['title'],'案件一覧')
        self.assertIn('Game Alpha',row['text'])
        self.assertNotIn('SECRET',row['text'])
        self.assertEqual(row['retrieval'],'direct_http')

    def test_direct_fetch_rejects_unregistered_domain(self):
        item={'id':'warau-new','includeDomains':['warau.jp']}
        with self.assertRaisesRegex(ValueError,'not registered'):
            mod.direct_fetch_seed(item,'https://evil.example/list')

    def test_direct_success_skips_firecrawl_even_when_key_exists(self):
        cfg={'maxResultsPerQuery':8,'queries':[{'id':'warau-new','query':'x','sourceType':'point_site','includeDomains':['warau.jp'],'directUrls':['https://www.warau.jp/list'],'firecrawlFallback':True}]}
        row={'sourceId':'warau-new','sourceType':'point_site','title':'Games','description':'','url':'https://www.warau.jp/list','text':'Game A offer text long enough to be useful','retrieval':'direct_http'}
        with patch.object(mod,'direct_fetch_seed',return_value=row), patch.object(mod,'firecrawl_search') as fc, patch.object(mod,'known_games',return_value=[]), patch.object(mod,'extract_names',return_value=[]):
            out=mod.run('expired-key','gem',cfg)
        fc.assert_not_called()
        self.assertEqual(out['summary']['searchResults'],1)
        self.assertEqual(out['summary']['failedSources'],0)
        self.assertTrue(out['diagnostics'][0]['directAttempted'])
        self.assertFalse(out['diagnostics'][0]['firecrawlAttempted'])

    def test_direct_failure_then_402_is_fail_soft_and_diagnostic(self):
        cfg={'maxResultsPerQuery':8,'queries':[{'id':'warau-new','query':'x','sourceType':'point_site','includeDomains':['warau.jp'],'directUrls':['https://www.warau.jp/list'],'firecrawlFallback':True}]}
        with patch.object(mod,'direct_fetch_seed',side_effect=RuntimeError('HTTP 503')), patch.object(mod,'firecrawl_search',side_effect=RuntimeError('HTTP Error 402: Payment Required')), patch.object(mod,'known_games',return_value=[]), patch.object(mod,'extract_names',return_value=[]):
            out=mod.run('expired-key','gem',cfg)
        d=out['diagnostics'][0]
        self.assertEqual(out['summary']['failedSources'],1)
        self.assertTrue(d['firecrawlAttempted'])
        self.assertIn('503',d['directErrors'][0])
        self.assertIn('402',d['searchError'])

    def test_missing_firecrawl_key_does_not_block_direct_sources(self):
        cfg={'maxResultsPerQuery':8,'queries':[{'id':'coincome-new','query':'x','sourceType':'point_site','includeDomains':['cimcome.jp'],'directUrls':['https://cimcome.jp/campaigns?_category_id=21'],'firecrawlFallback':True}]}
        row={'sourceId':'coincome-new','sourceType':'point_site','title':'Apps','description':'','url':'https://cimcome.jp/campaigns','text':'Game A app offer text long enough to be useful','retrieval':'direct_http'}
        with patch.object(mod,'direct_fetch_seed',return_value=row), patch.object(mod,'firecrawl_search') as fc, patch.object(mod,'known_games',return_value=[]), patch.object(mod,'extract_names',return_value=[]):
            out=mod.run('','gem',cfg)
        fc.assert_not_called()
        self.assertEqual(out['summary']['failedSources'],0)

    def test_two_direct_point_sites_still_meet_existing_source_score_without_lowering_gate(self):
        items=[
            {'sourceId':'warau-new','sourceType':'point_site','title':'A','url':'https://www.warau.jp/list'},
            {'sourceId':'coincome-new','sourceType':'point_site','title':'A','url':'https://cimcome.jp/campaigns'},
        ]
        row=mod.score_candidates([{'canonical_name':'Game A','evidence_indexes':[0,1],'confidence':90}],items,[])[0]
        self.assertEqual(row['sourceCount'],2)
        self.assertGreaterEqual(row['score'],60)
        self.assertEqual(row['confidence'],90)

    def test_duplicate_direct_rows_are_deduped_before_gemini(self):
        cfg={'queries':[{'id':'warau-new','query':'x','sourceType':'point_site','includeDomains':['warau.jp'],'directUrls':['https://www.warau.jp/a','https://www.warau.jp/b'],'firecrawlFallback':True}]}
        def direct(item,url):
            return {'sourceId':'warau-new','sourceType':'point_site','title':'A','description':'','url':'https://www.warau.jp/list','text':'same readable game list content here 1234567890','retrieval':'direct_http'}
        captured={}
        def extract(gem,items,known): captured['n']=len(items); return []
        with patch.object(mod,'direct_fetch_seed',side_effect=direct), patch.object(mod,'known_games',return_value=[]), patch.object(mod,'extract_names',side_effect=extract):
            out=mod.run('','gem',cfg)
        self.assertEqual(captured['n'],1)
        self.assertEqual(out['summary']['searchResults'],1)

    def test_direct_overlap_can_reach_existing_research_gate(self):
        import importlib.util
        pspec=importlib.util.spec_from_file_location('promote_v34',ROOT/'scripts/promote_trend_candidates.py')
        promote=importlib.util.module_from_spec(pspec); pspec.loader.exec_module(promote)
        cfg=json.loads((ROOT/'config/trend_discovery.json').read_text())
        items=[
            {'sourceId':'warau-new','sourceType':'point_site','title':'A','url':'https://www.warau.jp/list'},
            {'sourceId':'coincome-new','sourceType':'point_site','title':'A','url':'https://cimcome.jp/campaigns'},
        ]
        candidate=mod.score_candidates([{'canonical_name':'Brand New Game','evidence_indexes':[0,1],'confidence':90}],items,[])[0]
        trend={'generatedAt':'2026-09-01T00:00:00+09:00','candidates':[candidate]}
        queue=promote.build_research_queue(trend,cfg,previous={},known=set(),now='2026-09-01T00:01:00+09:00')
        self.assertEqual(cfg['minimumScoreForResearch'],60)
        self.assertEqual(cfg['minimumConfidenceForResearch'],70)
        self.assertEqual(cfg['minimumSourcesForResearch'],2)
        self.assertTrue(cfg['requirePointSiteEvidenceForResearch'])
        self.assertEqual(queue['summary']['collectorReady'],1)
        self.assertEqual(queue['summary']['rejected'],0)

if __name__=='__main__': unittest.main()
