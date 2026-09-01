import importlib.util
import sys
from email.message import Message
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


probe = load('probe_v41', Path('scripts/firecrawl_township_probe.py'))


class FakeResponse:
    def __init__(self, url, body=b'<html><body>ok</body></html>'):
        self.url = url
        self.body = body
        self.headers = Message()
        self.headers['Content-Type'] = 'text/html; charset=utf-8'

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, _limit=-1):
        return self.body


MOPPY = {
    'id': 'moppy', 'name': 'モッピー', 'mobile': True,
    'search_domains': ['moppy.jp', 'pc.moppy.jp'],
    'direct_detail_url_hints': ['ad/detail.php'],
}


def test_mobile_source_uses_smartphone_safari_user_agent(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured['ua'] = req.get_header('User-agent')
        captured['timeout'] = timeout
        return FakeResponse(req.full_url)

    monkeypatch.setattr(probe, 'urlopen', fake_urlopen)
    _, meta = probe.direct_http_get('https://pc.moppy.jp/category/list.php', MOPPY)
    ua = captured['ua']
    assert 'iPhone' in ua
    assert 'Mobile/' in ua
    assert 'Safari/' in ua
    assert meta['deviceMode'] == 'mobile'


def test_non_mobile_source_keeps_bounded_desktop_identity(monkeypatch):
    captured = {}
    source = {'id': 'x', 'search_domains': ['example.com'], 'mobile': False}

    def fake_urlopen(req, timeout=0):
        captured['ua'] = req.get_header('User-agent')
        return FakeResponse(req.full_url)

    monkeypatch.setattr(probe, 'urlopen', fake_urlopen)
    _, meta = probe.direct_http_get('https://example.com/list', source)
    assert 'POIGAMELAB/1.0' in captured['ua']
    assert 'iPhone' not in captured['ua']
    assert meta['deviceMode'] == 'desktop'


def test_mobile_listing_can_discover_moppy_site_id_without_hardcoded_offer(monkeypatch):
    listing = '''<html><body><div class="card">
      <h3>テストゲーム（StepUp）</h3>
      <a href="/ad/detail.php?site_id=123456&utm_source=list"><img alt="詳細"></a>
    </div></body></html>'''.encode()
    detail = '''<html><head><title>テストゲーム（StepUp）</title></head>
      <body><h1>テストゲーム（StepUp）</h1><p>1,234P</p><p>30日以内</p></body></html>'''.encode()
    seen_uas = []

    def fake_urlopen(req, timeout=0):
        seen_uas.append(req.get_header('User-agent'))
        if 'detail.php' in req.full_url:
            return FakeResponse(req.full_url, detail)
        return FakeResponse(req.full_url, listing)

    monkeypatch.setattr(probe, 'urlopen', fake_urlopen)
    source = dict(MOPPY, direct_listing_urls=['https://pc.moppy.jp/category/list.php'], direct_listing_limit=1, direct_detail_limit=4)
    candidates, diag = probe.direct_first_party_collect(source, ['テストゲーム'], {'offerwall_domains_discovered': []})
    assert len(candidates) == 1
    assert probe.offer_identity_url(candidates[0]['url']) == 'https://pc.moppy.jp/ad/detail.php?site_id=123456'
    assert diag['candidateCount'] == 1
    assert diag['listings'][0]['deviceMode'] == 'mobile'
    assert diag['details'][0]['deviceMode'] == 'mobile'
    assert all('iPhone' in ua for ua in seen_uas)


def test_mobile_direct_still_rejects_cross_game_detail(monkeypatch):
    listing = '''<div class="card"><h3>テストゲーム</h3>
      <a href="/ad/detail.php?site_id=123456">詳細</a></div>'''.encode()
    wrong = '<html><body><h1>別ゲーム</h1><p>9,999P</p></body></html>'.encode()

    def fake_urlopen(req, timeout=0):
        return FakeResponse(req.full_url, wrong if 'detail.php' in req.full_url else listing)

    monkeypatch.setattr(probe, 'urlopen', fake_urlopen)
    source = dict(MOPPY, direct_listing_urls=['https://pc.moppy.jp/category/list.php'])
    candidates, diag = probe.direct_first_party_collect(source, ['テストゲーム'], {'offerwall_domains_discovered': []})
    assert candidates == []
    assert diag['details'][0]['targetFound'] is False
