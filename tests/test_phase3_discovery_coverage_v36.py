import importlib.util, json, unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('trend_v36',ROOT/'scripts/discover_trending_games.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
pspec=importlib.util.spec_from_file_location('promote_v36',ROOT/'scripts/promote_trend_candidates.py')
promote=importlib.util.module_from_spec(pspec); pspec.loader.exec_module(promote)

class DiscoveryCoverageV36Tests(unittest.TestCase):
    def test_warau_adds_bounded_broad_official_listing(self):
        cfg=json.loads((ROOT/'config/trend_discovery.json').read_text())
        warau={q['id']:q for q in cfg['queries']}['warau-new']
        self.assertEqual(len(warau['directUrls']),2)
        self.assertIn('https://www.warau.jp/contents/point/category?point_group=2',warau['directUrls'])

    def test_direct_url_keeps_public_selectors_but_drops_tracking(self):
        url='https://www.warau.jp/contents/point/category?point_group=2&page=1&sort=new&utm_source=x&token=secret'
        self.assertEqual(
            mod.safe_direct_url(url),
            'https://www.warau.jp/contents/point/category?point_group=2&page=1&sort=new'
        )

    def test_multiple_direct_listing_queries_do_not_collapse_before_gemini(self):
        cfg={'queries':[{
            'id':'warau-new','query':'x','sourceType':'point_site','includeDomains':['warau.jp'],
            'directUrls':['https://www.warau.jp/contents/point/category?point_group=2',
                          'https://www.warau.jp/contents/point/category?category_id=290&point_group=6'],
            'firecrawlFallback':False,
        }]}
        def fake(item,url):
            return {'sourceId':'warau-new','sourceType':'point_site','title':'Warau','description':'',
                    'url':mod.safe_direct_url(url),'text':'official listing text long enough for extraction','retrieval':'direct_http'}
        captured={}
        def fake_extract(gem,items,known):
            captured['urls']=[x['url'] for x in items]
            return []
        with patch.object(mod,'direct_fetch_seed',side_effect=fake), patch.object(mod,'known_games',return_value=[]), \
             patch.object(mod,'extract_names',side_effect=fake_extract), patch.object(mod,'firecrawl_search') as fc:
            out=mod.run('expired','gem',cfg)
        fc.assert_not_called()
        self.assertEqual(out['summary']['searchResults'],2)
        self.assertEqual(len(set(captured['urls'])),2)

    def test_stepup_variants_merge_across_independent_sources_and_promote(self):
        items=[
            {'sourceId':'warau-new','sourceType':'point_site','title':'Warau','url':'https://www.warau.jp/list'},
            {'sourceId':'moppy-official-games','sourceType':'point_site','title':'Moppy','url':'https://pc.moppy.jp/article'},
        ]
        extracted=[
            {'canonical_name':'ロイヤルマッチ（StepUp）','aliases':[],'evidence_indexes':[0],'confidence':0},
            {'canonical_name':'ロイヤルマッチ','aliases':[],'evidence_indexes':[1],'confidence':0},
        ]
        rows=mod.score_candidates(extracted,items,[])
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual(row['game'],'ロイヤルマッチ')
        self.assertIn('ロイヤルマッチ(StepUp)',row['aliases'])
        self.assertEqual(row['sourceCount'],2)
        self.assertEqual(row['confidence'],80)
        cfg=json.loads((ROOT/'config/trend_discovery.json').read_text())
        ok,reasons=promote.promotion_decision(row,cfg,known=set())
        self.assertTrue(ok,reasons)

    def test_platform_and_registered_provider_decorations_are_identity_only(self):
        self.assertEqual(mod.canonical_game_name('Android_Merge Peko＜StepUp＞'),'Merge Peko')
        self.assertEqual(mod.canonical_game_name('【SKYFLAG】モンスターバスケット（StepUp）'),'モンスターバスケット')

    def test_live_shape_firecrawl_402_still_promotes_two_direct_source_match(self):
        cfg={
            'maxResultsPerQuery':8,
            'queries':[
                {'id':'x-poikatsu','query':'x','sourceType':'social','includeDomains':['x.com'],'firecrawlFallback':True},
                {'id':'warau-new','query':'x','sourceType':'point_site','includeDomains':['warau.jp'],
                 'directUrls':['https://www.warau.jp/contents/point/category?category_id=290&point_group=6',
                               'https://www.warau.jp/contents/point/category?point_group=2'],
                 'firecrawlFallback':True},
                {'id':'chobirich-new','query':'x','sourceType':'point_site','includeDomains':['chobirich.com'],'firecrawlFallback':True},
                {'id':'moppy-official-games','query':'x','sourceType':'point_site','includeDomains':['pc.moppy.jp'],
                 'directUrls':['https://pc.moppy.jp/poikatsu-lab/4753-1/'],'firecrawlFallback':False},
                {'id':'coincome-new','query':'x','sourceType':'point_site','includeDomains':['cimcome.jp'],
                 'directUrls':['https://cimcome.jp/campaigns?_category_id=21'],'firecrawlFallback':True},
            ]
        }
        def fake_direct(item,url):
            return {'sourceId':item['id'],'sourceType':item['sourceType'],'title':item['id'],'description':'',
                    'url':mod.safe_direct_url(url),'text':'official listing text with game names and enough content for extraction',
                    'retrieval':'direct_http'}
        def fake_extract(gem,items,known):
            warau_idx=next(i for i,x in enumerate(items) if x['sourceId']=='warau-new' and 'point_group=2' in x['url'])
            moppy_idx=next(i for i,x in enumerate(items) if x['sourceId']=='moppy-official-games')
            return [
                {'canonical_name':'ロイヤルマッチ（StepUp）','evidence_indexes':[warau_idx],'confidence':0},
                {'canonical_name':'ロイヤルマッチ','evidence_indexes':[moppy_idx],'confidence':0},
            ]
        with patch.object(mod,'direct_fetch_seed',side_effect=fake_direct), \
             patch.object(mod,'firecrawl_search',side_effect=RuntimeError('HTTP Error 402: Payment Required')), \
             patch.object(mod,'known_games',return_value=[]), patch.object(mod,'extract_names',side_effect=fake_extract):
            out=mod.run('expired','gem',cfg)
        self.assertEqual(out['summary']['failedSources'],2)
        self.assertEqual(out['summary']['searchResults'],4)
        self.assertEqual(len(out['candidates']),1)
        row=out['candidates'][0]
        self.assertEqual(row['game'],'ロイヤルマッチ')
        self.assertEqual(row['sourceCount'],2)
        self.assertEqual(row['confidence'],80)
        real_cfg=json.loads((ROOT/'config/trend_discovery.json').read_text())
        ok,reasons=promote.promotion_decision(row,real_cfg,known=set())
        self.assertTrue(ok,reasons)

    def test_conservative_identity_does_not_merge_titles_or_non_stepup_suffixes(self):
        items=[
            {'sourceId':'a','sourceType':'point_site','title':'A','url':'https://a.example/x'},
            {'sourceId':'b','sourceType':'point_site','title':'B','url':'https://b.example/x'},
            {'sourceId':'c','sourceType':'point_site','title':'C','url':'https://c.example/x'},
        ]
        extracted=[
            {'canonical_name':'Royal Match','evidence_indexes':[0]},
            {'canonical_name':'Royal Match 2','evidence_indexes':[1]},
            {'canonical_name':'Royal Match（Anniversary）','evidence_indexes':[2]},
        ]
        rows=mod.score_candidates(extracted,items,[])
        self.assertEqual({r['game'] for r in rows},{'Royal Match','Royal Match 2','Royal Match(Anniversary)'})
        self.assertTrue(all(r['sourceCount']==1 for r in rows))

if __name__=='__main__': unittest.main()
