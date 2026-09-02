import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('v53', ROOT/'scripts'/'build_poi_guide_draft.py')
v53 = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(v53)


def decisions(rows=None):
    return {'phase':'PHASE4_GUIDE_CLAIM_GATE_V51','decisions': rows or []}


def supported(claim='市場では商品をコインで買うことができる', category='tip', game='Township', urls=None):
    return {
        'game':game,'category':category,'claim':claim,'status':'supported_quarantine',
        'sourceUrls':urls or ['https://a.example/guide','https://b.example/guide'],
        'independentSourceCount':2,'officialSourceCount':0,'publicationEligible':False,
    }


def claims_doc(rows=None):
    claims=[]
    for row in rows or []:
        if row.get('status')!='supported_quarantine':
            continue
        urls=row.get('sourceUrls') or ['https://a.example/guide','https://b.example/guide']
        for i,url in enumerate(urls):
            claims.append({
                'game':row['game'],'category':row['category'],'claim':row['claim'],
                'evidenceQuote':row['claim'],'url':url,
                'sourceType':'official' if i==0 and row.get('officialSourceCount') else 'community_guide',
                'status':'validated_quarantine',
            })
    return {'phase':'PHASE4_GUIDE_CLAIMS_CORROBORATED_V52','claims':claims}


def targets():
    return {'games':[{'game':'Township','aliases':['Township','タウンシップ']}]}


def cfg(**overrides):
    base={
        'maxGamesPerRun':1,'maxPoiXSearchesPerGame':2,'maxPoiXResultsPerSearch':5,
        'maxPoiXDirectFetchesPerGame':4,
        'xQueryTemplates':['site:x.com "{game}" ゲーム ポイ活','site:x.com "{alias}" ポイ活 達成 日数'],
    }
    base.update(overrides); return base


def html(text):
    return f'<html><body><article>{text}</article></body></html>'


def test_logic_version_and_publication_boundary():
    assert v53.LOGIC_VERSION == 'V53'
    rows=[supported()]; out=v53.run(decisions(rows),claims_doc(rows),cfg(),targets(),'k',searcher=lambda *a:{'results':[]})
    assert out['phase']=='PHASE4_POI_GUIDE_DRAFT_V53'
    assert out['publicationWrites']==0
    assert out['drafts'][0]['publicationEligible'] is False


def test_only_supported_quarantine_can_enter_verified_sections():
    rows=[supported('確定してよい情報','mechanic'),{
        **supported('まだ保留の情報','timeline'), 'status':'held_single_source'
    }]
    out=v53.run(decisions(rows),claims_doc(rows),cfg(),targets(),'k',searcher=lambda *a:{'results':[]})
    texts=[i['text'] for s in out['drafts'][0]['verifiedSections'] for i in s['items']]
    assert texts==['確定してよい情報']
    assert out['supportedClaims'][0]['claim']=='確定してよい情報'


def test_x_query_uses_twitter_x_and_japanese_alias():
    qs=v53.x_queries('Township',['Township','タウンシップ'],cfg())
    assert qs==['site:x.com "Township" ゲーム ポイ活','site:x.com "タウンシップ" ポイ活 達成 日数']


def test_x_status_url_is_strict_and_canonical():
    assert v53.normalize_x_status_url('https://twitter.com/User/status/123?utm_source=x')=='https://x.com/User/status/123'
    assert v53.normalize_x_status_url('https://x.com/User/status/123/photo/1')=='https://x.com/User/status/123'
    assert v53.normalize_x_status_url('https://x.com/search?q=Township')==''
    assert v53.normalize_x_status_url('https://evil.example/User/status/123')==''
    assert v53.normalize_x_status_url('http://127.0.0.1/User/status/123')==''


def test_search_snippet_never_becomes_experience_when_direct_fetch_fails():
    def searcher(*_):
        return {'results':[{'url':'https://x.com/a/status/100','content':'Township ポイ活 10日で達成'}]}
    def fetcher(_):
        raise RuntimeError('blocked')
    rows,diag=v53.collect_x_experiences('Township',['Township','タウンシップ'],cfg(maxPoiXSearchesPerGame=1),'k',searcher,fetcher)
    assert rows==[]
    assert diag['xFetchErrors']==1
    assert diag['xExperienceCandidates']==0


def test_direct_post_requires_target_and_poi_context():
    urls=['https://x.com/a/status/1','https://x.com/b/status/2','https://x.com/c/status/3']
    def searcher(*_): return {'results':[{'url':u} for u in urls]}
    bodies={
        urls[0]:html('Townshipを遊んでいます。今日は晴れ。'),
        urls[1]:html('別ゲームのポイ活案件を10日で達成。'),
        urls[2]:html('Townshipのポイ活案件、レベル条件を達成しました。'),
    }
    rows,diag=v53.collect_x_experiences('Township',['Township','タウンシップ'],cfg(maxPoiXSearchesPerGame=1),'k',searcher,lambda u:(bodies[u],{'httpStatus':200}))
    assert len(rows)==1 and rows[0]['url'].endswith('/c/status/3')
    assert rows[0]['usableAsFactualClaim'] is False
    assert diag['xPoiContextMissing']==1
    assert diag['xTargetMissing']==1


def test_one_account_cannot_monopolize_experience_candidates():
    def searcher(*_):
        return {'results':[{'url':'https://x.com/a/status/1'},{'url':'https://x.com/a/status/2'},{'url':'https://x.com/b/status/3'}]}
    def fetcher(u): return html(f'Township ポイ活 案件達成 {u}'),{'httpStatus':200}
    rows,diag=v53.collect_x_experiences('Township',['Township'],cfg(maxPoiXSearchesPerGame=1),'k',searcher,fetcher)
    assert {r['sourceIdentity'] for r in rows}=={'x:a','x:b'}
    assert diag['xDuplicateAccounts']==1


def test_api_and_fetch_bounds_are_hard():
    counter={'search':0,'fetch':0}
    def searcher(*_):
        counter['search']+=1
        return {'results':[{'url':f'https://x.com/u{i}/status/{counter["search"]}{i}'} for i in range(8)]}
    def fetcher(u):
        counter['fetch']+=1
        return html('Township ポイ活 案件 達成'),{'httpStatus':200}
    rows,diag=v53.collect_x_experiences('Township',['Township'],cfg(maxPoiXSearchesPerGame=2,maxPoiXDirectFetchesPerGame=4,maxPoiXResultsPerSearch=8),'k',searcher,fetcher)
    assert counter['search']==2==diag['xSearchCalls']
    assert counter['fetch']==4==diag['xDirectFetches']
    assert len(rows)<=4


def test_malformed_search_response_is_visible_and_fail_closed():
    rows,diag=v53.collect_x_experiences('Township',['Township'],cfg(maxPoiXSearchesPerGame=1),'k',lambda *_:{'oops':1},lambda *_:None)
    assert rows==[]
    assert diag['xMalformedSearchResponses']==1
    assert diag['xDirectFetches']==0


def test_draft_is_explicitly_poikatsu_and_reports_research_gaps():
    rows=[
        supported('市場では商品をコインで買うことができる','tip'),
        supported('畑の収穫量を2倍にする','mechanic'),
    ]
    out=v53.run(decisions(rows),claims_doc(rows),cfg(),targets(),'k',searcher=lambda *a:{'results':[]})
    draft=out['drafts'][0]
    assert 'ポイ活攻略' in draft['title']
    assert 'ポイ活案件' in draft['purpose']
    assert '案件条件' in draft['researchGaps']
    assert '達成日数' in ' '.join(draft['researchGaps'])
    assert draft['draftReady'] is False


def test_draft_ready_requires_condition_timeline_priority_and_bottleneck_coverage():
    rows=[
        supported('案件条件はレベル20到達','requirement'),
        supported('20日以内に達成する','timeline'),
        supported('ヘリ注文を優先する','priority'),
        supported('コイン不足に注意する','warning'),
    ]
    out=v53.run(decisions(rows),claims_doc(rows),cfg(),targets(),'k',searcher=lambda *a:{'results':[]})
    draft=out['drafts'][0]
    assert draft['researchGaps']==[]
    assert draft['draftReady'] is True



def test_x_research_completion_is_visible_when_search_errors():
    rows=[
        supported('案件条件はレベル20到達','requirement'),
        supported('20日以内に達成する','timeline'),
        supported('ヘリ注文を優先する','priority'),
        supported('コイン不足に注意する','warning'),
    ]
    def broken(*_): raise RuntimeError('search down')
    out=v53.run(decisions(rows),claims_doc(rows),cfg(),targets(),'k',searcher=broken)
    draft=out['drafts'][0]
    assert draft['researchGaps']==[]
    assert draft['xTwitterResearch']['complete'] is False
    assert draft['draftReady'] is False

def test_numbers_from_x_never_enter_verified_claims():
    def searcher(*_): return {'results':[{'url':'https://x.com/a/status/1'}]}
    def fetcher(_): return html('Township ポイ活 Lv50を16日で達成した'),{'httpStatus':200}
    rows=[supported('市場では商品をコインで買える','tip')]; out=v53.run(decisions(rows),claims_doc(rows),cfg(maxPoiXSearchesPerGame=1),targets(),'k',searcher,fetcher)
    verified=' '.join(i['text'] for s in out['drafts'][0]['verifiedSections'] for i in s['items'])
    assert '16' not in verified and '50' not in verified
    assert '16日' in out['xExperiences'][0]['excerpt']
    assert out['xExperiences'][0]['usableAsFactualClaim'] is False


def test_wrong_corroborated_phase_fails_before_search():
    called={'n':0}
    def searcher(*_): called['n']+=1; return {'results':[]}
    try:
        v53.run(decisions([supported()]),{'phase':'WRONG'},cfg(),targets(),'k',searcher=searcher)
        assert False, 'expected RuntimeError'
    except RuntimeError as exc:
        assert 'phase mismatch' in str(exc)
    assert called['n']==0


def test_missing_api_key_is_fail_visible_before_search():
    try:
        rows=[supported()]; v53.run(decisions(rows),claims_doc(rows),cfg(),targets(),'',searcher=lambda *a:{'results':[]})
        assert False, 'expected RuntimeError'
    except RuntimeError as exc:
        assert 'TAVILY_API_KEY unavailable' in str(exc)



def test_stale_supported_decision_without_corroborated_evidence_is_not_used():
    row=supported('古い判定だけに存在する情報','tip')
    out=v53.run(decisions([row]),claims_doc([]),cfg(),targets(),'k',searcher=lambda *a:{'results':[]})
    assert out['supportedClaims']==[]
    assert out['drafts'][0]['verifiedSections']==[]


def test_x_fetch_budget_is_balanced_across_query_variants():
    calls=[]
    def searcher(query,*_):
        if 'Township' in query:
            return {'results':[{'url':f'https://x.com/en{i}/status/{100+i}'} for i in range(5)]}
        return {'results':[{'url':f'https://x.com/ja{i}/status/{200+i}'} for i in range(5)]}
    def fetcher(url):
        calls.append(url)
        return html('Township タウンシップ ポイ活 案件達成'),{'httpStatus':200}
    v53.collect_x_experiences('Township',['Township','タウンシップ'],cfg(maxPoiXDirectFetchesPerGame=4),'k',searcher,fetcher)
    assert len(calls)==4
    assert any('/en' in u for u in calls)
    assert any('/ja' in u for u in calls)

def test_status_summary_counts_real_search_calls_and_zero_publication():
    rows=[supported()]; out=v53.run(decisions(rows),claims_doc(rows),cfg(maxPoiXSearchesPerGame=2),targets(),'k',searcher=lambda *a:{'results':[]})
    s=v53.summarize(out)
    assert s['logicVersion']=='V53'
    assert s['xSearchCalls']==2 and s['apiCalls']==2
    assert s['publicationWrites']==0


def test_direct_x_meta_description_fallback_is_accepted():
    def searcher(*_):
        return {'results':[{'url':'https://x.com/metauser/status/900'}]}

    raw = (
        '<html><head>'
        '<meta property="og:description" '
        'content="Township \u30dd\u30a4\u6d3b 4\u65e5\u76ee Lv16 \u6848\u4ef6\u6311\u6226\u4e2d">'
        '</head><body>X shell only</body></html>'
    )

    rows, diag = v53.collect_x_experiences(
        'Township',
        ['Township', '\u30bf\u30a6\u30f3\u30b7\u30c3\u30d7'],
        cfg(maxPoiXSearchesPerGame=1),
        'k',
        searcher,
        lambda _:(raw, {'httpStatus':200}),
    )

    assert len(rows) == 1
    assert rows[0]['sourceIdentity'] == 'x:metauser'
    assert '4\u65e5\u76ee' in rows[0]['excerpt']
    assert 'Lv16' in rows[0]['excerpt']
    assert diag['xMetaDescriptionFallbacks'] == 1
    assert diag['xTargetMissing'] == 0
    assert diag['xPoiContextMissing'] == 0


def test_x_metadata_does_not_combine_partial_signals_across_lanes():
    def searcher(*_):
        return {'results':[{'url':'https://x.com/split/status/901'}]}

    raw = (
        '<html><head>'
        '<meta name="twitter:description" '
        'content="\u30dd\u30a4\u6d3b 4\u65e5\u76ee Lv16 \u6848\u4ef6\u6311\u6226\u4e2d">'
        '</head><body>Township only</body></html>'
    )

    rows, diag = v53.collect_x_experiences(
        'Township',
        ['Township'],
        cfg(maxPoiXSearchesPerGame=1),
        'k',
        searcher,
        lambda _:(raw, {'httpStatus':200}),
    )

    assert rows == []
    assert diag['xMetaDescriptionFallbacks'] == 0
    assert diag['xPoiContextMissing'] == 1


def test_x_meta_parser_accepts_attribute_order_and_decodes_entities():
    raw = (
        '<html><head>'
        '<meta content="Township &amp; \u30dd\u30a4\u6d3b 2\u65e5\u76ee Lv57" '
        'name="twitter:description">'
        '</head></html>'
    )
    text, source = v53.x_direct_post_text(raw, ['Township'])
    assert source == 'meta'
    assert 'Township & \u30dd\u30a4\u6d3b' in text
    assert '2\u65e5\u76ee' in text
    assert 'Lv57' in text
