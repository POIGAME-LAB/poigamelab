import importlib.util, json, sys
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('probe', ROOT/'scripts/firecrawl_township_probe.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def cand(src, url, md='Township 累計 21,670pt'):
    return {'source_id':src['id'],'source_name':src['name'],'kind':'known_official_probe','url':url,'title':'Township','description':'','markdown':md,'links':[],'metadata':{'targetFound':True}}

def test_fast_path_skips_search():
    src={'id':'warau','name':'ワラウ','enabled':True,'known_target_urls':['u1','u2'],'prefer_known_pages':True,'known_pages_sufficient':2,'search_domains':['warau.jp']}
    cfg={'target':{'aliases':['Township','タウンシップ']},'sources':[src],'offerwall_domains_discovered':[]}
    known=[cand(src,'https://www.warau.jp/a'),cand(src,'https://www.warau.jp/b')]
    with patch.object(m,'probe_known_pages',return_value=(known,[{'ok':True},{'ok':True}])), patch.object(m,'domain_search') as search, patch.object(m,'direct_scrape') as direct:
        got,diag=m.collect_firecrawl('x',cfg)
    assert len(got)==2 and diag[0]['mode']=='known_official_fast_path'
    search.assert_not_called(); direct.assert_not_called()

def test_discovery_fallback_runs_when_no_known_pages():
    src={'id':'moppy','name':'モッピー','enabled':True,'known_target_urls':[],'prefer_known_pages':False,'search_domains':['moppy.jp']}
    cfg={'target':{'aliases':['Township']},'sources':[src],'offerwall_domains_discovered':[]}
    direct={'source_id':'moppy','source_name':'モッピー','kind':'direct_scrape','url':'https://moppy.jp/','markdown':'','links':[],'metadata':{'targetFound':False}}
    with patch.object(m,'probe_known_pages',return_value=([],[])), patch.object(m,'direct_scrape',return_value=direct), patch.object(m,'domain_search',return_value=[]) as search, patch.object(m,'verify_search_hits',return_value=([],[])), patch.object(m,'follow_candidate_links',return_value=([],[])):
        got,diag=m.collect_firecrawl('x',cfg)
    search.assert_called_once(); assert diag[0]['mode']=='discovery'

def test_warau_reward_recovery_and_gate():
    cfg=json.loads((ROOT/'config/point_sources.json').read_text())
    url='https://www.warau.jp/contents/point/pointEntrance.php?point_id=204645'
    src=next(x for x in cfg['sources'] if x['id']=='warau')
    candidates=[cand(src,url,'Township Android 累計 21,670pt 1pt=1円')]
    v={'offers':[{'site':'ワラウ','reward_yen':None,'condition':'Township StepUp 累計21,670pt','platform':'Android','deadline':'60日以内','url':url,'evidence_urls':[url]}]}
    out=m.apply_deterministic_enrichment(v,candidates,cfg)
    o=out['offers'][0]
    assert o['reward_yen']==21670 and o['reward_source']=='python_warau_same_identity' and o['auto_publish_ready'] is True

def test_bad_offer_never_auto_publishes():
    cfg=json.loads((ROOT/'config/point_sources.json').read_text())
    v={'offers':[{'site':'不明','reward_yen':9999999,'condition':'短い','platform':'','deadline':'','url':'https://evil.example/x','evidence_urls':[]}]}
    out=m.apply_deterministic_enrichment(v,[],cfg)
    assert out['offers'][0]['auto_publish_ready'] is False

def test_coincome_has_both_known_os_pages():
    cfg=json.loads((ROOT/'config/point_sources.json').read_text())
    c=next(x for x in cfg['sources'] if x['id']=='coincome')
    assert set(c['known_target_urls'])=={'https://cimcome.jp/campaigns/details/9857','https://cimcome.jp/campaigns/details/9856'}

def test_regression_four_publishable_offers():
    cfg=json.loads((ROOT/'config/point_sources.json').read_text())
    w=next(x for x in cfg['sources'] if x['id']=='warau'); c=next(x for x in cfg['sources'] if x['id']=='coincome')
    wu1,wu2=w['known_target_urls']; cu1,cu2=c['known_target_urls']
    candidates=[cand(w,wu1,'Township Android 累計 21,670pt 1pt=1円'),cand(w,wu2,'Township iOS 累計 16,760pt 1pt=1円'),cand(c,cu1,'Township Android 33,125円'),cand(c,cu2,'Township iOS 30,025円')]
    v={'offers':[
      {'site':'ワラウ','reward_yen':None,'condition':'Township Android 累計21,670pt','url':wu1,'evidence_urls':[wu1]},
      {'site':'ワラウ','reward_yen':None,'condition':'Township iOS 累計16,760pt','url':wu2,'evidence_urls':[wu2]},
      {'site':'COINCOME','reward_yen':33125,'condition':'Township Android StepUp 条件達成','url':cu1,'evidence_urls':[cu1]},
      {'site':'COINCOME','reward_yen':30025,'condition':'Township iOS StepUp 条件達成','url':cu2,'evidence_urls':[cu2]},
    ]}
    out=m.apply_deterministic_enrichment(v,candidates,cfg)
    assert sum(bool(x['auto_publish_ready']) for x in out['offers'])==4


def test_warau_query_ids_are_distinct_offer_identities():
    a='https://www.warau.jp/contents/point/pointEntrance.php?point_id=204645'
    b='https://www.warau.jp/contents/point/pointEntrance.php?point_id=204643'
    assert m.sanitize_url(a) == m.sanitize_url(b)  # proves why V10 collapsed them
    assert m.offer_identity_url(a) != m.offer_identity_url(b)

def test_collect_keeps_both_warau_query_offers():
    src={'id':'warau','name':'ワラウ','enabled':True,
         'known_target_urls':[
           'https://www.warau.jp/contents/point/pointEntrance.php?point_id=204645',
           'https://www.warau.jp/contents/point/pointEntrance.php?point_id=204643'],
         'prefer_known_pages':True,'known_pages_sufficient':2,'search_domains':['warau.jp']}
    cfg={'target':{'aliases':['Township','タウンシップ']},'sources':[src],'offerwall_domains_discovered':[]}
    known=[cand(src,src['known_target_urls'][0]),cand(src,src['known_target_urls'][1])]
    with patch.object(m,'probe_known_pages',return_value=(known,[{'ok':True},{'ok':True}])):
        got,diag=m.collect_firecrawl('x',cfg)
    assert len(got)==2
    assert {x['url'] for x in got}==set(src['known_target_urls'])

def test_end_to_end_four_offers_survive_collection_ai_and_gate():
    cfg=json.loads((ROOT/'config/point_sources.json').read_text())
    w=next(x for x in cfg['sources'] if x['id']=='warau')
    c=next(x for x in cfg['sources'] if x['id']=='coincome')
    # Keep this focused on the two sources whose stable official detail URLs are known.
    testcfg={'target':cfg['target'],'sources':[w,c],'offerwall_domains_discovered':cfg.get('offerwall_domains_discovered',[])}
    known_map={
      'warau':[cand(w,w['known_target_urls'][0],'Township Android 累計 21,670pt 1pt=1円'),cand(w,w['known_target_urls'][1],'Township iOS 累計 16,760pt 1pt=1円')],
      'coincome':[cand(c,c['known_target_urls'][0],'Township Android 33,125円'),cand(c,c['known_target_urls'][1],'Township iOS 30,025円')],
    }
    def fake_probe(key,src,aliases):
        arr=known_map[src['id']]
        return arr,[{'url':x['url'],'ok':True,'targetFound':True} for x in arr]
    with patch.object(m,'probe_known_pages',side_effect=fake_probe):
        candidates,diag=m.collect_firecrawl('x',testcfg)
    assert len(candidates)==4
    assert sum(x['source_id']=='warau' for x in candidates)==2
    assert sum(x['source_id']=='coincome' for x in candidates)==2

    def fake_ai(key,items):
        offers=[]
        for x in items:
            if x['source_id']=='warau':
                is_android='204645' in x['url']
                offers.append({'site':'ワラウ','reward_yen':None,
                    'condition':'Township Android 累計21,670pt' if is_android else 'Township iOS 累計16,760pt',
                    'platform':'Android' if is_android else 'iOS','deadline':'60日以内','url':x['url'],'evidence_urls':[x['url']]})
            elif x['source_id']=='coincome':
                is_android=x['url'].endswith('/9857')
                offers.append({'site':'COINCOME','reward_yen':33125 if is_android else 30025,
                    'condition':'Township StepUp 条件達成','platform':'Android' if is_android else 'iOS','deadline':'',
                    'url':x['url'],'evidence_urls':[x['url']]})
        return {'game':'Township','offers':offers,'verdict':'ok','needs_human_review':False},'mock-gemini'
    with patch.object(m,'gemini_extract_batch',side_effect=fake_ai):
        verified,models=m.gemini_extract('x',candidates)
    assert len(verified['offers'])==4
    enriched=m.apply_deterministic_enrichment(verified,candidates,testcfg)
    assert sum(bool(x['auto_publish_ready']) for x in enriched['offers'])==4

def test_offer_identity_drops_tracking_but_keeps_public_selector():
    u='https://www.warau.jp/contents/point/pointEntrance.php?point_id=204645&user_id=SECRET&click_id=TRACK&digest=NOPE'
    ident=m.offer_identity_url(u)
    assert 'point_id=204645' in ident
    assert 'SECRET' not in ident and 'TRACK' not in ident and 'NOPE' not in ident


def test_cross_source_evidence_cannot_auto_publish():
    cfg=json.loads((ROOT/'config/point_sources.json').read_text())
    w=next(x for x in cfg['sources'] if x['id']=='warau')['known_target_urls'][0]
    c=next(x for x in cfg['sources'] if x['id']=='coincome')['known_target_urls'][0]
    v={'offers':[{'site':'ワラウ','reward_yen':21670,'condition':'Township Android 累計21,670pt','url':w,'evidence_urls':[c]}]}
    o=m.apply_deterministic_enrichment(v,[],cfg)['offers'][0]
    assert o['auto_publish_ready'] is False

def test_offerwall_cannot_auto_publish_as_first_party():
    cfg=json.loads((ROOT/'config/point_sources.json').read_text())
    u='https://ow.skyflag.jp/some-public-offer'
    v={'offers':[{'site':'モッピー','reward_yen':10000,'condition':'Township StepUp 条件達成','url':u,'evidence_urls':[u]}]}
    o=m.apply_deterministic_enrichment(v,[],cfg)['offers'][0]
    assert o['deterministic_checks']['first_party_registered_source'] is False
    assert o['auto_publish_ready'] is False


def test_collector_never_exceeds_two_parallel_sources(monkeypatch):
    import threading, time
    sources=[]
    for i in range(4):
        sources.append({
            'id':f's{i}','name':f'S{i}','enabled':True,
            'known_target_urls':[f'https://s{i}.example/a'],
            'prefer_known_pages':True,'known_pages_sufficient':1,
            'search_domains':[f's{i}.example']
        })
    testcfg={'target':{'aliases':['Township']},'sources':sources,'offerwall_domains_discovered':[]}
    lock=threading.Lock()
    state={'active':0,'peak':0}
    def fake_probe(key,src,aliases):
        with lock:
            state['active'] += 1
            state['peak']=max(state['peak'],state['active'])
        time.sleep(0.04)
        with lock:
            state['active'] -= 1
        c={'source_id':src['id'],'source_name':src['name'],'kind':'known_official_probe',
           'url':src['known_target_urls'][0],'title':'Township','description':'',
           'markdown':'Township 1000円 条件達成','links':[],'metadata':{'targetFound':True}}
        return [c],[{'ok':True,'targetFound':True}]
    monkeypatch.setenv('FIRECRAWL_SOURCE_WORKERS','2')
    with patch.object(m,'probe_known_pages',side_effect=fake_probe):
        got,diag=m.collect_firecrawl('x',testcfg)
    assert len(got)==4
    assert state['peak']==2

def test_parallel_collector_preserves_config_order(monkeypatch):
    import time
    sources=[
        {'id':'slow','name':'Slow','enabled':True,'known_target_urls':['https://slow.example/a'],
         'prefer_known_pages':True,'known_pages_sufficient':1,'search_domains':['slow.example']},
        {'id':'fast','name':'Fast','enabled':True,'known_target_urls':['https://fast.example/a'],
         'prefer_known_pages':True,'known_pages_sufficient':1,'search_domains':['fast.example']},
    ]
    testcfg={'target':{'aliases':['Township']},'sources':sources,'offerwall_domains_discovered':[]}
    def fake_probe(key,src,aliases):
        if src['id']=='slow': time.sleep(0.05)
        c={'source_id':src['id'],'source_name':src['name'],'kind':'known_official_probe',
           'url':src['known_target_urls'][0],'title':'Township','description':'','markdown':'Township',
           'links':[],'metadata':{'targetFound':True}}
        return [c],[{'ok':True}]
    monkeypatch.setenv('FIRECRAWL_SOURCE_WORKERS','2')
    with patch.object(m,'probe_known_pages',side_effect=fake_probe):
        got,diag=m.collect_firecrawl('x',testcfg)
    assert [d['source_id'] for d in diag]==['slow','fast']
    assert [c['source_id'] for c in got]==['slow','fast']


def test_known_page_cache_avoids_network(tmp_path, monkeypatch):
    src={'id':'warau','name':'ワラウ','known_target_urls':['https://www.warau.jp/contents/point/pointEntrance.php?point_id=204645']}
    c=cand(src,src['known_target_urls'][0])
    monkeypatch.setattr(m,'CACHE_DIR',tmp_path)
    m.save_candidate_cache(src['id'],src['known_target_urls'][0],c)
    monkeypatch.setenv('POIGAMELAB_KNOWN_CACHE_SECONDS','1800')
    with patch.object(m,'direct_scrape') as live:
        got,diag=m.probe_known_pages('x',src,['Township'])
    live.assert_not_called()
    assert len(got)==1 and diag[0]['cache']=='hit'
    assert got[0]['kind']=='known_official_cache'

def test_expired_cache_refreshes_live(tmp_path, monkeypatch):
    import os, time
    src={'id':'warau','name':'ワラウ','known_target_urls':['https://www.warau.jp/contents/point/pointEntrance.php?point_id=204645']}
    c=cand(src,src['known_target_urls'][0])
    monkeypatch.setattr(m,'CACHE_DIR',tmp_path)
    m.save_candidate_cache(src['id'],src['known_target_urls'][0],c)
    p=m.cache_path_for(src['id'],src['known_target_urls'][0])
    old=time.time()-4000
    os.utime(p,(old,old))
    monkeypatch.setenv('POIGAMELAB_KNOWN_CACHE_SECONDS','1800')
    live=cand(src,src['known_target_urls'][0],'Township 累計 22,000pt')
    with patch.object(m,'direct_scrape',return_value=live) as call:
        got,diag=m.probe_known_pages('x',src,['Township'])
    call.assert_called_once()
    assert diag[0]['cache']=='miss'

def test_live_failure_can_use_stale_known_official_cache(tmp_path, monkeypatch):
    import os, time
    src={'id':'warau','name':'ワラウ','known_target_urls':['https://www.warau.jp/contents/point/pointEntrance.php?point_id=204645']}
    c=cand(src,src['known_target_urls'][0])
    monkeypatch.setattr(m,'CACHE_DIR',tmp_path)
    m.save_candidate_cache(src['id'],src['known_target_urls'][0],c)
    p=m.cache_path_for(src['id'],src['known_target_urls'][0])
    old=time.time()-4000
    os.utime(p,(old,old))
    monkeypatch.setenv('POIGAMELAB_KNOWN_CACHE_SECONDS','1800')
    with patch.object(m,'direct_scrape',side_effect=TimeoutError('slow')):
        got,diag=m.probe_known_pages('x',src,['Township'])
    assert len(got)==1
    assert diag[0]['cache']=='stale_fallback'
    assert got[0]['metadata']['staleCacheFallback'] is True


def test_extract_target_adjacent_opaque_detail_link():
    md="""
    ## 人気アプリ
    Township（タウンシップ）
    [詳細を見る](https://www.chobirich.com/smartphone/ad.php?adid=98765)
    12,000pt
    """
    got=m.extract_target_adjacent_links(md,['Township','タウンシップ'])
    assert got==['https://www.chobirich.com/smartphone/ad.php?adid=98765']

def test_target_adjacent_does_not_take_unrelated_link():
    md="""
    Township（タウンシップ）
    12,000pt
    """ + ("x"*900) + """
    [別ゲーム](https://www.chobirich.com/foo?id=999)
    """
    assert m.extract_target_adjacent_links(md,['Township','タウンシップ'])==[]

def test_follow_opaque_target_link_even_without_url_hint():
    src={
      'id':'chobirich','name':'ちょびリッチ',
      'search_domains':['chobirich.com','www.chobirich.com'],
      'mobile':True
    }
    cfg={'offerwall_domains_discovered':[]}
    seed={
      'source_id':'chobirich','source_name':'ちょびリッチ',
      'url':'https://www.chobirich.com/smartphone',
      'markdown':'Township [詳細](https://www.chobirich.com/x.php?x=12345)',
      'description':'','links':[],'metadata':{}
    }
    returned={
      'source_id':'chobirich','source_name':'ちょびリッチ',
      'kind':'direct_scrape','url':'https://www.chobirich.com/x.php?x=12345',
      'title':'Township','description':'','markdown':'Township 12000pt 条件達成',
      'links':[],'metadata':{'targetFound':True}
    }
    with patch.object(m,'direct_scrape',return_value=returned) as call:
        out,diag=m.follow_candidate_links('x',src,[seed],['Township'],cfg,limit=6)
    assert len(out)==1
    assert diag[0]['reason']=='target_adjacent'
    assert out[0]['kind']=='followed_detail'
    call.assert_called_once()

def test_follow_target_link_blocks_external_unregistered_domain():
    src={
      'id':'chobirich','name':'ちょびリッチ',
      'search_domains':['chobirich.com','www.chobirich.com'],
      'mobile':True
    }
    cfg={'offerwall_domains_discovered':[]}
    seed={
      'source_id':'chobirich','source_name':'ちょびリッチ',
      'url':'https://www.chobirich.com/smartphone',
      'markdown':'Township [詳細](https://evil.example/x.php?id=123)',
      'description':'','links':[],'metadata':{}
    }
    with patch.object(m,'direct_scrape') as call:
        out,diag=m.follow_candidate_links('x',src,[seed],['Township'],cfg,limit=6)
    assert out==[]
    assert diag==[]
    call.assert_not_called()


def test_extract_appland_labeled_link():
    md='[アプリランド](https://example-provider.jp/start?user_id=SECRET&x=1)'
    got=m.extract_labeled_links(md,['アプリランド'])
    assert got==['https://example-provider.jp/start?user_id=SECRET&x=1']

def test_provider_hub_discovery_is_source_opt_in():
    src={'provider_hub_labels':['アプリランド'],'provider_url_hints':['skyflag']}
    direct={
      'markdown':'Townshipではない一覧 [アプリランド](https://ow.skyflag.jp/start?user_id=abc)',
      'links':[]
    }
    got=m.discover_provider_hub_links(direct,src)
    assert got==['https://ow.skyflag.jp/start?user_id=abc']
    assert 'user_id=abc' in got[0]  # runtime-only transient URL

def test_provider_hub_persists_sanitized_url(monkeypatch):
    src={'id':'chobirich','name':'ちょびリッチ','provider_hub_labels':['アプリランド']}
    response={'data':{
      'markdown':'Township 12345ポイント 条件達成',
      'links':['https://ow.skyflag.jp/detail?id=10&click_id=SECRET'],
      'metadata':{'title':'アプリランド'}
    }}
    with patch.object(m,'firecrawl_post',return_value=response):
        c=m.scrape_provider_hub('k',src,'https://ow.skyflag.jp/start?user_id=SECRET&digest=ABC',['Township'])
    assert c['metadata']['targetFound'] is True
    assert c['url']=='https://ow.skyflag.jp/start'
    assert 'SECRET' not in json.dumps(c,ensure_ascii=False)
    assert 'digest' not in json.dumps(c,ensure_ascii=False)

def test_provider_hub_candidate_still_cannot_bypass_first_party_gate():
    cfg=json.loads((ROOT/'config/point_sources.json').read_text())
    candidates=[{
      'source_id':'chobirich','source_name':'ちょびリッチ','kind':'provider_hub_scrape',
      'url':'https://ow.skyflag.jp/start','title':'Township','description':'',
      'markdown':'Township 12000円 条件達成','links':[],
      'metadata':{'targetFound':True,'providerHubDomain':'ow.skyflag.jp'}
    }]
    verified={'offers':[{
      'site':'ちょびリッチ','reward_yen':12000,'condition':'条件達成',
      'platform':'Android','deadline':'','url':'https://ow.skyflag.jp/start',
      'evidence_urls':['https://ow.skyflag.jp/start']
    }]}
    out=m.apply_deterministic_enrichment(verified,candidates,cfg)
    assert out['offers'][0]['auto_publish_ready'] is False
    assert out['offers'][0]['deterministic_checks']['first_party_registered_source'] is False


def test_chobirich_verified_detail_promoted_to_known_fast_path():
    cfg=json.loads((ROOT/'config/point_sources.json').read_text())
    ch=next(x for x in cfg['sources'] if x['id']=='chobirich')
    assert ch['prefer_known_pages'] is True
    assert ch['known_pages_sufficient']==1
    assert ch['known_target_urls']==['https://www.chobirich.com/ad_details/1894712']

def test_chobirich_fast_path_skips_broad_discovery():
    cfg=json.loads((ROOT/'config/point_sources.json').read_text())
    candidate={
      'source_id':'chobirich','source_name':'ちょびリッチ','kind':'known_official_probe',
      'url':'https://www.chobirich.com/ad_details/1894712',
      'title':'Township','description':'','markdown':'Township Android 最大31,817円',
      'links':[],'metadata':{'targetFound':True}
    }
    original=m.probe_known_pages
    def fake_known(key,source,aliases):
        if source['id']=='chobirich':
            return [candidate],[{'url':candidate['url'],'ok':True,'targetFound':True,'cache':'miss'}]
        return [],[]
    with patch.object(m,'probe_known_pages',side_effect=fake_known), \
         patch.object(m,'direct_scrape') as direct, \
         patch.object(m,'domain_search') as search:
        candidates,diags=m.collect_firecrawl('k',cfg)
    chdiag=next(x for x in diags if x['source_id']=='chobirich')
    assert chdiag['mode']=='known_official_fast_path'
    assert chdiag['search']['skipped'] is True
    assert any(x['url']==candidate['url'] for x in candidates)
    # Other sources may call discovery, but Chobirich itself must not.
    assert not any(call.args[1]['id']=='chobirich' for call in direct.call_args_list)
    assert not any(call.args[1]['id']=='chobirich' for call in search.call_args_list)

def test_chobirich_known_cache_avoids_firecrawl():
    cfg=json.loads((ROOT/'config/point_sources.json').read_text())
    ch=next(x for x in cfg['sources'] if x['id']=='chobirich')
    cached={
      'source_id':'chobirich','source_name':'ちょびリッチ','kind':'known_official_cache',
      'url':'https://www.chobirich.com/ad_details/1894712',
      'title':'Township','description':'','markdown':'Township Android 最大31,817円',
      'links':[],'metadata':{'targetFound':True}
    }
    with patch.object(m,'load_candidate_cache',return_value=cached), \
         patch.object(m,'firecrawl_post') as net:
        got,diag=m.probe_known_pages('k',ch,['Township'])
    assert len(got)==1
    assert diag[0]['cache']=='hit'
    net.assert_not_called()

def test_five_offer_publication_regression_v17():
    cfg=json.loads((ROOT/'config/point_sources.json').read_text())
    rows=[
      ('ワラウ','https://www.warau.jp/contents/point/pointEntrance.php?point_id=204645','Android',21670),
      ('ワラウ','https://www.warau.jp/contents/point/pointEntrance.php?point_id=204643','iOS',16760),
      ('ちょびリッチ','https://www.chobirich.com/ad_details/1894712','Android',31817),
      ('COINCOME','https://cimcome.jp/campaigns/details/9857','Android',33125),
      ('COINCOME','https://cimcome.jp/campaigns/details/9856','iOS',30025),
    ]
    verified={'offers':[]}; candidates=[]
    for site,url,platform,reward in rows:
        verified['offers'].append({'site':site,'reward_yen':reward,
          'condition':'60日以内にStepUpミッションクリア','platform':platform,
          'deadline':'60日','url':url,'evidence_urls':[url]})
        candidates.append({'source_id':'x','source_name':site,'kind':'known_official_probe',
          'url':url,'title':'Township','description':'','markdown':'Township 条件達成',
          'links':[],'metadata':{'targetFound':True}})
    out=m.apply_deterministic_enrichment(verified,candidates,cfg)
    assert sum(x['auto_publish_ready'] is True for x in out['offers'])==5
