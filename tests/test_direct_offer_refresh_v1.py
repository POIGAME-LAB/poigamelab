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
from urllib.request import HTTPSHandler, build_opener
from urllib.response import addinfourl

import pytest


@pytest.fixture(autouse=True)
def isolate_module_paths(tmp_path, monkeypatch):
    for name in ('ROOT', 'POLICY', 'TARGETS', 'SOURCES', 'PUBLISHED', 'STATUS', 'LEGACY_STATUS', 'REVIEW'):
        monkeypatch.setattr(direct, name, tmp_path if name == 'ROOT' else tmp_path / getattr(direct, name).name)


def test_external_redirect_is_blocked_before_destination_request(monkeypatch):
    requested = []

    class FakeHTTPS(HTTPSHandler):
        def https_open(self, req):
            requested.append(req.full_url)
            headers = Message()
            redirect = req.full_url == 'https://example.test/offer'
            if redirect:
                headers['Location'] = 'https://outside.invalid/private'
            response = addinfourl(io.BytesIO(b''), headers, req.full_url, 302 if redirect else 200)
            response.msg = 'Found' if redirect else 'OK'
            return response

    monkeypatch.setattr(direct, 'build_opener', lambda guard: build_opener(FakeHTTPS(), guard), raising=False)
    with pytest.raises(ValueError, match='redirect left'):
        direct.fetch_first_party('https://example.test/offer', {'search_domains': ['example.test']})
    assert requested == ['https://example.test/offer']


def test_same_domain_transport_downgrade_is_blocked_before_destination_request(monkeypatch):
    requested = []

    class FakeHTTPS(HTTPSHandler):
        def https_open(self, req):
            requested.append(req.full_url)
            headers = Message()
            headers['Location'] = 'http://example.test/detail'
            response = addinfourl(io.BytesIO(b''), headers, req.full_url, 302)
            response.msg = 'Found'
            return response

    monkeypatch.setattr(direct, 'build_opener', lambda guard: build_opener(FakeHTTPS(), guard), raising=False)
    with pytest.raises(ValueError, match='redirect left'):
        direct.fetch_first_party('https://example.test/start', {'search_domains': ['example.test']})
    assert requested == ['https://example.test/start']


@pytest.mark.parametrize('url', [
    'http://example.test/detail',
    'https://user@example.test/detail',
    'https://example.test:444/detail',
])
def test_first_party_guard_rejects_insecure_or_unexpected_transport(url):
    source = {'search_domains': ['example.test']}
    assert direct.source_host_allowed(url, source) is False
    with pytest.raises(ValueError, match='outside registered first-party domains'):
        direct.fetch_first_party(url, source)


def test_apex_registration_does_not_trust_arbitrary_subdomains():
    source = {'search_domains': ['example.test', 'www.example.test']}
    assert direct.source_host_allowed('https://example.test/path', source) is True
    assert direct.source_host_allowed('https://www.example.test/path', source) is True
    assert direct.source_host_allowed('https://evil.example.test/path', source) is False


def test_allowed_redirect_and_oversized_response(monkeypatch):
    requested = []

    class FakeHTTPS(HTTPSHandler):
        def https_open(self, req):
            requested.append(req.full_url)
            headers = Message()
            redirect = req.full_url.endswith('/start')
            if redirect:
                headers['Location'] = 'https://example.test/detail'
            response = addinfourl(io.BytesIO(b'' if redirect else b'12345'), headers,
                                  req.full_url, 302 if redirect else 200)
            response.msg = 'Found' if redirect else 'OK'
            return response

    monkeypatch.setattr(direct, 'build_opener', lambda guard: build_opener(FakeHTTPS(), guard), raising=False)
    source = {'search_domains': ['example.test']}
    assert direct.fetch_first_party('https://example.test/start', source, max_bytes=5) == (
        '12345', 'https://example.test/detail')
    assert len(requested) == 2
    with pytest.raises(ValueError, match='incomplete evidence'):
        direct.fetch_first_party('https://example.test/detail', source, max_bytes=4)


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
        'search_domains': ['warau.jp', 'www.warau.jp', 'ssl.warau.jp'], 'direct_listing_urls': []}]}))
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
        'search_domains': ['warau.jp', 'www.warau.jp', 'ssl.warau.jp'], 'direct_listing_urls': []}]}))
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
        'search_domains':['chobirich.com','www.chobirich.com'], 'direct_listing_urls':[]}]}))
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


def test_scheduled_fetch_disabled_source_never_calls_network_or_changes_published(monkeypatch):
    direct.POLICY.write_text(json.dumps({
        'comparisonSources': ['chobirich'],
        'minimumConfirmedSourcesForComparison': 2,
        'games': {'テストゲーム': {'enabled': True}},
    }))
    direct.TARGETS.write_text(json.dumps({'games': [{
        'game': 'テストゲーム',
        'known_urls_by_source': {'chobirich': [CHOBI_URL]},
    }]}))
    direct.SOURCES.write_text(json.dumps({'sources': [{
        'id': 'chobirich',
        'search_domains': ['chobirich.com', 'www.chobirich.com'],
        'direct_listing_urls': ['https://www.chobirich.com/smartphone?pos=app'],
        'direct_listing_limit': 1,
        'direct_detail_limit': 6,
        'scheduled_fetch_enabled': False,
    }]}))
    row = dict.fromkeys(direct.FIELDS, '')
    row.update(
        offerKey='chobi-disabled',
        game='テストゲーム',
        site='chobirich',
        reward='600',
        condition='既存掲載を保持',
        platform='Android',
        updatedAt='2026-08-31',
        url=CHOBI_URL,
        sourceUrl=CHOBI_URL,
        verified='true',
    )
    direct.write_published([row])
    before = direct.PUBLISHED.read_bytes()
    monkeypatch.setattr(
        direct, 'fetch_first_party',
        lambda *args, **kwargs: pytest.fail('disabled source must not fetch'),
    )

    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == before

    status = json.loads(direct.STATUS.read_text())
    assert status['apiCalls'] == status['refreshedRows'] == status['publishedRewardChanges'] == 0
    source = status['games'][0]['sources'][0]
    assert source['source'] == 'chobirich'
    assert source['state'] == 'review_required'
    assert source['knownOrDiscoveredUrls'] == source['confirmedOffers'] == source['updatedRows'] == 0
    assert source['reviewRequired'] == 1
    assert status['games'][0]['comparisonReady'] is False

    items = json.loads(direct.REVIEW.read_text())['items']
    assert len(items) == 1
    assert items[0]['reason'] == 'scheduled_source_fetch_disabled'
    assert items[0]['existingRows'] == 1


def test_repository_unattended_fetch_disables_only_unreliable_comparison_sources(monkeypatch):
    monkeypatch.setattr(direct, 'SOURCES', ROOT/'config/point_sources.json')
    payload = json.loads((ROOT/'config/point_sources.json').read_text())
    by_id = {source['id']: source for source in payload['sources']}
    comparison = json.loads((ROOT/'config/refresh_policy.json').read_text())['comparisonSources']

    disabled = {
        source_id for source_id in comparison
        if by_id[source_id].get('scheduled_fetch_enabled', True) is not True
    }
    assert disabled == {'chobirich', 'mikoshi'}
    assert 'reliable' in by_id['chobirich']['scheduled_fetch_reason'].lower()
    assert 'javascript' in by_id['mikoshi']['scheduled_fetch_reason'].lower()

    assert all(
        by_id[source_id].get('scheduled_fetch_enabled', True) is True
        for source_id in comparison
        if source_id not in disabled
    )


def test_repository_gendama_uses_current_https_listing_and_service_item_identity():
    payload = json.loads((ROOT/'config/point_sources.json').read_text())
    gendama = next(source for source in payload['sources'] if source['id'] == 'gendama')
    listing = 'https://www.gendama.jp/welcome'
    detail = 'https://www.gendama.jp/service/item/1426617?frame=pctopnewclient'

    assert gendama['start_url'] == listing
    assert gendama['direct_listing_urls'] == [listing]
    assert '/service/item/' in gendama['direct_detail_url_hints']
    assert gendama.get('scheduled_fetch_enabled', True) is True
    assert gendama['generic_reward_detection_enabled'] is False
    assert 'conversion' in gendama['generic_reward_detection_reason'].lower()
    assert direct.source_host_allowed(listing, gendama) is True
    assert direct.source_host_allowed(detail, gendama) is True
    assert direct.detail_like(detail, gendama) is True
    assert direct.offer_identity_key(detail, 'gendama') == 'gendama:pathid:1426617'


def test_gendama_generic_points_never_become_yen_reward_candidates(monkeypatch):
    detail = 'https://www.gendama.jp/service/item/1426617?frame=pctopnewclient'
    direct.POLICY.write_text(json.dumps({
        'comparisonSources': ['gendama'],
        'minimumConfirmedSourcesForComparison': 2,
        'games': {'テストゲーム': {'enabled': True}},
    }))
    direct.TARGETS.write_text(json.dumps({'games': [{
        'game': 'テストゲーム',
        'known_urls_by_source': {'gendama': [detail]},
    }]}))
    direct.SOURCES.write_text(json.dumps({'sources': [{
        'id': 'gendama',
        'search_domains': ['www.gendama.jp'],
        'direct_listing_urls': [],
        'direct_detail_limit': 6,
        'direct_detail_url_hints': ['/service/item/'],
        'generic_reward_detection_enabled': False,
    }]}))
    row = dict.fromkeys(direct.FIELDS, '')
    row.update(
        offerKey='gendama-test',
        game='テストゲーム',
        site='gendama',
        reward='300',
        condition='既存要約',
        platform='Android',
        updatedAt='2026-08-31',
        url=detail,
        sourceUrl=detail,
        verified='true',
    )
    direct.write_published([row])

    raw = '<html><body><h1>テストゲーム Android</h1><p>最大3,000pt</p></body></html>'
    monkeypatch.setattr(direct, 'fetch_first_party', lambda url, source: (raw, url))
    before = direct.PUBLISHED.read_bytes()

    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == before

    status = json.loads(direct.STATUS.read_text())
    assert status['refreshedRows'] == status['publishedRewardChanges'] == 0
    assert status['games'][0]['comparisonReady'] is False

    items = json.loads(direct.REVIEW.read_text())['items']
    assert len(items) == 1
    item = items[0]
    assert item['reason'] == 'source_specific_reward_parser_required'
    assert item['storedReward'] == '300'
    assert item['storedPlatform'] == 'Android'
    assert item['platformHint'] == 'Android'
    assert 'detectedReward' not in item
    assert 'detectedStrongRewards' not in item
    assert 'detectedWeakRewards' not in item


COINCOME_URL = 'https://cimcome.jp/campaigns/details/12345'


@pytest.fixture
def coincome_markup():
    return f'''<html><head><link rel="canonical" href="{COINCOME_URL}"></head><body>
<main>
<h1>テストゲーム</h1>
<div>600円</div>
<p>新規アプリインストール後、StepUpミッションクリアでキャッシュバック</p>
<div>Android 対象アプリ</div>
<section>ストア概要</section>
<h2>適用端末</h2><p>SP</p>
<h2>キャッシュバック条件</h2>
<h3>承認条件</h3>
<p>新規アプリインストール後、30日以内にStepUpミッションクリアで報酬獲得となります</p>
<p>■ポイント獲得条件</p>
<p>広告クリック後は同一端末・同一ブラウザで条件達成してください</p>
<h3>否認条件</h3>
<p>重複利用、虚偽、不正利用は対象外</p>
<div>リンクをコピーする</div>
</main></body></html>'''


def parse_coincome(raw, requested=COINCOME_URL, final=COINCOME_URL):
    return direct.inspect_coincome_offer(raw, requested, final, ['テストゲーム'])


def test_coincome_review_parser_binds_identity_reward_os_and_full_terms(coincome_markup):
    evidence = parse_coincome(coincome_markup)
    assert evidence['state'] == 'parsed'
    assert evidence['offerId'] == '12345'
    assert evidence['platform'] == 'Android'
    assert evidence['displayedRewardYen'] == 600
    assert evidence['rewardUnit'] == 'JPY-equivalent'
    assert evidence['parserVersion'] == 'coincome-detail-review-v1'
    assert all(marker in evidence['termsText'] for marker in (
        '適用端末', 'キャッシュバック条件', '承認条件', 'ポイント獲得条件', '否認条件'))
    assert len(evidence['evidenceFingerprint']) == 64


@pytest.mark.parametrize('old,new,reason', [
    ('<div>600円</div>', '<div>900円 600円</div>', 'ambiguous_displayed_reward'),
    ('Android 対象アプリ', 'iOS Android 対象アプリ', 'ambiguous_offer_platform'),
    ('Android 対象アプリ', '対象アプリ', 'ambiguous_offer_platform'),
    ('ポイント獲得条件', '成果条件', 'incomplete_offer_terms'),
    ('否認条件', '対象外条件', 'incomplete_offer_terms'),
    ('<section>ストア概要</section>', '', 'missing_offer_header_boundary'),
    ('<h1>テストゲーム</h1>', '<h1>別ゲーム</h1>', 'offer_title_mismatch'),
    ('/campaigns/details/12345', '/campaigns/details/99999', 'canonical_offer_mismatch'),
])
def test_coincome_rejects_ambiguous_or_incomplete_evidence(coincome_markup, old, new, reason):
    evidence = parse_coincome(coincome_markup.replace(old, new))
    assert evidence['state'] == 'review_required'
    assert evidence['reason'] == reason


@pytest.mark.parametrize('url', [
    'http://cimcome.jp/campaigns/details/12345',
    'https://www.cimcome.jp/campaigns/details/12345',
    'https://user@cimcome.jp/campaigns/details/12345',
    'https://cimcome.jp:444/campaigns/details/12345',
    'https://cimcome.jp/campaigns/details/12345/extra',
    'https://cimcome.jp/campaigns/details/12345?ref=test',
])
def test_coincome_rejects_unsupported_identity_urls(coincome_markup, url):
    assert parse_coincome(coincome_markup, requested=url)['state'] == 'review_required'


def test_coincome_terms_change_invalidates_fingerprint(coincome_markup):
    original = parse_coincome(coincome_markup)
    changed = parse_coincome(coincome_markup.replace(
        '広告クリック後は同一端末・同一ブラウザで条件達成してください',
        '広告クリック後30日以内に同一端末・同一ブラウザで条件達成してください'))
    assert original['state'] == changed['state'] == 'parsed'
    assert original['evidenceFingerprint'] != changed['evidenceFingerprint']


def test_coincome_explicit_not_found_page_is_unavailable():
    raw = '<html><body><main>404 Not Found ページが見つかりません</main></body></html>'
    evidence = parse_coincome(raw)
    assert evidence['state'] == 'unavailable'
    assert evidence['reason'] == 'source_offer_unavailable'


@pytest.mark.parametrize('fetch_fails', [False, True])
def test_coincome_is_review_only_and_never_refreshes_published_date(
        coincome_markup, monkeypatch, fetch_fails):
    direct.POLICY.write_text(json.dumps({
        'comparisonSources': ['coincome'],
        'minimumConfirmedSourcesForComparison': 2,
        'games': {'テストゲーム': {'enabled': True}},
    }))
    direct.TARGETS.write_text(json.dumps({'games': [{
        'game': 'テストゲーム',
        'known_urls_by_source': {'coincome': [COINCOME_URL]},
    }]}))
    direct.SOURCES.write_text(json.dumps({'sources': [{
        'id': 'coincome',
        'search_domains': ['cimcome.jp'],
        'direct_listing_urls': [],
        'direct_detail_limit': 6,
    }]}))
    row = dict.fromkeys(direct.FIELDS, '')
    row.update(
        offerKey='coincome-test',
        game='テストゲーム',
        site='coincome',
        reward='600',
        condition='既存要約',
        platform='Android',
        updatedAt='2026-08-31',
        url=COINCOME_URL,
        sourceUrl=COINCOME_URL,
        verified='true',
    )
    direct.write_published([row])
    direct.POLICY.with_name('approved_offer_baselines.json').write_text(json.dumps({
        'schemaVersion': 1,
        'approvals': [{
            'offerKey': row['offerKey'],
            'approved': True,
            'source': 'coincome',
        }],
    }))
    calls = []

    def fetch(url, source):
        calls.append(url)
        if fetch_fails:
            raise HTTPError(url, 404, 'Not Found', {}, None)
        return coincome_markup, url

    monkeypatch.setattr(direct, 'fetch_first_party', fetch)
    before = direct.PUBLISHED.read_bytes()
    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == before
    assert calls == [COINCOME_URL]

    status = json.loads(direct.STATUS.read_text())
    assert status['refreshedRows'] == status['publishedRewardChanges'] == status['apiCalls'] == 0
    assert status['games'][0]['comparisonReady'] is False
    item = json.loads(direct.REVIEW.read_text())['items'][0]
    if fetch_fails:
        assert item['reason'] == 'fetch_failed'
        assert item['error'] == 'http_status_404'
    else:
        assert item['approvalHoldReason'] == 'source_refresh_not_enabled'
        assert item['sourceEvidence']['displayedRewardYen'] == 600
        assert item['platformMatches'] is True
        assert item['requiredChecks'] == ['reward_unit_conversion', 'complete_terms_vs_published_row']


MOPPY_URL = 'https://pc.moppy.jp/ad/detail.php?site_id=12345'
MOPPY_ALT_URL = 'https://pc.moppy.jp/ad/detail.php?s_id=12345'


@pytest.fixture
def moppy_markup():
    return f'''<html><head><link rel="canonical" href="{MOPPY_URL}"></head><body>
<main>
<h1>テストゲーム（StepUp）〖Android〗</h1>
<p>新規アプリインストール後、45日以内に各成果地点到達でクリア</p>
<div>600P</div>
<section>ポイント獲得条件</section>
<p>モッピーでは「1ポイント=1円」のポイントが貯まります。</p>
<p>※ご注意ください。「POINT GET」をタップ後に遷移するページに記載のポイント数と獲得条件が適用となります。</p>
<div>■獲得条件 新規アプリインストール後、45日以内に各成果地点クリアで報酬獲得となります。
〖成果受付期間〗インストール後、45日以内
各成果地点は「POINT GET」をタップ後に遷移するページでご確認ください。
■注意事項 クリックされた時点で表示されていた条件が適用されます。</div>
<h3>広告概要</h3>
</main></body></html>'''


def parse_moppy(raw, requested=MOPPY_URL, final=MOPPY_URL):
    return direct.inspect_moppy_offer(raw, requested, final, ['テストゲーム'])


def test_moppy_review_parser_binds_shell_identity_reward_os_and_terms(moppy_markup):
    evidence = parse_moppy(moppy_markup)
    assert evidence['state'] == 'parsed'
    assert evidence['offerId'] == '12345'
    assert evidence['platform'] == 'Android'
    assert evidence['displayedRewardPoints'] == 600
    assert evidence['rewardUnit'] == 'P'
    assert evidence['baseYenPerPoint'] == 1
    assert evidence['downstreamTermsRequired'] is True
    assert evidence['parserVersion'] == 'moppy-shell-review-v1'
    assert '成果受付期間' in evidence['termsText']
    assert len(evidence['evidenceFingerprint']) == 64


def test_moppy_site_id_and_s_id_are_same_offer_identity(moppy_markup):
    assert direct.moppy_offer_id(MOPPY_URL) == direct.moppy_offer_id(MOPPY_ALT_URL) == '12345'
    evidence = parse_moppy(moppy_markup, requested=MOPPY_URL, final=MOPPY_ALT_URL)
    assert evidence['state'] == 'parsed'


@pytest.mark.parametrize('old,new,reason', [
    ('<div>600P</div>', '<div>600P 900P</div>', 'ambiguous_displayed_reward'),
    ('〖Android〗', '〖Android / iOS〗', 'ambiguous_offer_platform'),
    ('「1ポイント=1円」', '「2ポイント=1円」', 'unit_conversion_review_required'),
    ('POINT GET', '案件ボタン', 'downstream_terms_review_required'),
    ('成果受付期間', '受付期間', 'incomplete_offer_terms'),
    ('■注意事項', '一般注意', 'incomplete_offer_terms'),
    ('<section>ポイント獲得条件</section>', '', 'missing_offer_header_boundary'),
    ('<h1>テストゲーム（StepUp）〖Android〗</h1>', '<h1>別ゲーム（StepUp）〖Android〗</h1>', 'offer_title_mismatch'),
    ('/ad/detail.php?site_id=12345', '/ad/detail.php?site_id=99999', 'canonical_offer_mismatch'),
])
def test_moppy_rejects_ambiguous_or_incomplete_shell_evidence(moppy_markup, old, new, reason):
    evidence = parse_moppy(moppy_markup.replace(old, new))
    assert evidence['state'] == 'review_required'
    assert evidence['reason'] == reason


@pytest.mark.parametrize('url', [
    'http://pc.moppy.jp/ad/detail.php?site_id=12345',
    'https://moppy.jp/ad/detail.php?site_id=12345',
    'https://user@pc.moppy.jp/ad/detail.php?site_id=12345',
    'https://pc.moppy.jp:444/ad/detail.php?site_id=12345',
    'https://pc.moppy.jp/ad/detail.php?site_id=12345&ref=test',
    'https://pc.moppy.jp/ad/detail.php?site_id=12345&s_id=12345',
    'https://pc.moppy.jp/ad/other.php?site_id=12345',
])
def test_moppy_rejects_unsupported_identity_urls(moppy_markup, url):
    assert parse_moppy(moppy_markup, requested=url)['state'] == 'review_required'


def test_moppy_terms_change_invalidates_fingerprint(moppy_markup):
    original = parse_moppy(moppy_markup)
    changed = parse_moppy(moppy_markup.replace(
        'インストール後、45日以内',
        'インストール後、44日以内'))
    assert original['state'] == changed['state'] == 'parsed'
    assert original['evidenceFingerprint'] != changed['evidenceFingerprint']


@pytest.mark.parametrize('fetch_fails', [False, True])
def test_moppy_is_review_only_even_when_shell_matches_published_row(
        moppy_markup, monkeypatch, fetch_fails):
    direct.POLICY.write_text(json.dumps({
        'comparisonSources': ['moppy'],
        'minimumConfirmedSourcesForComparison': 2,
        'games': {'テストゲーム': {'enabled': True}},
    }))
    direct.TARGETS.write_text(json.dumps({'games': [{
        'game': 'テストゲーム',
        'known_urls_by_source': {'moppy': [MOPPY_URL]},
    }]}))
    direct.SOURCES.write_text(json.dumps({'sources': [{
        'id': 'moppy',
        'search_domains': ['pc.moppy.jp'],
        'direct_listing_urls': [],
        'direct_detail_limit': 6,
    }]}))
    row = dict.fromkeys(direct.FIELDS, '')
    row.update(
        offerKey='moppy-test',
        game='テストゲーム',
        site='moppy',
        reward='600',
        condition='既存要約',
        platform='Android',
        updatedAt='2026-08-31',
        url=MOPPY_URL,
        sourceUrl=MOPPY_URL,
        verified='true',
    )
    direct.write_published([row])
    direct.POLICY.with_name('approved_offer_baselines.json').write_text(json.dumps({
        'schemaVersion': 1,
        'approvals': [{
            'offerKey': row['offerKey'],
            'approved': True,
            'source': 'moppy',
        }],
    }))
    calls = []

    def fetch(url, source):
        calls.append(url)
        if fetch_fails:
            raise HTTPError(url, 404, 'Not Found', {}, None)
        return moppy_markup, MOPPY_ALT_URL

    monkeypatch.setattr(direct, 'fetch_first_party', fetch)
    before = direct.PUBLISHED.read_bytes()
    assert direct.main() == 0
    assert direct.PUBLISHED.read_bytes() == before
    assert calls == [MOPPY_URL]

    status = json.loads(direct.STATUS.read_text())
    assert status['refreshedRows'] == status['publishedRewardChanges'] == status['apiCalls'] == 0
    assert status['games'][0]['comparisonReady'] is False
    item = json.loads(direct.REVIEW.read_text())['items'][0]
    if fetch_fails:
        assert item['reason'] == 'fetch_failed'
        assert item['error'] == 'http_status_404'
    else:
        assert item['approvalHoldReason'] == 'source_refresh_not_enabled'
        assert item['sourceEvidence']['displayedRewardPoints'] == 600
        assert item['sourceEvidence']['downstreamTermsRequired'] is True
        assert item['platformMatches'] is True


def test_repository_whiteout_moppy_review_targets_include_current_android_and_ios():
    targets = json.loads((ROOT/'config/game_targets.json').read_text())['games']
    whiteout = next(item for item in targets if item['game'] == 'ホワイトアウト・サバイバル')
    urls = whiteout['known_urls_by_source']['moppy']
    by_id = {direct.moppy_offer_id(url): url for url in urls}
    assert set(by_id) >= {'160375', '160371'}

    rows = list(csv.DictReader((ROOT/'data/published_offers.csv').open(encoding='utf-8', newline='')))
    published_moppy = [row for row in rows
        if row['game'] == 'ホワイトアウト・サバイバル' and row['site'] == 'moppy']
    assert len(published_moppy) == 1
    assert direct.moppy_offer_id(published_moppy[0]['url']) == '160375'
    assert all(direct.moppy_offer_id(row['url']) != '160371' for row in published_moppy)


def test_listing_only_source_skips_stale_known_details_and_preserves_rows(monkeypatch):
    listing = 'https://example.test/list'
    stale = 'https://example.test/detail?id=999'
    direct.POLICY.write_text(json.dumps({
        'comparisonSources': ['testsite'],
        'minimumConfirmedSourcesForComparison': 2,
        'games': {'Game A': {'enabled': True}},
    }))
    direct.TARGETS.write_text(json.dumps({'games': [{
        'game': 'Game A',
        'known_urls_by_source': {'testsite': [stale]},
    }]}))
    direct.SOURCES.write_text(json.dumps({'sources': [{
        'id': 'testsite',
        'search_domains': ['example.test'],
        'direct_listing_urls': [listing],
        'direct_listing_limit': 1,
        'direct_detail_limit': 4,
        'direct_detail_url_hints': ['/detail'],
        'scheduled_known_detail_fetch_enabled': False,
    }]}))
    row = dict.fromkeys(direct.FIELDS, '')
    row.update(
        offerKey='existing',
        game='Game A',
        site='testsite',
        reward='100',
        condition='existing',
        platform='iOS',
        updatedAt='2026-09-01',
        url=stale,
        sourceUrl=stale,
        verified='true',
    )
    direct.write_published([row])
    before = direct.PUBLISHED.read_bytes()
    requested = []

    def fetch(url, source):
        requested.append(url)
        if url == listing:
            return '<body>No matching game today</body>', url
        pytest.fail('stale known detail URL must not be fetched')

    monkeypatch.setattr(direct, 'fetch_first_party', fetch)
    assert direct.main() == 0
    assert requested == [listing]
    assert direct.PUBLISHED.read_bytes() == before

    items = json.loads(direct.REVIEW.read_text())['items']
    assert len(items) == 1
    assert items[0]['reason'] == 'discovery_required'
    assert items[0]['knownDetailFetchEnabled'] is False


def test_listing_only_source_fetches_only_newly_discovered_detail(monkeypatch):
    listing = 'https://example.test/list'
    stale = 'https://example.test/detail?id=999'
    current = 'https://example.test/detail?id=123'
    direct.POLICY.write_text(json.dumps({
        'comparisonSources': ['testsite'],
        'minimumConfirmedSourcesForComparison': 2,
        'games': {'Game A': {'enabled': True}},
    }))
    direct.TARGETS.write_text(json.dumps({'games': [{
        'game': 'Game A',
        'known_urls_by_source': {'testsite': [stale]},
    }]}))
    direct.SOURCES.write_text(json.dumps({'sources': [{
        'id': 'testsite',
        'search_domains': ['example.test'],
        'direct_listing_urls': [listing],
        'direct_listing_limit': 1,
        'direct_detail_limit': 4,
        'direct_detail_url_hints': ['/detail'],
        'scheduled_known_detail_fetch_enabled': False,
    }]}))
    direct.write_published([])
    requested = []

    def fetch(url, source):
        requested.append(url)
        if url == listing:
            return (
                '<body>Game A <a href="/detail?id=123">Game A offer</a></body>',
                listing,
            )
        if url == current:
            return '<body>Game A 累計 100 pt</body>', current
        pytest.fail('unexpected URL')

    monkeypatch.setattr(direct, 'fetch_first_party', fetch)
    assert direct.main() == 0
    assert requested == [listing, current]
    assert stale not in requested
    assert direct.read_published() == []

    items = json.loads(direct.REVIEW.read_text())['items']
    assert any(item['reason'] == 'unpublished_offer_found' and item['url'] == current for item in items)


def test_repository_coincome_uses_listing_only_scheduled_discovery(monkeypatch):
    monkeypatch.setattr(direct, 'SOURCES', ROOT/'config/point_sources.json')
    payload = json.loads((ROOT/'config/point_sources.json').read_text())
    by_id = {source['id']: source for source in payload['sources']}
    coincome = by_id['coincome']
    assert coincome['scheduled_fetch_enabled'] if 'scheduled_fetch_enabled' in coincome else True
    assert coincome['scheduled_known_detail_fetch_enabled'] is False
    assert 'listing' in coincome['scheduled_known_detail_fetch_reason'].lower()
    assert coincome['direct_listing_urls'] == ['https://cimcome.jp/campaigns?_category_id=21']


def test_repository_mementomori_moppy_review_targets_use_current_45_day_pair():
    targets = json.loads((ROOT/'config/game_targets.json').read_text())['games']
    memo = next(item for item in targets if item['game'] == 'メメントモリ')
    urls = memo['known_urls_by_source']['moppy']
    by_id = {direct.moppy_offer_id(url): url for url in urls}
    assert set(by_id) == {'160690', '160688'}

    rows = list(csv.DictReader((ROOT/'data/published_offers.csv').open(encoding='utf-8', newline='')))
    published = [row for row in rows if row['game'] == 'メメントモリ' and row['site'] == 'moppy']
    assert published == []


def test_offerwall_presence_returns_only_known_sanitized_provider_domains():
    secret = 'user-token-DO-NOT-STORE'
    raw = f'''<body>
    <section>Game A
      <a href="https://ow-gf-rewards.com/offers/game-a?uid={secret}#step">Open offerwall</a>
      <a href="https://unknown.example/path?uid={secret}">Unknown provider</a>
      <a href="http://appdriver.jp/path?uid={secret}">Insecure provider</a>
      <a href="https://user@appdriver.jp/path">Credentialed provider</a>
      <a href="https://appdriver.jp:444/path">Unexpected port</a>
    </section>
    </body>'''
    found = direct.discover_offerwall_presence(
        raw,
        'https://example.test/list',
        ['Game A'],
        ['ow-gf-rewards.com', 'appdriver.jp'],
    )
    assert found == ['ow-gf-rewards.com']
    serialized = json.dumps(found)
    assert secret not in serialized
    assert '/offers/' not in serialized
    assert '?' not in serialized
    assert '#' not in serialized


def test_offerwall_presence_requires_target_adjacent_context():
    padding = 'x' * 1600
    raw = (
        '<body>Game A ' + padding +
        '<a href="https://ow-gf-rewards.com/private?uid=secret">Unrelated wall</a>'
        '</body>'
    )
    assert direct.discover_offerwall_presence(
        raw,
        'https://example.test/list',
        ['Game A'],
        ['ow-gf-rewards.com'],
    ) == []


def test_offerwall_presence_is_review_only_and_never_fetched_or_published(monkeypatch):
    listing = 'https://example.test/list'
    secret = 'sensitive-user-id'
    direct.POLICY.write_text(json.dumps({
        'comparisonSources': ['testsite'],
        'minimumConfirmedSourcesForComparison': 2,
        'games': {'Game A': {'enabled': True}},
    }))
    direct.TARGETS.write_text(json.dumps({'games': [{'game': 'Game A'}]}))
    direct.SOURCES.write_text(json.dumps({
        'sources': [{
            'id': 'testsite',
            'search_domains': ['example.test'],
            'direct_listing_urls': [listing],
            'direct_listing_limit': 1,
            'direct_detail_limit': 4,
            'direct_detail_url_hints': ['/detail'],
        }],
        'offerwall_domains_discovered': ['ow-gf-rewards.com'],
        'offerwall_presence_detection': {
            'enabled': True,
            'follow_external_links': False,
            'persist': 'provider_domain_only',
            'require_target_context': True,
        },
    }))
    direct.SOURCES.with_name('offerwall_providers.json').write_text(json.dumps({
        'schemaVersion': 1,
        'providers': [{
            'id': 'gf_rewards',
            'name': 'GF Rewards',
            'presenceDomains': ['ow-gf-rewards.com'],
            'retrievalMode': 'presence_only',
            'followExternalLinks': False,
            'persist': 'provider_domain_only',
        }],
    }))
    row = dict.fromkeys(direct.FIELDS, '')
    row.update(
        offerKey='existing',
        game='Game A',
        site='testsite',
        reward='100',
        condition='existing',
        platform='iOS',
        updatedAt='2026-09-01',
        url='',
        sourceUrl='',
        verified='true',
    )
    direct.write_published([row])
    before = direct.PUBLISHED.read_bytes()
    requested = []

    def fetch(url, source):
        requested.append(url)
        assert url == listing
        return (
            f'<body><section>Game A '
            f'<a href="https://ow-gf-rewards.com/path?uid={secret}">Offerwall</a>'
            f'</section></body>',
            listing,
        )

    monkeypatch.setattr(direct, 'fetch_first_party', fetch)
    assert direct.main() == 0
    assert requested == [listing]
    assert direct.PUBLISHED.read_bytes() == before

    review_text = direct.REVIEW.read_text()
    items = json.loads(review_text)['items']
    assert len(items) == 1
    assert items[0]['reason'] == 'offerwall_presence_candidate'
    assert items[0]['providerDomains'] == ['ow-gf-rewards.com']
    assert items[0]['providerCandidates'] == [{
        'providerId': 'gf_rewards',
        'providerName': 'GF Rewards',
        'domain': 'ow-gf-rewards.com',
        'retrievalMode': 'presence_only',
    }]
    assert secret not in review_text
    assert '/path' not in review_text

    status = json.loads(direct.STATUS.read_text())
    source = status['games'][0]['sources'][0]
    assert source['offerwallPresenceDomains'] == 1
    assert source['offerwallReviewedProviders'] == 1
    assert source['confirmedOffers'] == source['updatedRows'] == 0
    assert source['reviewRequired'] == 1
    assert status['refreshedRows'] == status['publishedRewardChanges'] == 0
    assert status['games'][0]['comparisonReady'] is False


def test_offerwall_presence_detection_fails_closed_without_exact_privacy_contract(monkeypatch):
    listing = 'https://example.test/list'
    direct.POLICY.write_text(json.dumps({
        'comparisonSources': ['testsite'],
        'minimumConfirmedSourcesForComparison': 2,
        'games': {'Game A': {'enabled': True}},
    }))
    direct.TARGETS.write_text(json.dumps({'games': [{'game': 'Game A'}]}))
    direct.write_published([])

    base_source = {
        'sources': [{
            'id': 'testsite',
            'search_domains': ['example.test'],
            'direct_listing_urls': [listing],
            'direct_listing_limit': 1,
            'direct_detail_limit': 4,
            'direct_detail_url_hints': ['/detail'],
        }],
        'offerwall_domains_discovered': ['ow-gf-rewards.com'],
    }
    unsafe_policies = [
        None,
        {'enabled': True, 'follow_external_links': True,
         'persist': 'provider_domain_only', 'require_target_context': True},
        {'enabled': True, 'follow_external_links': False,
         'persist': 'full_url', 'require_target_context': True},
        {'enabled': True, 'follow_external_links': False,
         'persist': 'provider_domain_only', 'require_target_context': False},
    ]

    for policy in unsafe_policies:
        payload = dict(base_source)
        if policy is not None:
            payload['offerwall_presence_detection'] = policy
        direct.SOURCES.write_text(json.dumps(payload))
        monkeypatch.setattr(direct, 'fetch_first_party', lambda url, source: (
            '<body>Game A <a href="https://ow-gf-rewards.com/path?uid=secret">Wall</a></body>',
            listing,
        ))
        assert direct.main() == 0
        items = json.loads(direct.REVIEW.read_text())['items']
        assert len(items) == 1
        assert items[0]['reason'] == 'discovery_required'
        assert 'providerDomains' not in items[0]


def test_repository_offerwall_presence_policy_is_domain_only_and_no_follow():
    payload = json.loads((ROOT/'config/point_sources.json').read_text())
    policy = payload['offerwall_presence_detection']
    assert policy == {
        'enabled': True,
        'follow_external_links': False,
        'persist': 'provider_domain_only',
        'require_target_context': True,
    }
    domains = payload['offerwall_domains_discovered']
    assert len(domains) == len(set(domains))
    assert all('/' not in domain and '?' not in domain and '#' not in domain for domain in domains)


def test_offerwall_presence_does_not_cross_adjacent_offer_cards():
    raw = '''<body>
      <article class="offer-card"><h3>Game A</h3><p>100pt</p></article>
      <article class="offer-card"><h3>Game B</h3>
        <a href="https://ow-gf-rewards.com/path?uid=secret">Open wall</a>
      </article>
    </body>'''
    assert direct.discover_offerwall_presence(
        raw,
        'https://example.test/list',
        ['Game A'],
        ['ow-gf-rewards.com'],
    ) == []


def test_offerwall_presence_accepts_nested_link_inside_same_offer_card():
    raw = '''<body>
      <article class="offer-card">
        <header><h3>Game A</h3></header>
        <div class="actions"><span><a href="https://ow-gf-rewards.com/path?uid=secret">Open wall</a></span></div>
      </article>
      <article class="offer-card"><h3>Game B</h3></article>
    </body>'''
    assert direct.discover_offerwall_presence(
        raw,
        'https://example.test/list',
        ['Game A'],
        ['ow-gf-rewards.com'],
    ) == ['ow-gf-rewards.com']


def test_offerwall_presence_rejects_page_wide_container_even_when_target_exists():
    filler = 'x' * 1500
    raw = (
        '<body><main>Game A ' + filler +
        '<a href="https://ow-gf-rewards.com/path?uid=secret">Open wall</a>'
        '</main></body>'
    )
    assert direct.discover_offerwall_presence(
        raw,
        'https://example.test/list',
        ['Game A'],
        ['ow-gf-rewards.com'],
    ) == []


def test_offerwall_provider_registry_loads_reviewed_gf_rewards_contract(tmp_path):
    path = tmp_path/'offerwall_providers.json'
    path.write_text(json.dumps({
        'schemaVersion': 1,
        'providers': [{
            'id': 'gf_rewards',
            'name': 'GF Rewards',
            'presenceDomains': ['ow-gf-rewards.com'],
            'retrievalMode': 'presence_only',
            'followExternalLinks': False,
            'persist': 'provider_domain_only',
        }],
    }))
    registry = direct.load_offerwall_provider_registry(path)
    assert registry == {
        'ow-gf-rewards.com': {
            'providerId': 'gf_rewards',
            'providerName': 'GF Rewards',
            'domain': 'ow-gf-rewards.com',
            'retrievalMode': 'presence_only',
        }
    }
    assert direct.offerwall_provider_candidates(
        ['ow-gf-rewards.com', 'appdriver.jp'], registry
    ) == [{
        'providerId': 'gf_rewards',
        'providerName': 'GF Rewards',
        'domain': 'ow-gf-rewards.com',
        'retrievalMode': 'presence_only',
    }]


@pytest.mark.parametrize('providers', [
    [{
        'id': 'gf_rewards',
        'presenceDomains': ['ow-gf-rewards.com'],
        'retrievalMode': 'direct_fetch',
        'followExternalLinks': True,
        'persist': 'full_url',
    }],
    [{
        'id': 'gf_rewards',
        'presenceDomains': ['ow-gf-rewards.com'],
        'retrievalMode': 'presence_only',
        'followExternalLinks': False,
        'persist': 'provider_domain_only',
    }, {
        'id': 'other_provider',
        'presenceDomains': ['ow-gf-rewards.com'],
        'retrievalMode': 'presence_only',
        'followExternalLinks': False,
        'persist': 'provider_domain_only',
    }],
])
def test_offerwall_provider_registry_rejects_unsafe_or_duplicate_contracts(tmp_path, providers):
    path = tmp_path/'offerwall_providers.json'
    path.write_text(json.dumps({'schemaVersion': 1, 'providers': providers}))
    with pytest.raises(ValueError):
        direct.load_offerwall_provider_registry(path)


def test_repository_gf_rewards_provider_contract_is_presence_only():
    payload = json.loads((ROOT/'config/offerwall_providers.json').read_text())
    assert payload['schemaVersion'] == 1
    gf = next(item for item in payload['providers'] if item['id'] == 'gf_rewards')
    assert gf['presenceDomains'] == ['ow-gf-rewards.com']
    assert gf['informationDomains'] == ['info.gf-rewards.com']
    assert gf['retrievalMode'] == 'presence_only'
    assert gf['followExternalLinks'] is False
    assert gf['persist'] == 'provider_domain_only'
    assert gf['requiresUserTrackingContext'] is True
    assert gf['privacyEvidenceUrl'] == 'https://info.gf-rewards.com/privacy.html'


def test_repository_appdriver_provider_contract_is_presence_only():
    path = ROOT/'config/offerwall_providers.json'
    payload = json.loads(path.read_text())
    appdriver = next(item for item in payload['providers'] if item['id'] == 'appdriver')
    assert appdriver['presenceDomains'] == ['appdriver.jp']
    assert appdriver['informationDomains'] == ['appdriver.jp']
    assert appdriver['retrievalMode'] == 'presence_only'
    assert appdriver['followExternalLinks'] is False
    assert appdriver['persist'] == 'provider_domain_only'
    assert appdriver['requiresUserTrackingContext'] is True
    assert appdriver['termsEvidenceUrl'] == 'https://appdriver.jp/public/info/terms'
    assert appdriver['integrationEvidenceUrl'].endswith('Reward_for_publisher_ver1.4_English.pdf')

    registry = direct.load_offerwall_provider_registry(path)
    assert registry['appdriver.jp'] == {
        'providerId': 'appdriver',
        'providerName': 'AppDriver',
        'domain': 'appdriver.jp',
        'retrievalMode': 'presence_only',
    }
    assert direct.offerwall_provider_candidates(
        ['appdriver.jp', 'unknown.example'], registry
    ) == [{
        'providerId': 'appdriver',
        'providerName': 'AppDriver',
        'domain': 'appdriver.jp',
        'retrievalMode': 'presence_only',
    }]


def test_repository_skyflag_provider_contract_is_presence_only():
    path = ROOT/'config/offerwall_providers.json'
    payload = json.loads(path.read_text())
    skyflag = next(item for item in payload['providers'] if item['id'] == 'skyflag')
    assert skyflag['presenceDomains'] == ['ow.skyflag.jp']
    assert skyflag['informationDomains'] == ['skyflag.info', 'skyfall.co.jp']
    assert skyflag['retrievalMode'] == 'presence_only'
    assert skyflag['followExternalLinks'] is False
    assert skyflag['persist'] == 'provider_domain_only'
    assert skyflag['anonymousPublicCatalogEstablished'] is False

    registry = direct.load_offerwall_provider_registry(path)
    assert registry['ow.skyflag.jp'] == {
        'providerId': 'skyflag',
        'providerName': 'SKYFLAG',
        'domain': 'ow.skyflag.jp',
        'retrievalMode': 'presence_only',
    }


def test_repository_all_discovered_offerwall_domains_have_reviewed_presence_only_providers():
    source_payload = json.loads((ROOT/'config/point_sources.json').read_text())
    provider_path = ROOT/'config/offerwall_providers.json'
    provider_payload = json.loads(provider_path.read_text())
    registry = direct.load_offerwall_provider_registry(provider_path)

    discovered = set(source_payload['offerwall_domains_discovered'])
    assert set(registry) == discovered
    assert len(discovered) == 9

    expected = {
        'ow-gf-rewards.com': 'gf_rewards',
        'appdriver.jp': 'appdriver',
        'ow.skyflag.jp': 'skyflag',
        'cdn.mychips.io': 'mychips',
        'ow.z.mobu.jp': 'zucks',
        'wall.smaad.net': 'smaad',
        'sdk.tyrads.com': 'tyrads',
        'chobirich.playtimeweb.com': 'adjoe_playtime',
        'offerwall.ayet.io': 'ayet',
    }
    assert {domain: item['providerId'] for domain, item in registry.items()} == expected

    providers = provider_payload['providers']
    assert len(providers) == len({item['id'] for item in providers})
    assert all(item['retrievalMode'] == 'presence_only' for item in providers)
    assert all(item['followExternalLinks'] is False for item in providers)
    assert all(item['persist'] == 'provider_domain_only' for item in providers)


def test_remaining_provider_contracts_keep_user_contextual_walls_presence_only():
    path = ROOT/'config/offerwall_providers.json'
    payload = json.loads(path.read_text())
    by_id = {item['id']: item for item in payload['providers']}

    for provider_id in ('mychips', 'zucks', 'tyrads', 'adjoe_playtime', 'ayet'):
        item = by_id[provider_id]
        assert item['requiresUserTrackingContext'] is True
        assert item['retrievalMode'] == 'presence_only'
        assert item['followExternalLinks'] is False
        assert item['persist'] == 'provider_domain_only'

    assert by_id['smaad']['anonymousPublicCatalogEstablished'] is False
    assert by_id['smaad']['retrievalMode'] == 'presence_only'
    assert by_id['smaad']['followExternalLinks'] is False
