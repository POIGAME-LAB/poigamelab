import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('probe_v44', ROOT/'scripts'/'firecrawl_township_probe.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

SOURCE={"id":"moppy","name":"モッピー","start_url":"https://pc.moppy.jp/category/list.php","search_domains":["moppy.jp","pc.moppy.jp"],"direct_detail_url_hints":["ad/detail.php"]}
ALIASES=["ホワイトアウト・サバイバル"]

def test_indexed_discovery_requires_direct_target_confirmation():
    def search(_q):
        return {"results":[
            {"url":"https://pc.moppy.jp/ad/detail.php?site_id=111&utm_source=x"},
            {"url":"https://pc.moppy.jp/ad/detail.php?site_id=222"},
            {"url":"https://evil.example/ad/detail.php?site_id=333"},
        ]}
    def fetch(url, source):
        if '111' in url:
            return '<h1>ホワイトアウト・サバイバル（StepUp）【iOS】</h1><p>123P 条件</p>', {"status":200}
        return '<h1>別ゲーム</h1><p>99999P</p>', {"status":200}
    m.CURRENT_TARGET={"game":"ホワイトアウト・サバイバル","aliases":ALIASES}
    cs,d=m.tavily_official_detail_discovery(SOURCE,ALIASES,api_key='x',fetcher=fetch,searcher=search)
    assert len(cs)==1
    assert m.offer_identity_url(cs[0]['url']).endswith('site_id=111')
    assert d['resultUrls']==3 and d['eligibleUrls']==2 and d['confirmed']==1

def test_indexed_discovery_skips_without_key():
    cs,d=m.tavily_official_detail_discovery(SOURCE,ALIASES,api_key='')
    assert cs==[] and d['attempted'] is False and 'skipped' in d

def test_identity_preserves_moppy_site_id_and_drops_tracking():
    u=m.offer_identity_url('https://pc.moppy.jp/ad/detail.php?site_id=160371&utm_source=abc&track_ref=nw')
    assert 'site_id=160371' in u
    assert 'utm_source' not in u and 'track_ref' not in u

def test_search_snippet_cannot_become_candidate_when_detail_mismatches():
    def search(_q):
        return {"results":[{"url":"https://pc.moppy.jp/ad/detail.php?site_id=999","title":"ホワイトアウト・サバイバル 99999P","content":"ホワイトアウト・サバイバル"}]}
    def fetch(url, source): return '<h1>別ゲーム</h1>', {"status":200}
    m.CURRENT_TARGET={"game":"ホワイトアウト・サバイバル","aliases":ALIASES}
    cs,d=m.tavily_official_detail_discovery(SOURCE,ALIASES,api_key='x',fetcher=fetch,searcher=search)
    assert cs==[] and d['confirmed']==0

def test_workflow_wires_optional_tavily_secret():
    text=(ROOT/'.github'/'workflows'/'discover-trending-games.yml').read_text()
    assert 'TAVILY_API_KEY: ${{ secrets.TAVILY_API_KEY }}' in text
