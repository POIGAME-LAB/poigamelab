import importlib.util, json, unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('trend_v37',ROOT/'scripts/discover_trending_games.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
pspec=importlib.util.spec_from_file_location('promote_v37',ROOT/'scripts/promote_trend_candidates.py')
promote=importlib.util.module_from_spec(pspec); pspec.loader.exec_module(promote)

class LongListingExtractionV37Tests(unittest.TestCase):
    def test_long_page_tail_is_chunked_instead_of_truncated(self):
        text=('前半案件\n' * 900) + '\nロイヤルマッチ(StepUp)\n' + ('後半案件\n' * 50)
        units=mod.prepare_extraction_items([{
            'sourceId':'warau-new','sourceType':'point_site','title':'Warau','description':'',
            'url':'https://www.warau.jp/list','text':text,'retrieval':'direct_http'
        }], {'extractionChunkChars':4500,'extractionChunkOverlap':300,'maxChunksPerResult':6})
        self.assertGreater(len(units),1)
        self.assertTrue(any('ロイヤルマッチ' in x['text'] for x in units))
        self.assertTrue(all(len(x['text']) <= 4500 for x in units))

    def test_same_page_multiple_chunks_never_inflate_independent_sources(self):
        items=[
            {'sourceId':'warau-new','sourceType':'point_site','title':'Warau','url':'https://www.warau.jp/list','text':'a'},
            {'sourceId':'warau-new','sourceType':'point_site','title':'Warau','url':'https://www.warau.jp/list','text':'b'},
        ]
        extracted=[
            {'canonical_name':'ロイヤルマッチ(StepUp)','evidence_indexes':[0]},
            {'canonical_name':'ロイヤルマッチ','evidence_indexes':[1]},
        ]
        rows=mod.score_candidates(extracted,items,[])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['sourceCount'],1)
        self.assertEqual(rows[0]['mentionCount'],1)
        self.assertEqual(rows[0]['confidence'],45)

    def test_batch_local_indexes_are_remapped_to_global_units(self):
        items=[]
        for i in range(3):
            items.append({'sourceId':f's{i}','sourceType':'point_site','title':str(i),'description':'',
                          'url':f'https://s{i}.example/x','text':'x'*2500})
        calls=[]
        def fake_batch(gem,batch,known):
            calls.append([x['sourceId'] for x in batch])
            return [{'canonical_name':f'Game {batch[0]["sourceId"]}','evidence_indexes':[0]}]
        with patch.object(mod,'_extract_names_batch',side_effect=fake_batch):
            out=mod.extract_names('gem',items,[],{'maxExtractionBatchChars':4000,'maxExtractionBatches':6})
        self.assertEqual(len(calls),3)
        self.assertEqual([x['evidence_indexes'] for x in out],[[0],[1],[2]])

    def test_api_batch_count_is_bounded(self):
        items=[]
        for i in range(20):
            items.append({'sourceId':f's{i}','sourceType':'point_site','title':'x','description':'',
                          'url':f'https://s{i}.example/x','text':'x'*3000})
        with patch.object(mod,'_extract_names_batch',return_value=[]) as call:
            mod.extract_names('gem',items,[],{'maxExtractionBatchChars':4000,'maxExtractionBatches':3})
        self.assertEqual(call.call_count,3)

    def test_live_shape_long_warau_tail_plus_moppy_promotes_without_threshold_change(self):
        cfg={
            'maxResultsPerQuery':8,'extractionChunkChars':4500,'extractionChunkOverlap':300,
            'maxChunksPerResult':6,'maxExtractionBatchChars':5000,'maxExtractionBatches':6,
            'queries':[
                {'id':'x-poikatsu','query':'x','sourceType':'social','includeDomains':['x.com'],'firecrawlFallback':True},
                {'id':'warau-new','query':'x','sourceType':'point_site','includeDomains':['warau.jp'],
                 'directUrls':['https://www.warau.jp/contents/point/category?point_group=2'],'firecrawlFallback':True},
                {'id':'chobirich-new','query':'x','sourceType':'point_site','includeDomains':['chobirich.com'],'firecrawlFallback':True},
                {'id':'moppy-official-games','query':'x','sourceType':'point_site','includeDomains':['pc.moppy.jp'],
                 'directUrls':['https://pc.moppy.jp/poikatsu-lab/4753-1/'],'firecrawlFallback':False},
            ]
        }
        long_warau=('別ゲーム案件\n' * 900) + '\nロイヤルマッチ(StepUp)\n' + ('別案件\n' * 20)
        def fake_direct(item,url):
            text=long_warau if item['id']=='warau-new' else 'おすすめゲーム ロイヤルマッチ 案件情報'
            return {'sourceId':item['id'],'sourceType':item['sourceType'],'title':item['id'],'description':'',
                    'url':mod.safe_direct_url(url),'text':text,'retrieval':'direct_http'}
        def fake_gemini(gem,batch,known):
            rows=[]
            for i,x in enumerate(batch):
                if 'ロイヤルマッチ' in x['text']:
                    title='ロイヤルマッチ(StepUp)' if x['sourceId']=='warau-new' else 'ロイヤルマッチ'
                    rows.append({'canonical_name':title,'evidence_indexes':[i],'confidence':0})
            return rows
        with patch.object(mod,'direct_fetch_seed',side_effect=fake_direct), \
             patch.object(mod,'firecrawl_search',side_effect=RuntimeError('HTTP Error 402: Payment Required')), \
             patch.object(mod,'known_games',return_value=[]), patch.object(mod,'_extract_names_batch',side_effect=fake_gemini):
            out=mod.run('expired','gem',cfg)
        self.assertEqual(out['summary']['failedSources'],2)
        row=next(x for x in out['candidates'] if x['game']=='ロイヤルマッチ')
        self.assertEqual(row['sourceCount'],2)
        self.assertEqual(row['confidence'],80)
        real_cfg=json.loads((ROOT/'config/trend_discovery.json').read_text())
        ok,reasons=promote.promotion_decision(row,real_cfg,known=set())
        self.assertTrue(ok,reasons)

    def test_chunk_cap_prevents_unbounded_long_page_growth(self):
        units=mod.prepare_extraction_items([{
            'sourceId':'warau-new','sourceType':'point_site','title':'Warau','description':'',
            'url':'https://www.warau.jp/list','text':'x\n'*100000,'retrieval':'direct_http'
        }], {'extractionChunkChars':4500,'extractionChunkOverlap':300,'maxChunksPerResult':4})
        self.assertEqual(len(units),4)

if __name__=='__main__': unittest.main()
