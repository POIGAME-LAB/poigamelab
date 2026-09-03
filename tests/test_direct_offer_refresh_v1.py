import csv, importlib.util, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('direct',ROOT/'scripts/direct_offer_refresh.py')
direct=importlib.util.module_from_spec(spec); spec.loader.exec_module(direct)

def test_reward_change_is_review_only_not_auto_publish(tmp_path, monkeypatch):
    (tmp_path/'config').mkdir()
    (tmp_path/'data').mkdir()

    direct.ROOT=tmp_path
    direct.POLICY=tmp_path/'config/refresh_policy.json'
    direct.TARGETS=tmp_path/'config/game_targets.json'
    direct.SOURCES=tmp_path/'config/point_sources.json'
    direct.PUBLISHED=tmp_path/'data/published_offers.csv'
    direct.STATUS=tmp_path/'data/comparison_refresh_status.json'
    direct.REVIEW=tmp_path/'data/comparison_review_queue.json'

    direct.POLICY.write_text(json.dumps({
        'comparisonSources':['warau'],
        'minimumConfirmedSourcesForComparison':1,
        'games':{'ホワイトアウト・サバイバル':{'enabled':True,'supplementalSources':[]}}
    },ensure_ascii=False),encoding='utf-8')
    direct.TARGETS.write_text(json.dumps({'games':[{
        'game':'ホワイトアウト・サバイバル',
        'aliases':['Whiteout Survival'],
        'known_urls_by_source':{'warau':['https://www.warau.jp/detail?id=1']}
    }]},ensure_ascii=False),encoding='utf-8')
    direct.SOURCES.write_text(json.dumps({'sources':[{
        'id':'warau','search_domains':['warau.jp','www.warau.jp'],'mobile':True,
        'direct_listing_urls':[],'direct_detail_url_hints':['/detail']
    }]},ensure_ascii=False),encoding='utf-8')

    with direct.PUBLISHED.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=direct.FIELDS,lineterminator='\n')
        w.writeheader()
        w.writerow({
            'offerKey':'k','game':'ホワイトアウト・サバイバル','site':'warau',
            'provider':'','reward':'11500','condition':'ok','platform':'iOS',
            'type':'StepUp','deadline':'','updatedAt':'2026-09-01',
            'url':'https://www.warau.jp/detail?id=1',
            'sourceUrl':'https://www.warau.jp/detail?id=1','verified':'true'
        })

    def fake_fetch(url, source, timeout=15, max_bytes=1200000):
        return '<body>ホワイトアウト・サバイバル iOS 累計 12,500 pt</body>', url
    monkeypatch.setattr(direct,'fetch_first_party',fake_fetch)

    assert direct.main()==0
    rows=list(csv.DictReader(direct.PUBLISHED.open(encoding='utf-8')))
    assert rows[0]['reward']=='11500'
    review=json.loads(direct.REVIEW.read_text(encoding='utf-8'))['items']
    assert any(x['reason']=='reward_change_candidate' for x in review)
    status=json.loads(direct.STATUS.read_text(encoding='utf-8'))
    assert status['apiCalls']==0
    assert status['publishedRewardChanges']==0

def test_same_reward_refreshes_freshness(tmp_path, monkeypatch):
    (tmp_path/'config').mkdir()
    (tmp_path/'data').mkdir()

    direct.ROOT=tmp_path
    direct.POLICY=tmp_path/'config/refresh_policy.json'
    direct.TARGETS=tmp_path/'config/game_targets.json'
    direct.SOURCES=tmp_path/'config/point_sources.json'
    direct.PUBLISHED=tmp_path/'data/published_offers.csv'
    direct.STATUS=tmp_path/'data/comparison_refresh_status.json'
    direct.REVIEW=tmp_path/'data/comparison_review_queue.json'

    direct.POLICY.write_text(json.dumps({
        'comparisonSources':['warau'],
        'minimumConfirmedSourcesForComparison':1,
        'games':{'メメントモリ':{'enabled':True,'supplementalSources':[]}}
    },ensure_ascii=False),encoding='utf-8')
    direct.TARGETS.write_text(json.dumps({'games':[{
        'game':'メメントモリ',
        'aliases':['MementoMori'],
        'known_urls_by_source':{'warau':['https://www.warau.jp/detail?id=2']}
    }]},ensure_ascii=False),encoding='utf-8')
    direct.SOURCES.write_text(json.dumps({'sources':[{
        'id':'warau','search_domains':['warau.jp','www.warau.jp'],'mobile':True,
        'direct_listing_urls':[],'direct_detail_url_hints':['/detail']
    }]},ensure_ascii=False),encoding='utf-8')

    with direct.PUBLISHED.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=direct.FIELDS,lineterminator='\n')
        w.writeheader()
        w.writerow({
            'offerKey':'m','game':'メメントモリ','site':'warau','provider':'',
            'reward':'12050','condition':'ok','platform':'Android','type':'StepUp',
            'deadline':'','updatedAt':'2026-09-01',
            'url':'https://www.warau.jp/detail?id=2',
            'sourceUrl':'https://www.warau.jp/detail?id=2','verified':'true'
        })

    def fake_fetch(url, source, timeout=15, max_bytes=1200000):
        return '<body>メメントモリ Android 累計 12,050 pt</body>', url
    monkeypatch.setattr(direct,'fetch_first_party',fake_fetch)

    assert direct.main()==0
    rows=list(csv.DictReader(direct.PUBLISHED.open(encoding='utf-8')))
    assert rows[0]['reward']=='12050'
    assert rows[0]['updatedAt'] != '2026-09-01'
    status=json.loads(direct.STATUS.read_text(encoding='utf-8'))
    assert status['apiCalls']==0
    assert status['refreshedRows']==1
