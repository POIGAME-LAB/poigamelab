import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('probe_v39', ROOT/'scripts/firecrawl_township_probe.py')
mod = importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name] = mod; SPEC.loader.exec_module(mod)


class CardContextLinkV39Tests(unittest.TestCase):
    def source(self):
        return {
            'id': 'warau', 'name': 'ワラウ', 'enabled': True,
            'start_url': 'https://www.warau.jp/contents/point/category?point_group=2',
            'search_domains': ['warau.jp', 'www.warau.jp'],
            'direct_listing_urls': ['https://www.warau.jp/contents/point/category?point_group=2'],
            'direct_listing_limit': 1, 'direct_detail_limit': 4,
            'known_target_urls': [], 'prefer_known_pages': False,
            'direct_detail_url_hints': ['pointEntrance.php'],
        }

    def test_image_only_anchor_uses_sibling_title_in_same_card(self):
        html = '''
        <ul class="offers"><li class="offer-card">
          <a class="thumb" href="/contents/point/pointEntrance.php?pl=pc_categoryService&point_id=205390"><img src="wos.jpg"></a>
          <div class="body"><h3>ホワイトアウト・サバイバル（StepUp）</h3><p>ゲーム案件</p></div>
        </li></ul>'''
        links = mod.target_adjacent_first_party_links(
            html, 'https://www.warau.jp/contents/point/category?point_group=2', self.source(), ['ホワイトアウト・サバイバル'])
        self.assertEqual(links, ['https://www.warau.jp/contents/point/pointEntrance.php?pl=pc_categoryService&point_id=205390'])

    def test_whole_card_click_with_nested_title_is_found(self):
        html = '''<article class="card"><a href="/contents/point/pointEntrance.php?point_id=205390">
          <div><img src="x"><span class="title">ホワイトアウト・サバイバル（StepUp）</span></div>
        </a></article>'''
        links = mod.target_adjacent_first_party_links(html, 'https://www.warau.jp/list', self.source(), ['ホワイトアウト・サバイバル'])
        self.assertEqual(len(links), 1)
        self.assertIn('point_id=205390', links[0])

    def test_same_offer_card_links_with_tracking_variants_are_deduped_by_identity(self):
        html = """<div class='card'>
          <a href='/contents/point/pointEntrance.php?pl=image&point_id=205390'><img src='x'></a>
          <h3>ホワイトアウト・サバイバル（StepUp）</h3>
          <a href='/contents/point/pointEntrance.php?pl=button&point_id=205390'>詳細を見る</a>
        </div>"""
        links = mod.target_adjacent_first_party_links(html, 'https://www.warau.jp/list', self.source(), ['ホワイトアウト・サバイバル'])
        self.assertEqual(len(links), 1)
        self.assertEqual(mod.offer_identity_url(links[0]),
                         'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205390')

    def test_distinct_public_offer_ids_in_same_target_card_remain_distinct(self):
        html = """<div class='card'>
          <h3>ホワイトアウト・サバイバル（StepUp）</h3>
          <a href='/contents/point/pointEntrance.php?point_id=205390'>iOS</a>
          <a href='/contents/point/pointEntrance.php?point_id=205391'>Android</a>
        </div>"""
        links = mod.target_adjacent_first_party_links(html, 'https://www.warau.jp/list', self.source(), ['ホワイトアウト・サバイバル'])
        self.assertEqual({mod.offer_identity_url(x) for x in links}, {
            'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205390',
            'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205391',
        })

    def test_neighbouring_card_target_does_not_bless_unrelated_detail(self):
        html = '''<div class="listing">
          <div class="card"><a href="/contents/point/pointEntrance.php?point_id=111"><img src="a"></a><h3>別ゲームA</h3></div>
          <div class="card"><a href="/contents/point/pointEntrance.php?point_id=205390"><img src="b"></a><h3>ホワイトアウト・サバイバル（StepUp）</h3></div>
          <div class="card"><a href="/contents/point/pointEntrance.php?point_id=333"><img src="c"></a><h3>別ゲームC</h3></div>
        </div>'''
        links = mod.target_adjacent_first_party_links(html, 'https://www.warau.jp/list', self.source(), ['ホワイトアウト・サバイバル'])
        self.assertEqual([mod.offer_identity_url(x) for x in links],
                         ['https://www.warau.jp/contents/point/pointEntrance.php?point_id=205390'])

    def test_page_level_target_mention_cannot_bless_unrelated_offer_link(self):
        html = '''<div class="page"><header>ホワイトアウト・サバイバル特集</header>
          <div class="listing">
            <div class="card"><a href="/contents/point/pointEntrance.php?point_id=111"><img src="a"></a><h3>別ゲームA</h3></div>
            <div class="card"><a href="/contents/point/pointEntrance.php?point_id=222"><img src="b"></a><h3>別ゲームB</h3></div>
          </div>
        </div>'''
        links = mod.target_adjacent_first_party_links(html, 'https://www.warau.jp/list', self.source(), ['ホワイトアウト・サバイバル'])
        self.assertEqual(links, [])

    def test_non_detail_navigation_link_is_not_accepted_from_target_card(self):
        html = '''<div class="card"><a href="/help"><img src="x"></a><h3>ホワイトアウト・サバイバル</h3></div>'''
        links = mod.target_adjacent_first_party_links(html, 'https://www.warau.jp/list', self.source(), ['ホワイトアウト・サバイバル'])
        self.assertEqual(links, [])

    def test_card_context_candidate_still_requires_detail_page_target_confirmation(self):
        source = self.source()
        listing = source['direct_listing_urls'][0]
        detail = 'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205390'
        pages = {
            listing: (f'<div class="card"><a href="{detail}"><img></a><h3>ホワイトアウト・サバイバル（StepUp）</h3></div>',
                      {'bytes': 150, 'truncated': False}),
            detail: ('<title>別ゲーム</title><main><h1>別ゲーム</h1><p>1000pt</p></main>',
                     {'bytes': 90, 'truncated': False}),
        }
        candidates, diag = mod.direct_first_party_collect(
            source, ['ホワイトアウト・サバイバル'], {'offerwall_domains_discovered': []},
            fetcher=lambda url, src: pages[url])
        self.assertEqual(candidates, [])
        self.assertEqual(diag['listings'][0]['detailLinks'], 1)
        self.assertFalse(diag['details'][0]['targetFound'])

    def test_card_context_then_confirmed_detail_passes_to_candidate(self):
        source = self.source()
        listing = source['direct_listing_urls'][0]
        detail = 'https://ssl.warau.jp/contents/point/pointEntrance.php?pl=pc_categoryService&point_id=205390'
        pages = {
            listing: (f'<div class="card"><a href="{detail}"><img></a><h3>ホワイトアウト・サバイバル（StepUp）</h3></div>',
                      {'bytes': 150, 'truncated': False}),
            detail: ('<title>ホワイトアウト・サバイバル（StepUp）</title><main><h1>ホワイトアウト・サバイバル</h1><p>最大12,500pt</p></main>',
                     {'bytes': 140, 'truncated': False}),
        }
        candidates, diag = mod.direct_first_party_collect(
            source, ['ホワイトアウト・サバイバル'], {'offerwall_domains_discovered': []},
            fetcher=lambda url, src: pages[url])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['kind'], 'direct_official_detail')
        self.assertEqual(mod.offer_identity_url(candidates[0]['url']),
                         'https://ssl.warau.jp/contents/point/pointEntrance.php?point_id=205390')
        self.assertEqual(diag['candidateCount'], 1)

    def test_registered_domain_allows_www_to_ssl_subdomain_redirect(self):
        source = self.source()
        class Headers:
            def get_content_charset(self): return 'utf-8'
        class Response:
            headers = Headers()
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return 'https://ssl.warau.jp/contents/point/pointEntrance.php?point_id=205390'
            def read(self, n): return '<h1>ホワイトアウト・サバイバル</h1>'.encode()
        with patch.object(mod, 'urlopen', return_value=Response()):
            body, meta = mod.direct_http_get('https://www.warau.jp/contents/point/pointEntrance.php?point_id=205390', source)
        self.assertIn('ホワイトアウト・サバイバル', body)
        self.assertFalse(meta['truncated'])

    def test_collect_firecrawl_uses_card_context_direct_candidate_and_skips_402_path(self):
        source = self.source()
        cfg = {
            'target': {'game': 'ホワイトアウト・サバイバル', 'aliases': ['ホワイトアウト・サバイバル']},
            'sources': [source], 'offerwall_domains_discovered': []
        }
        listing = source['direct_listing_urls'][0]
        detail = 'https://ssl.warau.jp/contents/point/pointEntrance.php?point_id=205390'
        pages = {
            listing: ('<div class="offer-card"><a href="'+detail+'"><img src="wos.jpg"></a>'
                      '<div><h3>ホワイトアウト・サバイバル（StepUp）</h3></div></div>',
                      {'bytes': 180, 'truncated': False}),
            detail: ('<title>ホワイトアウト・サバイバル（StepUp）</title><h1>ホワイトアウト・サバイバル</h1><p>最大12,500pt</p>',
                     {'bytes': 150, 'truncated': False}),
        }
        with patch.object(mod, 'probe_known_pages', return_value=([], [])), \
             patch.object(mod, 'direct_http_get', side_effect=lambda url, src: pages[url]), \
             patch.object(mod, 'direct_scrape', side_effect=AssertionError('Firecrawl path must not run after direct success')), \
             patch.object(mod, 'domain_search', side_effect=AssertionError('Firecrawl search must not run after direct success')):
            candidates, diagnostics = mod.collect_firecrawl('expired-firecrawl-key', cfg)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['kind'], 'direct_official_detail')
        self.assertEqual(diagnostics[0]['mode'], 'direct_official_fast_path')
        self.assertTrue(diagnostics[0]['search']['skipped'])



if __name__ == '__main__':
    unittest.main()
