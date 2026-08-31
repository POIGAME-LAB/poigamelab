import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('collector_v38', ROOT/'scripts/firecrawl_township_probe.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


class DirectResearchV38Tests(unittest.TestCase):
    def source(self, sid='warau', domain='warau.jp'):
        return {
            'id': sid, 'name': sid, 'enabled': True,
            'start_url': f'https://www.{domain}/list',
            'search_domains': [domain, f'www.{domain}'],
            'direct_listing_urls': [f'https://www.{domain}/list?page=1'],
            'direct_listing_limit': 1, 'direct_detail_limit': 4,
            'known_target_urls': [], 'prefer_known_pages': False,
        }

    def test_target_adjacent_links_keep_public_offer_identity_and_reject_external(self):
        source = self.source()
        html = '''<a href="/contents/point/pointEntrance.php?pl=tracking&point_id=205390">ホワイトアウト・サバイバル（StepUp）</a>
                  <a href="https://evil.example/x?id=1">ホワイトアウト・サバイバル</a>'''
        links = mod.target_adjacent_first_party_links(
            html, 'https://www.warau.jp/list?page=1', source, ['ホワイトアウト・サバイバル'])
        self.assertEqual(len(links), 1)
        self.assertIn('point_id=205390', links[0])
        self.assertEqual(mod.offer_identity_url(links[0]),
                         'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205390')

    def test_listing_is_discovery_only_detail_must_confirm_target(self):
        source = self.source()
        pages = {
            'https://www.warau.jp/list?page=1': (
                '<a href="/contents/point/pointEntrance.php?point_id=205390">ホワイトアウト・サバイバル（StepUp）</a>',
                {'bytes': 100, 'truncated': False}),
            'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205390': (
                '<title>別ゲーム</title><h1>別ゲーム</h1><p>1000pt</p>',
                {'bytes': 80, 'truncated': False}),
        }
        def fake_fetch(url, source): return pages[url]
        candidates, diag = mod.direct_first_party_collect(
            source, ['ホワイトアウト・サバイバル'], {'offerwall_domains_discovered': []}, fetcher=fake_fetch)
        self.assertEqual(candidates, [])
        self.assertTrue(diag['listings'][0]['targetFound'])
        self.assertFalse(diag['details'][0]['targetFound'])

    def test_confirmed_first_party_detail_becomes_exact_candidate(self):
        source = self.source()
        detail = 'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205390&pl=pc_categoryService'
        pages = {
            'https://www.warau.jp/list?page=1': (
                f'<a href="{detail}">ホワイトアウト・サバイバル（StepUp）</a>',
                {'bytes': 100, 'truncated': False}),
            detail: (
                '<title>ホワイトアウト・サバイバル（StepUp）</title><h1>ホワイトアウト・サバイバル（StepUp）</h1><p>最大12,500 pt</p>',
                {'bytes': 140, 'truncated': False}),
        }
        candidates, diag = mod.direct_first_party_collect(
            source, ['ホワイトアウト・サバイバル'], {'offerwall_domains_discovered': []},
            fetcher=lambda url, source: pages[url])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['kind'], 'direct_official_detail')
        self.assertEqual(mod.offer_identity_url(candidates[0]['url']),
                         'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205390')
        self.assertIn('12,500', candidates[0]['markdown'])
        self.assertEqual(diag['candidateCount'], 1)

    def test_direct_success_skips_all_firecrawl_calls_for_that_source(self):
        source = self.source()
        cfg = {'target': {'game': 'ホワイトアウト・サバイバル', 'aliases': ['ホワイトアウト・サバイバル']},
               'sources': [source], 'offerwall_domains_discovered': []}
        candidate = mod.compact_candidate(source, 'direct_official_detail',
            'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205390',
            title='ホワイトアウト・サバイバル', markdown='ホワイトアウト・サバイバル 12,500pt')
        with patch.object(mod, 'probe_known_pages', return_value=([], [])), \
             patch.object(mod, 'direct_first_party_collect', return_value=([candidate], {'attempted': True, 'candidateCount': 1, 'allListingsFetched': True})), \
             patch.object(mod, 'direct_scrape', side_effect=AssertionError('Firecrawl scrape must be skipped')), \
             patch.object(mod, 'domain_search', side_effect=AssertionError('Firecrawl search must be skipped')):
            candidates, diagnostics = mod.collect_firecrawl('expired-key', cfg)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(diagnostics[0]['mode'], 'direct_official_fast_path')
        self.assertTrue(diagnostics[0]['search']['skipped'])

    def test_other_source_402_is_fail_soft_and_does_not_erase_direct_candidate(self):
        warau = self.source('warau', 'warau.jp')
        moppy = self.source('moppy', 'moppy.jp')
        cfg = {'target': {'game': 'ホワイトアウト・サバイバル', 'aliases': ['ホワイトアウト・サバイバル']},
               'sources': [warau, moppy], 'offerwall_domains_discovered': []}
        candidate = mod.compact_candidate(warau, 'direct_official_detail',
            'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205390',
            title='ホワイトアウト・サバイバル', markdown='ホワイトアウト・サバイバル 12,500pt')
        def direct_result(source, aliases, cfg):
            if source['id'] == 'warau':
                return [candidate], {'attempted': True, 'candidateCount': 1, 'allListingsFetched': True}
            return [], {'attempted': True, 'candidateCount': 0, 'allListingsFetched': True}
        with patch.object(mod, 'probe_known_pages', return_value=([], [])), \
             patch.object(mod, 'direct_first_party_collect', side_effect=direct_result), \
             patch.object(mod, 'direct_scrape', side_effect=RuntimeError('HTTP Error 402: Payment Required')), \
             patch.object(mod, 'domain_search', side_effect=RuntimeError('HTTP Error 402: Payment Required')):
            candidates, diagnostics = mod.collect_firecrawl('expired-key', cfg)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(next(d for d in diagnostics if d['source_id']=='warau')['mode'], 'direct_official_fast_path')
        mdiag = next(d for d in diagnostics if d['source_id']=='moppy')
        self.assertFalse(mdiag['search']['ok'])
        complete, reasons = mod.assess_collection_completeness(diagnostics)
        self.assertFalse(complete)
        self.assertIn('moppy:search_failed', reasons)

    def test_missing_firecrawl_key_is_allowed_after_direct_success(self):
        source = self.source()
        cfg = {'target': {'game': 'G', 'aliases': ['G']}, 'sources': [source], 'offerwall_domains_discovered': []}
        candidate = mod.compact_candidate(source, 'direct_official_detail', 'https://www.warau.jp/x?id=1', markdown='G 1000pt')
        with patch.object(mod, 'probe_known_pages', return_value=([], [])), \
             patch.object(mod, 'direct_first_party_collect', return_value=([candidate], {'attempted': True, 'candidateCount': 1, 'allListingsFetched': True})):
            candidates, diagnostics = mod.collect_firecrawl('', cfg)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(diagnostics[0]['mode'], 'direct_official_fast_path')

    def test_config_direct_research_is_bounded_and_bridge_only_requires_gemini(self):
        cfg = json.loads((ROOT/'config/point_sources.json').read_text())
        for source in cfg['sources']:
            self.assertLessEqual(len(source.get('direct_listing_urls') or []), 2)
            self.assertLessEqual(int(source.get('direct_detail_limit', 4)), 4)
        bridge = (ROOT/'scripts/research_offer_bridge.py').read_text()
        self.assertIn("('GEMINI_API_KEY',)", bridge)
        self.assertNotIn("('FIRECRAWL_API_KEY','GEMINI_API_KEY')", bridge)

    def test_direct_detail_survives_existing_v20_strict_same_offer_gate(self):
        source = self.source()
        url = 'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205390&pl=pc_categoryService'
        candidate = mod.compact_candidate(source, 'direct_official_detail', url,
            title='ホワイトアウト・サバイバル（StepUp）',
            markdown='ホワイトアウト・サバイバル（StepUp） 累計 12,500 pt 初回アプリインストール後、StepUpミッションをクリア')
        verified = {'offers': [{
            'site': 'warau', 'url': url, 'evidence_urls': [url], 'reward_yen': 12500,
            'platform': 'iOS', 'condition': '初回アプリインストール後、StepUpミッションをクリア', 'reason': 'test'
        }]}
        cfg = {'sources': [source], 'offerwall_domains_discovered': []}
        mod.apply_deterministic_enrichment(verified, [candidate], cfg)
        offer = verified['offers'][0]
        self.assertTrue(offer['auto_publish_ready'], offer['deterministic_checks'])
        self.assertTrue(offer['deterministic_checks']['evidence_same_offer_identity'])
        self.assertTrue(offer['deterministic_checks']['exact_identity_candidate_present'])

    def test_direct_http_rejects_cross_domain_redirect(self):
        source = self.source()
        class Headers:
            def get_content_charset(self): return 'utf-8'
        class Response:
            headers = Headers()
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return 'https://evil.example/redirected'
            def read(self, n): return b'<html>target</html>'
        with patch.object(mod, 'urlopen', return_value=Response()):
            with self.assertRaisesRegex(ValueError, 'redirect'):
                mod.direct_http_get('https://www.warau.jp/list', source)

    def test_direct_http_response_size_is_bounded(self):
        source = self.source()
        class Headers:
            def get_content_charset(self): return 'utf-8'
        class Response:
            headers = Headers()
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return 'https://www.warau.jp/list'
            def read(self, n): return b'x' * n
        with patch.object(mod, 'urlopen', return_value=Response()):
            body, meta = mod.direct_http_get('https://www.warau.jp/list', source, max_bytes=100)
        self.assertEqual(len(body), 100)
        self.assertTrue(meta['truncated'])

if __name__ == '__main__':
    unittest.main()
