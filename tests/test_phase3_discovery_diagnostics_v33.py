import importlib.util, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('trend_v33',ROOT/'scripts/discover_trending_games.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class DiscoveryDiagnosticsV33Tests(unittest.TestCase):
    def test_status_preserves_per_source_failure_details(self):
        result={
            'generatedAt':'2026-08-31T00:00:00+00:00',
            'summary':{'searchResults':0,'candidates':0,'newReviewCandidates':0,'failedSources':1},
            'diagnostics':[{
                'sourceId':'warau-new','ok':False,'results':0,'fallbackAttempted':True,
                'fallbackResults':0,'searchError':'HTTP Error 503: Service Unavailable',
                'fallbackErrors':['timed out']
            }]
        }
        status=mod.build_status(result)
        self.assertFalse(status['ok'])
        self.assertEqual(status['diagnostics'][0]['sourceId'],'warau-new')
        self.assertTrue(status['diagnostics'][0]['fallbackAttempted'])
        self.assertIn('503',status['diagnostics'][0]['searchError'])
        self.assertEqual(status['diagnostics'][0]['fallbackErrors'],['timed out'])

    def test_status_marks_healthy_search_without_fallback(self):
        result={
            'generatedAt':'2026-08-31T00:00:00+00:00',
            'summary':{'searchResults':2,'candidates':1,'newReviewCandidates':1,'failedSources':0},
            'diagnostics':[{'sourceId':'x-poikatsu','ok':True,'results':2,'fallbackAttempted':False,'fallbackResults':0}]
        }
        status=mod.build_status(result)
        self.assertTrue(status['ok'])
        self.assertEqual(status['diagnostics'][0]['searchResults'],2)
        self.assertFalse(status['diagnostics'][0]['fallbackAttempted'])

    def test_error_text_redacts_secrets_and_flattens_lines(self):
        text='Authorization: Bearer abcDEF123\napi_key=supersecret timeout'
        safe=mod._safe_error_text(text)
        self.assertNotIn('abcDEF123',safe)
        self.assertNotIn('supersecret',safe)
        self.assertNotIn('\n',safe)
        self.assertIn('[REDACTED]',safe)

if __name__=='__main__': unittest.main()
