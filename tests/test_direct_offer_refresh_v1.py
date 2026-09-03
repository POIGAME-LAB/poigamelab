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
        'comparisonSources':['testsite'],
        'minimumConfirmedSourcesForComparison':1,
        'games':{'ホワイトアウト・サバイバル':{'enabled':True,'supplementalSources':[]}}
    },ensure_ascii=False),encoding='utf-8')
    direct.TARGETS.write_text(json.dumps({'games':[{
        'game':'ホワイトアウト・サバイバル',
        'aliases':['Whiteout Survival'],
        'known_urls_by_source':{'testsite':['https://www.testsite.jp/detail?id=1']}
    }]},ensure_ascii=False),encoding='utf-8')
    direct.SOURCES.write_text(json.dumps({'sources':[{
        'id':'testsite','search_domains':['testsite.jp','www.testsite.jp','ssl.testsite.jp'],'mobile':True,
        'direct_listing_urls':[],'direct_detail_url_hints':['/detail']
    }]},ensure_ascii=False),encoding='utf-8')

    with direct.PUBLISHED.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=direct.FIELDS,lineterminator='\n')
        w.writeheader()
        w.writerow({
            'offerKey':'k','game':'ホワイトアウト・サバイバル','site':'testsite',
            'provider':'','reward':'11500','condition':'ok','platform':'iOS',
            'type':'StepUp','deadline':'','updatedAt':'2026-09-01',
            'url':'https://www.testsite.jp/detail?id=1',
            'sourceUrl':'https://www.testsite.jp/detail?id=1','verified':'true'
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
        'comparisonSources':['testsite'],
        'minimumConfirmedSourcesForComparison':1,
        'games':{'メメントモリ':{'enabled':True,'supplementalSources':[]}}
    },ensure_ascii=False),encoding='utf-8')
    direct.TARGETS.write_text(json.dumps({'games':[{
        'game':'メメントモリ',
        'aliases':['MementoMori'],
        'known_urls_by_source':{'testsite':['https://www.testsite.jp/contents/point/pointEntrance.php?pl=pc_categoryService&point_id=205975']}
    }]},ensure_ascii=False),encoding='utf-8')
    direct.SOURCES.write_text(json.dumps({'sources':[{
        'id':'testsite','search_domains':['testsite.jp','www.testsite.jp'],'mobile':True,
        'direct_listing_urls':[],'direct_detail_url_hints':['/detail']
    }]},ensure_ascii=False),encoding='utf-8')

    with direct.PUBLISHED.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=direct.FIELDS,lineterminator='\n')
        w.writeheader()
        w.writerow({
            'offerKey':'m','game':'メメントモリ','site':'testsite','provider':'',
            'reward':'12050','condition':'ok','platform':'Android','type':'StepUp',
            'deadline':'','updatedAt':'2026-09-01',
            'url':'https://ssl.testsite.jp/contents/point/pointEntrance.php?pl=pc_categoryService&point_id=205975',
            'sourceUrl':'https://ssl.testsite.jp/contents/point/pointEntrance.php?pl=pc_categoryService&point_id=205975','verified':'true'
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
from urllib.error import HTTPError, URLError
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
    source = {'id': 'testsite', 'search_domains': ['example.test'],
              'direct_listing_urls': ['https://example.test/list', 'https://example.test/unused'],
              'direct_listing_limit': 1, 'direct_detail_limit': 2}
    direct.POLICY.write_text(json.dumps({'comparisonSources': ['testsite'],
        'games': {'Game A': {'enabled': True}, 'Game B': {'enabled': True}}}))
    direct.TARGETS.write_text(json.dumps({'games': [
        {'game': game, 'known_urls_by_source': {'testsite': [
            f'https://example.test/detail?id={n}' for n in range(5)]}}
        for game in ('Game A', 'Game B')]}))
    direct.SOURCES.write_text(json.dumps({'sources': [source]}))
    row = dict.fromkeys(direct.FIELDS, '')
    row.update(offerKey='a', game='Game A', site='testsite', reward='100',
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


@pytest.mark.parametrize('error,expected', [
    (HTTPError('https://example.test/private', 404, 'untrusted message', {}, None), 'http_status_404'),
    (HTTPError('https://example.test/private', 403, 'untrusted message', {}, None), 'http_status_403'),
    (HTTPError('https://example.test/private', 429, 'untrusted message', {}, None), 'http_status_429'),
    (HTTPError('https://example.test/private', 503, 'untrusted message', {}, None), 'http_status_503'),
    (HTTPError('https://example.test/private', 'untrusted', 'message', {}, None), 'http_error'),
    (TimeoutError('untrusted message'), 'timeout'),
    (URLError(TimeoutError('untrusted message')), 'timeout'),
    (URLError('untrusted message'), 'network_error'),
    (ConnectionError('untrusted message'), 'network_error'),
    (ValueError('redirect left registered first-party domains'), 'first_party_redirect_rejected'),
    (ValueError('response exceeds byte limit; incomplete evidence rejected'), 'response_too_large'),
    (ValueError('URL is outside registered first-party domains'), 'first_party_url_rejected'),
    (ValueError('untrusted message'), 'fetch_error'),
    (RuntimeError('untrusted message'), 'fetch_error'),
])
def test_fetch_errors_have_safe_stable_diagnostics(error, expected):
    assert direct.summarize_fetch_error(error) == expected


@pytest.mark.parametrize('known_details', [False, True])
@pytest.mark.parametrize('status_code', [404, 429])
def test_listing_failure_is_retained_with_or_without_known_details(
        refresh_case, monkeypatch, known_details, status_code):
    if not known_details:
        direct.TARGETS.write_text(json.dumps({'games': [{'game': game}
            for game in ('Game A', 'Game B')]}))
        direct.write_published([])
    before = direct.PUBLISHED.read_bytes()
    requested = []
    body = io.BytesIO(b'untrusted response body')

    def fetch(url, source):
        requested.append(url)
        if url.endswith('/list'):
            raise HTTPError(url, status_code, 'untrusted message', {}, body)
        return '<body>Game A Game B 100 pt</body>', url

    monkeypatch.setattr(direct, 'fetch_first_party', fetch)
    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == before
    assert body.closed
    assert requested == ['https://example.test/list'] + (
        ['https://example.test/detail?id=0', 'https://example.test/detail?id=1'] if known_details else [])
    reviews = json.loads(direct.REVIEW.read_text())['items']
    code = f'http_status_{status_code}'
    if known_details:
        failures = [item for item in reviews if item['reason'] == 'listing_fetch_failed']
        assert len(failures) == 2
        assert all(item['url'] == 'https://example.test/list' and item['error'] == code for item in failures)
    else:
        assert len(reviews) == 2
        assert all(item['reason'] == 'discovery_required' and item['listingErrors'] == [code]
                   for item in reviews)
    assert 'untrusted' not in direct.REVIEW.read_text()
    status = json.loads(direct.STATUS.read_text())
    assert status['apiCalls'] == status['refreshedRows'] == status['publishedRewardChanges'] == 0
    assert status['reviewCount'] == len(reviews)
    assert sum(source['reviewRequired'] for game in status['games'] for source in game['sources']) == len(reviews)
    assert all(not game['comparisonReady'] for game in status['games'])


@pytest.mark.parametrize('close_fails', [False, True])
def test_cached_detail_failure_is_closed_and_sanitized(refresh_case, monkeypatch, close_fails):
    requested = []
    bodies = []

    class ErrorBody(io.BytesIO):
        def read(self, *args):
            pytest.fail('HTTP error bodies must not be read for diagnostics')

        def close(self):
            super().close()
            if close_fails:
                raise OSError('untrusted close error')

    def fetch(url, source):
        requested.append(url)
        if url.endswith('/list'):
            return '<body>No target listed</body>', url
        body = ErrorBody(b'untrusted response body')
        bodies.append(body)
        raise HTTPError(url, 404, 'untrusted message', {}, body)

    monkeypatch.setattr(direct, 'fetch_first_party', fetch)
    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == refresh_case
    assert len(requested) == len(set(requested)) == 3
    assert len(bodies) == 2 and all(body.closed for body in bodies)
    items = json.loads(direct.REVIEW.read_text())['items']
    failures = [item for item in items if item['reason'] == 'fetch_failed']
    assert len(failures) == 4
    assert all(item['error'] == 'http_status_404' for item in failures)
    assert 'untrusted' not in direct.REVIEW.read_text()


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


WARAU_URL = 'https://www.warau.jp/contents/point/pointEntrance.php?point_id=101'


@pytest.fixture
def warau_markup():
    # Synthetic amounts/terms in the structural selectors observed on Warau.
    return '''<html><head><title>テストゲーム（StepUp）</title>
<link rel="canonical" href="https://www.warau.jp/contents/point/pointEntrance.php?point_id=101">
</head><body><div id="pointEntrancePointDetail"><div id="innerEntranceBox">
<h2 class="pointEntrance-Head_Title">テストゲーム（StepUp）</h2>
<div class="pointEntrance-BannerBox_SpLabelText">iOS</div>
<dl id="detailPointContainer"><span class="entrance-ptItem_PtInfo-point">300</span>
<span class="entrance-ptItem_PtInfo-unit">pt</span></dl>
<table class="sw-SurInfo_PtList"><tbody>
<tr><th>達成条件</th><th>獲得pt</th></tr>
<tr><td class="sw-SurInfo_PtListAcquirement">10日以内にレベル5到達</td>
<td><span class="sw-Pt">100</span><span class="sw-PtUnit">pt</span></td></tr>
<tr><td class="sw-SurInfo_PtListAcquirement">20日以内にレベル10到達</td>
<td><span class="sw-Pt">200</span><span class="sw-PtUnit">pt</span></td></tr>
</tbody></table><div class="sw-SurInfo_PtListCumulative">累計
<span class="sw-Pt">300</span><span class="sw-PtUnit">pt</span></div></div>
<div id="js_cautionDiv"><h3>ポイント獲得条件</h3><p>新規利用のみ</p>
<p>獲得対象外：再利用</p><p>注意事項：利用時の条件を確認</p></div></div>
<aside>おすすめ 別ゲーム Android 累計 999,999 pt</aside></body></html>'''


def parse_warau(markup, requested=WARAU_URL, final=WARAU_URL):
    return direct.inspect_warau_offer(markup, requested, final, ['テストゲーム'])


def test_warau_scopes_points_os_and_steps_to_one_offer(warau_markup):
    evidence = parse_warau(warau_markup)
    assert evidence['state'] == 'parsed'
    assert evidence['offerId'] == '101'
    assert evidence['platform'] == 'iOS'
    assert evidence['rewardPoints'] == 300
    assert evidence['rewardUnit'] == 'pt'
    assert 'rewardYen' not in evidence
    assert [step['rewardPoints'] for step in evidence['steps']] == [100, 200]
    assert '再利用' in evidence['termsText']
    assert len(evidence['evidenceFingerprint']) == 64
    alternative = WARAU_URL.replace('www.', 'ssl.') + '&pl=navigation'
    assert parse_warau(warau_markup, alternative, alternative)['state'] == 'parsed'


@pytest.mark.parametrize('old,new,reason', [
    ('<span class="sw-Pt">200</span>', '<span class="sw-Pt">201</span>', 'step_total_mismatch'),
    ('PtInfo-point">300', 'PtInfo-point">301', 'step_total_mismatch'),
    ('SpLabelText">iOS', 'SpLabelText">iOS Android', 'ambiguous_offer_platform'),
    ('pointEntrance-Head_Title">テストゲーム', 'pointEntrance-Head_Title">別ゲーム', 'offer_title_mismatch'),
    ('<span class="sw-PtUnit">pt', '<span class="sw-PtUnit">円', 'unexpected_reward_unit'),
    ('PtInfo-unit">pt', 'PtInfo-unit">円', 'unexpected_reward_unit'),
    ('<span class="sw-Pt">100</span>', '<span class="sw-Pt">1.00</span>', 'invalid_points'),
    ('<span class="sw-Pt">100</span>', '<span class="sw-Pt">-100</span>', 'invalid_points'),
    ('<span class="sw-Pt">100</span>', '<span class="sw-Pt">1,00</span>', 'invalid_points'),
    ('20日以内にレベル10到達', '10日以内にレベル5到達', 'missing_or_duplicate_steps'),
    ('<p>注意事項：利用時の条件を確認</p>', '', 'incomplete_offer_terms'),
    ('id="js_cautionDiv"', 'id="other"', 'missing_or_ambiguous_offer_structure'),
    ('id="innerEntranceBox"', 'id="other"', 'missing_or_ambiguous_offer_structure'),
    ('?point_id=101', '?point_id=102', 'canonical_offer_mismatch'),
    ('?point_id=101', '?point_id=101&amp;point_id=102', 'ambiguous_offer_identity'),
])
def test_warau_rejects_conflicting_or_missing_evidence(warau_markup, old, new, reason):
    evidence = parse_warau(warau_markup.replace(old, new))
    assert evidence['state'] == 'review_required'
    assert evidence['reason'] == reason


def test_warau_checks_final_identity_and_ended_page_before_recommendations(warau_markup):
    assert parse_warau(warau_markup, final=WARAU_URL.replace('101', '102'))['reason'] == 'redirected_to_different_offer'
    ended = warau_markup.replace('<body>', '<body><div class="pointEntranceNone-Main">広告にアクセスできません</div>')
    assert parse_warau(ended)['state'] == 'unavailable'
    assert parse_warau(ended)['reason'] == 'source_offer_unavailable'
    duplicate = warau_markup.replace('</body>', '<div id="pointEntrancePointDetail"></div></body>')
    assert parse_warau(duplicate)['state'] == 'review_required'


@pytest.mark.parametrize('old,new', [
    ('10日以内にレベル5到達', '10日以内にレベル6到達'),
    ('20日以内にレベル10到達', '19日以内にレベル10到達'),
    ('再利用', '再利用と課金'),
    ('SpLabelText">iOS', 'SpLabelText">Android'),
])
def test_warau_snapshot_changes_when_terms_or_os_change(warau_markup, old, new):
    assert parse_warau(warau_markup)['evidenceFingerprint'] != parse_warau(
        warau_markup.replace(old, new))['evidenceFingerprint']


def test_warau_snapshot_ignores_unrelated_recommendations(warau_markup):
    assert parse_warau(warau_markup)['evidenceFingerprint'] == parse_warau(
        warau_markup.replace('999,999', '888,888'))['evidenceFingerprint']


def test_warau_structured_review_is_not_a_publication(warau_markup, monkeypatch):
    direct.POLICY.write_text(json.dumps({'comparisonSources': ['warau'],
        'games': {'テストゲーム': {'enabled': True}}}))
    direct.TARGETS.write_text(json.dumps({'games': [{'game': 'テストゲーム',
        'known_urls_by_source': {'warau': [WARAU_URL]}}]}))
    direct.SOURCES.write_text(json.dumps({'sources': [{'id': 'warau',
        'search_domains': ['warau.jp'], 'direct_listing_urls': []}]}))
    row = dict.fromkeys(direct.FIELDS, '')
    row.update(offerKey='test', game='テストゲーム', site='warau', platform='Android',
               reward='300', condition='以前の条件', updatedAt='2026-01-01', url=WARAU_URL, verified='true')
    direct.write_published([row])
    before = direct.PUBLISHED.read_bytes()
    monkeypatch.setattr(direct, 'fetch_first_party', lambda url, source: (warau_markup, url))
    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == before
    items = json.loads(direct.REVIEW.read_text())['items']
    assert len(items) == 1
    assert items[0]['reason'] == 'structured_offer_review_required'
    assert items[0]['platformMatches'] is False
    assert items[0]['sourceEvidence']['rewardPoints'] == 300
    assert items[0]['sourceEvidence']['rewardUnit'] == 'pt'
    assert json.loads(direct.STATUS.read_text())['refreshedRows'] == 0


@pytest.fixture
def approved_case(warau_markup, monkeypatch):
    direct.POLICY.write_text(json.dumps({'comparisonSources': ['warau'],
        'minimumConfirmedSourcesForComparison': 2, 'games': {'テストゲーム': {'enabled': True}}}))
    direct.TARGETS.write_text(json.dumps({'games': [{'game': 'テストゲーム',
        'known_urls_by_source': {'warau': [WARAU_URL]}}]}))
    direct.SOURCES.write_text(json.dumps({'sources': [{'id': 'warau',
        'search_domains': ['warau.jp'], 'direct_listing_urls': []}]}))
    row = dict.fromkeys(direct.FIELDS, '')
    row.update(offerKey='approved', game='テストゲーム', site='warau', platform='iOS',
               reward='300', condition='審査済みの条件要約', type='StepUp', updatedAt='2026-09-01',
               url=WARAU_URL, sourceUrl=WARAU_URL, verified='true')
    other = dict(row, offerKey='unrelated', game='別ゲーム', site='other', reward='700')
    direct.write_published([row, other])
    evidence = parse_warau(warau_markup)
    approval = {'offerKey': row['offerKey'], 'game': row['game'], 'source': 'warau',
        'approved': True, 'reviewedBy': 'fixture-only', 'reviewedAt': '2026-09-02T00:00:00+00:00',
        'expiresAt': '2026-09-10T00:00:00+00:00', 'parserVersion': evidence['parserVersion'],
        'evidenceFingerprint': evidence['evidenceFingerprint'],
        'publishedRowFingerprint': direct.published_row_fingerprint(row),
        'unitConversion': {'sourceUnit': 'pt', 'targetUnit': 'JPY', 'yenPerPoint': 1,
                           'evidenceUrl': 'https://www.warau.jp/help/qa/128/'}}
    path = direct.POLICY.with_name('approved_offer_baselines.json')
    path.write_text(json.dumps({'schemaVersion': 1, 'approvals': [approval]}))
    monkeypatch.setattr(direct, 'fetch_first_party', lambda url, source: (warau_markup, url))
    monkeypatch.setattr(direct, 'now_iso', lambda: '2026-09-03T16:00:00+00:00')
    return row, approval, evidence, path


def test_approved_unchanged_snapshot_refreshes_only_date_once(approved_case, monkeypatch):
    before = direct.read_published()
    assert direct.main() == 0
    after = direct.read_published()
    assert after[0]['updatedAt'] == '2026-09-04'  # JST
    assert after[1] == before[1]
    assert {k:v for k,v in after[0].items() if k != 'updatedAt'} == {
        k:v for k,v in before[0].items() if k != 'updatedAt'}
    status = json.loads(direct.STATUS.read_text())
    assert status['refreshedRows'] == 1
    assert status['publishedRewardChanges'] == 0
    assert status['games'][0]['standardConfirmed'] == 1
    assert status['games'][0]['comparisonReady'] is False  # one source is not a comparison
    def no_rewrite(rows):
        pytest.fail('same-day confirmation must not rewrite the CSV')
    monkeypatch.setattr(direct, 'write_published', no_rewrite)
    assert direct.main() == 0
    assert json.loads(direct.STATUS.read_text())['refreshedRows'] == 1


def test_listing_failure_does_not_hide_independently_approved_detail(approved_case, warau_markup, monkeypatch):
    source = json.loads(direct.SOURCES.read_text())
    listing = 'https://www.warau.jp/list'
    source['sources'][0]['direct_listing_urls'] = [listing]
    direct.SOURCES.write_text(json.dumps(source))
    calls = []

    def fetch(url, source):
        calls.append(url)
        if url == listing:
            raise HTTPError(url, 404, 'untrusted message', {}, None)
        return warau_markup, url

    monkeypatch.setattr(direct, 'fetch_first_party', fetch)
    before = direct.read_published()
    assert direct.main() == 0
    after = direct.read_published()
    assert calls == [listing, WARAU_URL]
    assert after[0] == dict(before[0], updatedAt='2026-09-04')
    assert after[1:] == before[1:]
    status = json.loads(direct.STATUS.read_text())
    result = status['games'][0]['sources'][0]
    assert result['confirmedOffers'] == result['updatedRows'] == result['reviewRequired'] == 1
    assert status['refreshedRows'] == status['reviewCount'] == 1
    assert status['games'][0]['comparisonReady'] is False
    items = json.loads(direct.REVIEW.read_text())['items']
    assert len(items) == 1 and items[0]['reason'] == 'listing_fetch_failed'


@pytest.mark.parametrize('field,value', [
    ('approved', False), ('approved', 'true'), ('offerKey', 'different'),
    ('game', '別ゲーム'), ('source', 'other'), ('reviewedBy', ''),
    ('reviewedAt', '2027-01-01T00:00:00+00:00'), ('reviewedAt', '2026-09-01'),
    ('expiresAt', '2026-09-03T16:00:00+00:00'), ('expiresAt', 'invalid'),
    ('publishedRowFingerprint', '0'*64), ('evidenceFingerprint', '0'*64),
    ('parserVersion', 'future-version'), ('unitConversion', None),
    ('unitConversion', {'sourceUnit':'pt', 'targetUnit':'JPY', 'yenPerPoint': True,
                        'evidenceUrl':'https://www.warau.jp/help/qa/128/'}),
    ('unitConversion', {'sourceUnit':'pt', 'targetUnit':'JPY', 'yenPerPoint': 2,
                        'evidenceUrl':'https://www.warau.jp/help/qa/128/'}),
])
def test_invalid_approvals_keep_existing_bytes(approved_case, field, value):
    row, approval, evidence, path = approved_case
    approval[field] = value
    path.write_text(json.dumps({'schemaVersion': 1, 'approvals': [approval]}))
    before = direct.PUBLISHED.read_bytes()
    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == before
    assert json.loads(direct.STATUS.read_text())['refreshedRows'] == 0


@pytest.mark.parametrize('field,value', [
    ('condition', 'changed'), ('deadline', '2026-12-01'), ('platform', 'Android'),
    ('reward', '301'), ('verified', 'false'), ('sourceUrl', WARAU_URL.replace('101','102')),
])
def test_published_edit_invalidates_approval(approved_case, field, value):
    rows = direct.read_published()
    rows[0][field] = value
    direct.write_published(rows)
    before = direct.PUBLISHED.read_bytes()
    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == before


def test_changed_source_terms_require_new_approval(approved_case, warau_markup, monkeypatch):
    before = direct.PUBLISHED.read_bytes()
    monkeypatch.setattr(direct, 'fetch_first_party', lambda url, source: (
        warau_markup.replace('20日以内にレベル10到達', '19日以内にレベル10到達'), url))
    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == before
    assert json.loads(direct.REVIEW.read_text())['items'][0]['approvalHoldReason'] == 'source_terms_changed_since_approval'


@pytest.mark.parametrize('payload', ['{', '{"schemaVersion": 2, "approvals": []}',
    '{"schemaVersion": 1, "approvals": [null]}'])
def test_malformed_registry_stops_before_fetch(approved_case, payload, monkeypatch):
    approved_case[3].write_text(payload)
    before = direct.PUBLISHED.read_bytes()
    monkeypatch.setattr(direct, 'fetch_first_party', lambda *args: pytest.fail('must not fetch'))
    assert direct.main() == 2
    assert direct.PUBLISHED.read_bytes() == before


def test_duplicate_approvals_stop_before_fetch(approved_case, monkeypatch):
    approval = approved_case[1]
    approved_case[3].write_text(json.dumps({'schemaVersion': 1, 'approvals': [approval, approval]}))
    monkeypatch.setattr(direct, 'fetch_first_party', lambda *args: pytest.fail('must not fetch'))
    assert direct.main() == 2


def test_duplicate_published_identity_is_not_refreshed(approved_case):
    rows = direct.read_published()
    rows.append(dict(rows[0], offerKey='duplicate'))
    direct.write_published(rows)
    before = direct.PUBLISHED.read_bytes()
    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == before
    assert json.loads(direct.REVIEW.read_text())['items'][0]['approvalHoldReason'] == 'ambiguous_published_identity'


def test_concurrent_publication_change_is_not_overwritten(approved_case, warau_markup, monkeypatch):
    changed_bytes = direct.PUBLISHED.read_bytes() + b'\n'
    def fetch(url, source):
        direct.PUBLISHED.write_bytes(changed_bytes)
        return warau_markup, url
    monkeypatch.setattr(direct, 'fetch_first_party', fetch)
    assert direct.main() == 2
    assert direct.PUBLISHED.read_bytes() == changed_bytes


def test_expired_absolute_deadline_cannot_be_refreshed(approved_case):
    row, approval, evidence, path = approved_case
    row['deadline'] = '2026-09-03'
    approval['publishedRowFingerprint'] = direct.published_row_fingerprint(row)
    assert direct.approved_refresh_reason(row, evidence, approval, '2026-09-03T16:00:00+00:00') == 'published_deadline_expired'


def test_real_baseline_candidates_are_unapproved_and_bound_to_revised_rows():
    payload = json.loads((ROOT/'data/warau_baseline_candidates.json').read_text())
    assert payload['status'] == 'reviewed_registry_added'
    assert len(payload['candidates']) == 4
    rows = list(csv.DictReader((ROOT/'data/published_offers.csv').open(encoding='utf-8', newline='')))
    by_key = {row['offerKey']: row for row in rows}
    assert len(by_key) == len(rows)
    expected = {'204645': ('Township', 'Android', '21670', 9),
                '204643': ('Township', 'iOS', '16760', 9),
                '205817': ('きのこ伝説', 'Android', '18800', 11),
                '205816': ('きのこ伝説', 'iOS', '22000', 11)}
    seen = set()
    for candidate in payload['candidates']:
        assert candidate['approved'] is False
        assert 'reviewedAt' not in candidate and 'expiresAt' not in candidate
        row = by_key[candidate['offerKey']]
        assert row['site'] == 'warau' and row['verified'] == 'true'
        offer_id = direct.warau_offer_id(row['url'])
        seen.add(offer_id)
        assert (row['game'], row['platform'], row['reward'], candidate['stepCount']) == expected[offer_id]
        assert int(row['reward']) == candidate['rewardPoints']
        assert candidate['publishedRowFingerprint'] == direct.published_row_fingerprint(row)
        assert direct.approved_refresh_reason(row, {}, candidate, '2026-09-03T12:00:00+00:00') == 'baseline_approval_required'
        if row['game'] == 'Township':
            assert row['deadline'] == 'インストール日から起算して60日以内'
        else:
            assert row['deadline'] == 'インストール日から起算して30日／40日／45日以内（ステップ別）'
            for condition in ('課金を含む11ステップ', 'ステージ普通2-8', 'ステージ普通5-10',
                'ステージ困難1-10', 'ステージ終末IV10-10', '月パス購入（ダイヤ以外）',
                '終身パス購入（ダイヤ以外）', '一括1600円課金', 'プレイヤーレベル100到達',
                'レベル100到達後に一括3200円課金', '40日以内：プレイヤーレベル120到達',
                '45日以内：プレイヤーレベル125到達'):
                assert condition in row['condition']
    assert seen == set(expected)


def test_reviewed_registry_is_exactly_four_rows_for_seven_days(monkeypatch):
    from datetime import datetime, timedelta
    monkeypatch.setattr(direct, 'POLICY', ROOT/'config/refresh_policy.json')
    approvals = direct.load_refresh_approvals()
    candidates = json.loads((ROOT/'data/warau_baseline_candidates.json').read_text())['candidates']
    assert len(approvals) == 4
    assert set(approvals) == {candidate['offerKey'] for candidate in candidates}
    for candidate in candidates:
        approval = approvals[candidate['offerKey']]
        assert approval['approved'] is True
        assert approval['reviewedBy'] == 'Codex evidence review; maintainer authorized seven-day PR enrollment in ChatGPT on 2026-09-03'
        for field in ('game', 'source', 'sourceUrl', 'parserVersion', 'evidenceFingerprint',
                      'publishedRowFingerprint', 'unitConversion'):
            assert approval[field] == candidate[field]
        assert approval['reviewedAt'] == '2026-09-03T09:48:47+00:00'
        assert approval['expiresAt'] == '2026-09-10T09:48:47+00:00'
        assert datetime.fromisoformat(approval['expiresAt']) - datetime.fromisoformat(approval['reviewedAt']) == timedelta(days=7)


@pytest.mark.parametrize('offer_id', ['204645', '204643', '205817', '205816'])
def test_enrolled_rows_gate_time_boundaries_and_changed_evidence(offer_id):
    from datetime import datetime, timedelta
    rows = list(csv.DictReader((ROOT/'data/published_offers.csv').open(encoding='utf-8', newline='')))
    row = next(r for r in rows if r['site'] == 'warau' and direct.warau_offer_id(r['url']) == offer_id)
    approvals = json.loads((ROOT/'config/approved_offer_baselines.json').read_text())['approvals']
    approval = next(a for a in approvals if a['offerKey'] == row['offerKey'])
    # Gate-only fixture. Parsing real saved HTML is checked separately offline.
    evidence = {'state':'parsed', 'offerId':offer_id, 'platform':row['platform'],
        'parserVersion':approval['parserVersion'], 'evidenceFingerprint':approval['evidenceFingerprint'],
        'rewardUnit':'pt', 'rewardPoints':int(row['reward'])}
    start = datetime.fromisoformat(approval['reviewedAt'])
    end = datetime.fromisoformat(approval['expiresAt'])
    assert direct.approved_refresh_reason(row, evidence, approval, start.isoformat()) is None
    assert direct.approved_refresh_reason(row, evidence, approval, (end-timedelta(seconds=1)).isoformat()) is None
    for instant in (start-timedelta(seconds=1), end, end+timedelta(seconds=1)):
        assert direct.approved_refresh_reason(row, evidence, approval, instant.isoformat()) == 'approval_expired_or_invalid_time'
    assert direct.approved_refresh_reason(dict(row, updatedAt='2026-09-04'), evidence, approval, start.isoformat()) is None
    assert direct.approved_refresh_reason(dict(row, condition='changed'), evidence, approval, start.isoformat()) == 'published_row_changed_since_approval'
    assert direct.approved_refresh_reason(row, dict(evidence, evidenceFingerprint='changed'), approval, start.isoformat()) == 'source_terms_changed_since_approval'
    assert direct.approved_refresh_reason(row, dict(evidence, platform='other'), approval, start.isoformat()) == 'approved_platform_changed'
    assert direct.approved_refresh_reason(row, dict(evidence, rewardPoints=int(row['reward'])+1), approval, start.isoformat()) == 'approved_reward_changed'


CHOBI_URL = 'https://www.chobirich.com/ad_details/1234567'


@pytest.fixture
def chobi_markup():
    # Synthetic text with the structure inspected in the rendered official page.
    return f'''<html><head><link rel="canonical" href="{CHOBI_URL}"></head><body>
<main><h1>テストゲーム</h1><div><p>最大600ポイント</p>
<p id="item_yen">(最大<span>600</span>円相当)</p></div>
<p>iPhone・iOS向けの一般的な注意事項</p>
<button>QRコードを表示してスマホで利用する(Android用)</button>
<div class="ad-requirement"><h2>獲得方法：新規利用後、各ステップクリア</h2><p>
1. 広告クリックから30日以内にレベル10到達で100pt<br>
2. 広告クリックから40日以内にレベル100到達後に一括3200円課金で200pt<br>
3. 広告クリックから45日以内にレベル125到達で300pt<br>
成果受付期限：各ステップの広告クリック日からの日数<br>
成果調査受付期限：広告クリックから57日<br>
条件達成に関する注意事項：新規利用のみ<br>
却下条件：重複利用</p></div>
<button>QRコードを表示してスマホで利用する(Android用)</button>
<aside>おすすめ別ゲーム iOS 最大999999ポイント</aside></main></body></html>'''


def parse_chobi(raw, requested=CHOBI_URL, final=CHOBI_URL):
    return direct.inspect_chobirich_offer(raw, requested, final, ['テストゲーム'])


def test_chobirich_binds_numbered_steps_yen_os_and_deadline_origin(chobi_markup):
    evidence = parse_chobi(chobi_markup)
    assert evidence['state'] == 'parsed'
    assert evidence['platform'] == 'Android'  # not the generic Apple disclaimer
    assert evidence['rewardPoints'] == evidence['observedRewardYen'] == 600
    assert evidence['rewardUnit'] == 'pt'
    assert [x['rewardPoints'] for x in evidence['steps']] == [100, 200, 300]
    assert all('広告クリックから' in x['condition'] for x in evidence['steps'])
    assert 'レベル100到達後に一括3200円課金' in evidence['steps'][1]['condition']
    assert len(evidence['evidenceFingerprint']) == 64
    assert parse_chobi(chobi_markup.replace('999999', '888888'))['evidenceFingerprint'] == evidence['evidenceFingerprint']


@pytest.mark.parametrize('old,new,reason', [
    ('<span>600</span>', '<span>300</span>', 'source_reward_conversion_mismatch'),
    ('最大600ポイント', '最大1200ポイント', 'source_reward_conversion_mismatch'),
    ('最大600ポイント', '最大600円', 'missing_explicit_point_total'),
    ('円相当)', '円)', 'missing_explicit_yen_total'),
    ('で200pt', 'で201pt', 'step_total_mismatch'),
    ('で200pt', 'で200円', 'incomplete_numbered_steps'),
    ('で200pt', 'で2,00pt', 'invalid_points'),
    ('で200pt', 'で0.5pt', 'incomplete_numbered_steps'),
    ('2. 広告', '4. 広告', 'incomplete_numbered_steps'),
    ('3. 広告', '2. 広告', 'incomplete_numbered_steps'),
    ('3. 広告クリックから45日以内にレベル125到達で300pt<br>', '', 'step_total_mismatch'),
    ('class="ad-requirement"', 'class="other"', 'missing_or_ambiguous_offer_structure'),
    ('id="item_yen"', 'id="other"', 'missing_or_ambiguous_offer_structure'),
    ('成果受付期限', '受付期間', 'incomplete_offer_terms'),
    ('却下条件', '対象外', 'incomplete_offer_terms'),
    ('<h1>テストゲーム</h1>', '<h1>別ゲーム</h1>', 'offer_title_mismatch'),
    ('(Android用)', '(Android/iOS用)', 'ambiguous_offer_platform'),
    ('QRコードを表示してスマホで利用する(Android用)', '登録して利用する', 'ambiguous_offer_platform'),
    ('各ステップクリア', '商品の購入', 'unsupported_achievement_method'),
    ('<main>', '<main><p id="item_yen">(最大600円相当)</p>', 'missing_or_ambiguous_offer_structure'),
    ('/ad_details/1234567', '/ad_details/7654321', 'canonical_offer_mismatch'),
])
def test_chobirich_rejects_incomplete_or_conflicting_evidence(chobi_markup, old, new, reason):
    evidence = parse_chobi(chobi_markup.replace(old, new))
    assert evidence['state'] == 'review_required'
    assert evidence['reason'] == reason


def test_chobirich_conflicting_platform_buttons_and_redirect_are_held(chobi_markup):
    conflicting = chobi_markup.replace('</main>', '<button>QRコードを表示してスマホで利用する(iOS用)</button></main>')
    assert parse_chobi(conflicting)['reason'] == 'ambiguous_offer_platform'
    assert parse_chobi(chobi_markup, final=CHOBI_URL.replace('1234567','7654321'))['reason'] == 'redirected_to_different_offer'


@pytest.mark.parametrize('url', [
    'http://www.chobirich.com/ad_details/1234567',
    'https://outside.invalid/ad_details/1234567',
    'https://www.chobirich.com.evil.invalid/ad_details/1234567',
    'https://user@www.chobirich.com/ad_details/1234567',
    'https://www.chobirich.com:444/ad_details/1234567',
    'https://www.chobirich.com/ad_details/redirect/1234567',
    'https://www.chobirich.com/ad_details/1234567/extra',
])
def test_chobirich_rejects_unsupported_identity_urls(chobi_markup, url):
    assert parse_chobi(chobi_markup, requested=url)['state'] == 'review_required'


@pytest.mark.parametrize('old,new', [
    ('広告クリックから', 'インストールから'),
    ('レベル100到達後に', 'レベル90到達後に'),
    ('却下条件：重複利用', '却下条件：重複利用と再インストール'),
])
def test_chobirich_full_terms_changes_invalidate_snapshot(chobi_markup, old, new):
    assert parse_chobi(chobi_markup)['evidenceFingerprint'] != parse_chobi(chobi_markup.replace(old,new))['evidenceFingerprint']


@pytest.mark.parametrize('fetch_fails', [False, True])
def test_chobirich_is_review_only_even_with_an_approval_record(chobi_markup, monkeypatch, fetch_fails):
    direct.POLICY.write_text(json.dumps({'comparisonSources':['chobirich'],
        'minimumConfirmedSourcesForComparison':2, 'games':{'テストゲーム':{'enabled':True}}}))
    direct.TARGETS.write_text(json.dumps({'games':[{'game':'テストゲーム'}]}))
    direct.SOURCES.write_text(json.dumps({'sources':[{'id':'chobirich',
        'search_domains':['chobirich.com'], 'direct_listing_urls':[]}]}))
    row = dict.fromkeys(direct.FIELDS, '')
    row.update(offerKey='chobi-test', game='テストゲーム', site='chobirich', platform='不明',
        reward='600', condition='以前の要約', updatedAt='2026-08-31', url=CHOBI_URL, sourceUrl=CHOBI_URL, verified='true')
    direct.write_published([row])
    direct.POLICY.with_name('approved_offer_baselines.json').write_text(json.dumps(
        {'schemaVersion':1,'approvals':[{'offerKey':row['offerKey'],'approved':True,'source':'chobirich'}]}))
    calls = []
    def fetch(url, source):
        calls.append(url)
        if fetch_fails:
            from urllib.error import HTTPError
            raise HTTPError(url, 404, 'Not Found', {}, None)
        return chobi_markup, url
    monkeypatch.setattr(direct, 'fetch_first_party', fetch)
    before = direct.PUBLISHED.read_bytes()
    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == before
    assert calls == [CHOBI_URL]
    status = json.loads(direct.STATUS.read_text())
    assert status['refreshedRows'] == status['publishedRewardChanges'] == status['apiCalls'] == 0
    assert status['games'][0]['comparisonReady'] is False
    item = json.loads(direct.REVIEW.read_text())['items'][0]
    if fetch_fails:
        assert item['reason'] == 'fetch_failed'
    else:
        assert item['approvalHoldReason'] == 'source_refresh_not_enabled'
        assert item['sourceEvidence']['platform'] == 'Android'
        assert item['platformMatches'] is False
