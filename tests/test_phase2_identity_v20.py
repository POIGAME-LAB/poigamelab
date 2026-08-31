import importlib.util, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('probe',ROOT/'scripts/firecrawl_township_probe.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

CFG=json.loads((ROOT/'config/point_sources.json').read_text())

def candidate(site_id,site,url,markdown):
    return {'source_id':site_id,'source_name':site,'url':url,'markdown':markdown,'kind':'test'}

def offer(site,url,evidence,reward,platform='Android',condition='新規インストール後、StepUpミッションをクリア'):
    return {'site':site,'url':url,'evidence_urls':[evidence],'reward_yen':reward,
            'platform':platform,'condition':condition,'reason':'test'}

def test_cross_offer_evidence_is_blocked():
    o=offer('ワラウ',
      'https://ssl.warau.jp/contents/point/pointEntrance.php?point_id=205817',
      'https://ssl.warau.jp/contents/point/pointEntrance.php?point_id=196690',18800)
    v={'offers':[o]}
    cs=[candidate('warau','ワラウ','https://ssl.warau.jp/contents/point/pointEntrance.php?point_id=196690','累計18,800pt')]
    m.apply_deterministic_enrichment(v,cs,CFG)
    assert not o['auto_publish_ready']
    assert o['deterministic_checks']['evidence_same_offer_identity'] is False
    assert o['deterministic_checks']['exact_identity_candidate_present'] is False

def test_same_identity_tracking_params_ok():
    url='https://www.chobirich.com/ad_details/1883822'
    o=offer('ちょびリッチ',url+'?click_id=x',url,3831)
    v={'offers':[o]}
    cs=[candidate('chobirich','ちょびリッチ',url,'最大3,831円相当')]
    m.apply_deterministic_enrichment(v,cs,CFG)
    assert o['auto_publish_ready']
    assert o['reward_yen']==3831

def test_kinoko_clean_four_fastpaths_registered():
    data=json.loads((ROOT/'config/game_targets.json').read_text())
    k=next(x for x in data['games'] if x['game']=='きのこ伝説')
    known=k['known_urls_by_source']
    assert len(known['chobirich'])==3
    assert known['coincome']==[
        'https://cimcome.jp/campaigns/details/10037',
        'https://cimcome.jp/campaigns/details/10038']
    assert known['warau']==[
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205816']

def test_warau_deterministic_amount_uses_exact_identity_only():
    ios='https://www.warau.jp/contents/point/pointEntrance.php?point_id=204643'
    android='https://www.warau.jp/contents/point/pointEntrance.php?point_id=204645'
    o=offer('ワラウ',ios,ios,21670,'iOS','新規インストール後、累計最大16,760pt')
    cs=[
      candidate('warau','ワラウ',ios,'累計最大16,760pt'),
      candidate('warau','ワラウ',android,'累計最大21,670pt')
    ]
    v={'offers':[o]}
    m.apply_deterministic_enrichment(v,cs,CFG)
    assert o['reward_yen']==16760
    assert o['reward_source']=='python_warau_same_identity'
    assert o['auto_publish_ready']

def test_asset_urls_are_filtered_in_source():
    text=(ROOT/'scripts/firecrawl_township_probe.py').read_text()
    assert 'crawlable_detail_url' in text
    assert 'png|jpe?g|gif|webp|svg' in text
