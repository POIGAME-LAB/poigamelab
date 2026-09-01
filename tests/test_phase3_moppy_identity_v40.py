import importlib.util
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod; spec.loader.exec_module(mod); return mod

probe=load('probe_v40',Path('scripts/firecrawl_township_probe.py'))
publisher=load('publisher_v40',Path('scripts/publish_verified_offers.py'))

MOPPY={'id':'moppy','name':'モッピー','search_domains':['moppy.jp','pc.moppy.jp'],'direct_detail_url_hints':['ad/detail.php']}

def test_moppy_site_id_is_stable_offer_identity_and_tracking_is_dropped():
    url='https://pc.moppy.jp/ad/detail.php?site_id=160371&track_ref=nw&utm_source=x'
    expected='https://pc.moppy.jp/ad/detail.php?site_id=160371'
    assert probe.offer_identity_url(url)==expected
    assert publisher.safe_identity_url(url)==expected


def test_moppy_distinct_site_ids_do_not_collapse():
    a='https://pc.moppy.jp/ad/detail.php?site_id=160371&track_ref=a'
    b='https://pc.moppy.jp/ad/detail.php?site_id=160375&track_ref=b'
    assert probe.offer_identity_url(a)!=probe.offer_identity_url(b)
    assert publisher.safe_identity_url(a)!=publisher.safe_identity_url(b)


def test_moppy_site_id_detail_shape_is_accepted_without_target_specific_id():
    assert probe._detail_like_first_party_url('https://pc.moppy.jp/ad/detail.php?site_id=999999&track_ref=x',MOPPY)


def test_moppy_card_context_keeps_two_platform_offer_ids_separate():
    html='''<div class="card"><h3>テストゲーム（StepUp）</h3>
      <a href="/ad/detail.php?site_id=100001&track_ref=ios">iOS</a>
      <a href="/ad/detail.php?site_id=100002&track_ref=android">Android</a></div>'''
    links=probe.target_adjacent_first_party_links(html,'https://pc.moppy.jp/category/list.php',MOPPY,['テストゲーム'])
    assert {probe.offer_identity_url(x) for x in links}=={
      'https://pc.moppy.jp/ad/detail.php?site_id=100001',
      'https://pc.moppy.jp/ad/detail.php?site_id=100002',
    }

def test_adoption_cli_reports_exact_hold_reason_without_urls(tmp_path, capsys):
    adoption=load('adoption_v40',Path('scripts/evaluate_research_adoption.py'))
    payload={
      'game':'テストゲーム','quarantine':True,'autoPublish':False,
      'collectorResult':{
        'health':{'collectionComplete':True,'degradedReasons':[]},
        'verified':{'offers':[{
          'registered_source':'warau','auto_publish_ready':True,
          'deterministic_checks':{k:True for k in adoption.REQUIRED_CHECKS}
        }]}
      }
    }
    results=tmp_path/'results'; results.mkdir(); (results/'game.json').write_text(__import__('json').dumps(payload),encoding='utf-8')
    cfg=tmp_path/'cfg.json'; cfg.write_text('{"minimumVerifiedOffersForAdoption":2,"minimumVerifiedSourcesForAdoption":2}',encoding='utf-8')
    out=tmp_path/'out.json'
    original=adoption.run
    adoption.run=lambda: original(results,out,cfg)
    assert adoption.main()==0
    text=capsys.readouterr().out
    assert 'HOLD' in text
    assert 'insufficient_strict_offers' in text
    assert 'insufficient_verified_sources' in text
    assert 'sources=1 [warau]' in text
    assert 'http' not in text
