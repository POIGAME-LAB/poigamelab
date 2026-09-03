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
    direct.LEGACY_STATUS=tmp_path/'data/refresh_status.json'
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
        'id':'warau','search_domains':['warau.jp','www.warau.jp','ssl.warau.jp'],'mobile':True,
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

def test_same_reward_requires_full_offer_verification(tmp_path, monkeypatch):
    (tmp_path/'config').mkdir()
    (tmp_path/'data').mkdir()

    direct.ROOT=tmp_path
    direct.POLICY=tmp_path/'config/refresh_policy.json'
    direct.TARGETS=tmp_path/'config/game_targets.json'
    direct.SOURCES=tmp_path/'config/point_sources.json'
    direct.PUBLISHED=tmp_path/'data/published_offers.csv'
    direct.STATUS=tmp_path/'data/comparison_refresh_status.json'
    direct.LEGACY_STATUS=tmp_path/'data/refresh_status.json'
    direct.REVIEW=tmp_path/'data/comparison_review_queue.json'

    direct.POLICY.write_text(json.dumps({
        'comparisonSources':['warau'],
        'minimumConfirmedSourcesForComparison':1,
        'games':{'メメントモリ':{'enabled':True,'supplementalSources':[]}}
    },ensure_ascii=False),encoding='utf-8')
    direct.TARGETS.write_text(json.dumps({'games':[{
        'game':'メメントモリ',
        'aliases':['MementoMori'],
        'known_urls_by_source':{'warau':['https://www.warau.jp/contents/point/pointEntrance.php?pl=pc_categoryService&point_id=205975']}
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
            'url':'https://ssl.warau.jp/contents/point/pointEntrance.php?pl=pc_categoryService&point_id=205975',
            'sourceUrl':'https://ssl.warau.jp/contents/point/pointEntrance.php?pl=pc_categoryService&point_id=205975','verified':'true'
        })

    def fake_fetch(url, source, timeout=15, max_bytes=1200000):
        return '<body>メメントモリ Android 累計 12,050 pt</body>', url
    monkeypatch.setattr(direct,'fetch_first_party',fake_fetch)

    assert direct.main()==0
    rows=list(csv.DictReader(direct.PUBLISHED.open(encoding='utf-8')))
    assert rows[0]['reward']=='12050'
    assert rows[0]['updatedAt'] == '2026-09-01'
    status=json.loads(direct.STATUS.read_text(encoding='utf-8'))
    assert status['apiCalls']==0
    assert status['refreshedRows']==0
    review=json.loads(direct.REVIEW.read_text())['items']
    assert [x['reason'] for x in review] == ['offer_terms_review_required']

def test_offer_identity_ignores_warau_host_and_navigation_params():
    a=direct.offer_identity_key(
        'https://ssl.warau.jp/contents/point/pointEntrance.php?pl=pc_categoryService&point_id=205975',
        'warau'
    )
    b=direct.offer_identity_key(
        'https://www.warau.jp/contents/point/pointEntrance.php?page=2&point_id=205975&sort=relation',
        'warau'
    )
    assert a==b=='warau:point_id:205975'


# Each scenario owns every output path, regardless of test execution order.
import io
from email.message import Message
from urllib.request import HTTPHandler, build_opener
from urllib.response import addinfourl

import pytest


@pytest.fixture(autouse=True)
def isolate_module_paths(tmp_path, monkeypatch):
    for name in ('ROOT', 'POLICY', 'TARGETS', 'SOURCES', 'PUBLISHED', 'STATUS', 'LEGACY_STATUS', 'REVIEW'):
        monkeypatch.setattr(direct, name, tmp_path if name == 'ROOT' else tmp_path / getattr(direct, name).name)


def test_external_redirect_is_blocked_before_destination_request(monkeypatch):
    requested = []

    class FakeHTTP(HTTPHandler):
        def http_open(self, req):
            requested.append(req.full_url)
            headers = Message()
            redirect = req.full_url == 'http://example.test/offer'
            if redirect:
                headers['Location'] = 'http://outside.invalid/private'
            response = addinfourl(io.BytesIO(b''), headers, req.full_url, 302 if redirect else 200)
            response.msg = 'Found' if redirect else 'OK'
            return response

    monkeypatch.setattr(direct, 'build_opener', lambda guard: build_opener(FakeHTTP(), guard), raising=False)
    monkeypatch.setattr(direct, 'urlopen', build_opener(FakeHTTP()).open, raising=False)
    with pytest.raises(ValueError, match='redirect left'):
        direct.fetch_first_party('http://example.test/offer', {'search_domains': ['example.test']})
    assert requested == ['http://example.test/offer']


def test_allowed_redirect_and_oversized_response(monkeypatch):
    requested = []

    class FakeHTTP(HTTPHandler):
        def http_open(self, req):
            requested.append(req.full_url)
            headers = Message()
            redirect = req.full_url.endswith('/start')
            if redirect:
                headers['Location'] = 'http://example.test/detail'
            response = addinfourl(io.BytesIO(b'' if redirect else b'12345'), headers,
                                  req.full_url, 302 if redirect else 200)
            response.msg = 'Found' if redirect else 'OK'
            return response

    monkeypatch.setattr(direct, 'build_opener', lambda guard: build_opener(FakeHTTP(), guard), raising=False)
    monkeypatch.setattr(direct, 'urlopen', build_opener(FakeHTTP()).open, raising=False)
    source = {'search_domains': ['example.test']}
    assert direct.fetch_first_party('http://example.test/start', source, max_bytes=5) == (
        '12345', 'http://example.test/detail')
    assert len(requested) == 2
    with pytest.raises(ValueError, match='incomplete evidence'):
        direct.fetch_first_party('http://example.test/detail', source, max_bytes=4)


@pytest.fixture
def refresh_case(tmp_path):
    source = {'id': 'warau', 'search_domains': ['example.test'],
              'direct_listing_urls': ['https://example.test/list', 'https://example.test/unused'],
              'direct_listing_limit': 1, 'direct_detail_limit': 2}
    direct.POLICY.write_text(json.dumps({'comparisonSources': ['warau'],
        'games': {'Game A': {'enabled': True}, 'Game B': {'enabled': True}}}))
    direct.TARGETS.write_text(json.dumps({'games': [
        {'game': game, 'known_urls_by_source': {'warau': [
            f'https://example.test/detail?id={n}' for n in range(5)]}}
        for game in ('Game A', 'Game B')]}))
    direct.SOURCES.write_text(json.dumps({'sources': [source]}))
    row = dict.fromkeys(direct.FIELDS, '')
    row.update(offerKey='a', game='Game A', site='warau', reward='100',
               condition='Original condition', platform='iOS', updatedAt='2026-01-01',
               url='https://example.test/detail?id=0', verified='true')
    direct.write_published([row])
    return direct.PUBLISHED.read_bytes()


@pytest.mark.parametrize('failed', [False, True])
def test_request_limits_and_cross_game_cache(refresh_case, monkeypatch, failed):
    requested = []

    def fake_fetch(url, source):
        requested.append(url)
        if failed:
            raise TimeoutError('simulated timeout')
        return '<body>Game A Game B 累計 200 pt</body>', url

    monkeypatch.setattr(direct, 'fetch_first_party', fake_fetch)
    assert direct.main() == 0
    assert requested == ['https://example.test/list', 'https://example.test/detail?id=0',
                         'https://example.test/detail?id=1']
    assert direct.PUBLISHED.read_bytes() == refresh_case
    review = json.loads(direct.REVIEW.read_text())['items']
    assert sum(x['reason'] == 'detail_limit_reached' for x in review) == 2
    assert all(x['deferredCount'] == 3 for x in review if x['reason'] == 'detail_limit_reached')
    status = json.loads(direct.STATUS.read_text())
    assert status['refreshedRows'] == 0
    assert status['publishedRewardChanges'] == 0
    assert all(not game['comparisonReady'] for game in status['games'])
    if failed:
        assert sum(x['reason'] == 'fetch_failed' for x in review) == 4


@pytest.mark.parametrize('page', [
    'Game A iOS 累計 100 pt Original condition',
    'Game A Android 累計 100 pt Original condition',
    'Game A iOS Android 累計 100 pt Original condition',
    'Game A 累計 100 pt Original condition',
    'Game A iOS 累計 100 ポイント 2ポイント＝1円 Original condition',
    'Game A iOS 累計 100 円 Changed condition',
    'Game A iOS 累計 100 円 Original condition 期限変更：10日以内',
    'Game A iOS 累計 100 円 Original condition 掲載終了',
    'Game A iOS 累計 100 円 Original condition',
    '<h1>Game B iOS 累計 100 円</h1><aside>おすすめ Game A</aside>',
])
@pytest.mark.parametrize('verified', ['true', 'false'])
def test_page_wide_match_never_refreshes_or_promotes(refresh_case, monkeypatch, page, verified):
    rows = direct.read_published()
    rows[0]['verified'] = verified
    direct.write_published(rows)
    before = direct.PUBLISHED.read_bytes()
    monkeypatch.setattr(direct, 'fetch_first_party', lambda url, source: (page, url))
    def unexpected_write(rows):
        pytest.fail('Discovery-only run must not attempt a publication write')
    monkeypatch.setattr(direct, 'write_published', unexpected_write)
    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == before
    status = json.loads(direct.STATUS.read_text())
    assert status['refreshedRows'] == status['publishedRewardChanges'] == 0
    for game in status['games']:
        assert game['standardConfirmed'] == 0
        assert game['comparisonReady'] is False
        assert all(source['confirmedOffers'] == source['updatedRows'] == 0 for source in game['sources'])
    legacy = json.loads(direct.LEGACY_STATUS.read_text())
    assert all(result['publishableCount'] == 0 and result['collectionComplete'] is False
               for result in legacy['results'])
    reviews = json.loads(direct.REVIEW.read_text())['items']
    matching = [item for item in reviews if item['reason'] == 'offer_terms_review_required']
    assert len(matching) == 1
    assert matching[0]['game'] == 'Game A'
    assert set(matching[0]['requiredChecks']) == {
        'offer_identity', 'reward_unit', 'platform', 'achievement_conditions', 'deadline', 'availability'}


def test_missing_target_does_not_refresh_or_create_offer(refresh_case, monkeypatch):
    monkeypatch.setattr(direct, 'fetch_first_party', lambda url, source: (
        '<h1>Unrelated game iOS 累計 100 円</h1>', url))
    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == refresh_case
    reviews = json.loads(direct.REVIEW.read_text())['items']
    assert sum(item['reason'] == 'target_not_confirmed' for item in reviews) == 4
    assert not any(item['reason'] == 'unpublished_offer_found' for item in reviews)
