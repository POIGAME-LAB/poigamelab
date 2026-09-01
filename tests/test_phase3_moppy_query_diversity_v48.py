import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('probe_v48', ROOT/'scripts'/'firecrawl_township_probe.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
SOURCE={"id":"moppy","name":"モッピー","start_url":"https://pc.moppy.jp/category/list.php","search_domains":["moppy.jp","pc.moppy.jp"],"direct_detail_url_hints":["ad/detail.php"]}
ALIASES=["ホワイトアウト・サバイバル"]

def setup_module():
    m.CURRENT_TARGET={"game":"ホワイトアウト・サバイバル","aliases":ALIASES}

def test_second_query_recovers_when_first_query_misses():
    calls=[]
    def search(q):
        calls.append(q)
        if len(calls)==1: return {"results":[]}
        return {"results":[{"url":"https://pc.moppy.jp/ad/detail.php?site_id=160375&utm_source=x"}]}
    def fetch(url, source):
        return '<h1>ホワイトアウト・サバイバル（StepUp） Android</h1><p>6119P</p>', {"status":200}
    c,d=m.tavily_official_detail_discovery(SOURCE,ALIASES,api_key='x',searcher=search,fetcher=fetch)
    assert len(c)==1 and 'site_id=160375' in m.offer_identity_url(c[0]['url'])
    assert d['queryAttempts']==2 and d['confirmed']==1
    assert len(calls)==2

def test_stops_after_first_verified_result_to_bound_api_calls():
    calls=[]
    def search(q):
        calls.append(q); return {"results":[{"url":"https://pc.moppy.jp/ad/detail.php?site_id=1"}]}
    def fetch(url, source): return '<h1>ホワイトアウト・サバイバル</h1>', {"status":200}
    c,d=m.tavily_official_detail_discovery(SOURCE,ALIASES,api_key='x',searcher=search,fetcher=fetch)
    assert len(c)==1 and len(calls)==1 and d['queryAttempts']==1

def test_stale_404_then_later_query_can_recover():
    calls=[]
    def search(q):
        calls.append(q)
        sid='old' if len(calls)==1 else 'new'
        return {"results":[{"url":f"https://pc.moppy.jp/ad/detail.php?site_id={sid}"}]}
    def fetch(url, source):
        if 'old' in url: raise RuntimeError('HTTP Error 404: Not Found')
        return '<h1>ホワイトアウト・サバイバル iOS</h1>', {"status":200}
    c,d=m.tavily_official_detail_discovery(SOURCE,ALIASES,api_key='x',searcher=search,fetcher=fetch)
    assert len(c)==1 and d['queryAttempts']==2
    assert d['details'][0]['ok'] is False and d['details'][1]['targetFound'] is True

def test_external_and_duplicate_urls_never_become_evidence():
    calls=[]; fetched=[]
    def search(q):
        calls.append(q)
        if len(calls)==1:
            return {"results":[
                {"url":"https://evil.example/ad/detail.php?site_id=9"},
                {"url":"https://pc.moppy.jp/ad/detail.php?site_id=7&utm_source=a"},
            ]}
        return {"results":[{"url":"https://pc.moppy.jp/ad/detail.php?site_id=7&utm_source=b"}]}
    def fetch(url, source):
        fetched.append(url); return '<h1>別ゲーム</h1>', {"status":200}
    c,d=m.tavily_official_detail_discovery(SOURCE,ALIASES,api_key='x',searcher=search,fetcher=fetch)
    assert c==[] and len(fetched)==1 and d['eligibleUrls']==1
    assert d['queryAttempts']==3

def test_snippet_target_is_never_evidence_and_all_variants_can_cleanly_miss():
    def search(q): return {"results":[{"url":"https://pc.moppy.jp/ad/detail.php?site_id=8","title":"ホワイトアウト・サバイバル","content":"6119P"}]}
    def fetch(url, source): return '<h1>別ゲーム</h1>', {"status":200}
    c,d=m.tavily_official_detail_discovery(SOURCE,ALIASES,api_key='x',searcher=search,fetcher=fetch)
    assert c==[] and d['confirmed']==0 and d['searchCompleted'] is True
    assert d['queryAttempts']==3

def test_all_query_failures_remain_fail_closed():
    def search(q): raise RuntimeError('network down')
    c,d=m.tavily_official_detail_discovery(SOURCE,ALIASES,api_key='x',searcher=search)
    assert c==[] and d['searchCompleted'] is False
    assert d['queryAttempts']==3 and len(d['queryErrors'])==3

def test_partial_query_failure_without_candidate_is_not_clean_negative():
    calls=[]
    def search(q):
        calls.append(q)
        if len(calls)==1: return {"results":[]}
        raise RuntimeError('timeout')
    c,d=m.tavily_official_detail_discovery(SOURCE,ALIASES,api_key='x',searcher=search)
    assert c==[] and d['searchCompleted'] is False and d['queryErrors']

def test_v48_research_version_bumped():
    text=(ROOT/'config'/'trend_discovery.json').read_text()
    assert 'V48-moppy-indexed-query-diversity' in text
