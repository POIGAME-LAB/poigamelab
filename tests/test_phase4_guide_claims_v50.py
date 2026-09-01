import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('claims',ROOT/'scripts'/'extract_guide_claims.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
DOC={'evidence':[{'game':'Game A','url':'https://guide.example/a','sourceType':'community_guide','targetConfirmed':True,'status':'quarantined'}]}
def fetch(url): return '<p>Game Aでは城レベル10を3日で目指す。資源箱は温存する。</p>',{'httpStatus':200}
def ai_with(claims): return lambda *args:{'claims':claims}
def test_grounded_claim_passes_and_stays_quarantined():
 r=m.run(DOC,'k',fetcher=fetch,ai=ai_with([{'sourceId':'s1','category':'timeline','claim':'城レベル10を3日で目指す','evidenceQuote':'城レベル10を3日で目指す'}]))
 assert len(r['claims'])==1 and r['claims'][0]['status']=='validated_quarantine' and r['publicationWrites']==0
def test_hallucinated_quote_rejected():
 r=m.run(DOC,'k',fetcher=fetch,ai=ai_with([{'sourceId':'s1','category':'tip','claim':'課金必須','evidenceQuote':'課金必須'}]))
 assert r['claims']==[] and r['diagnostics'][0]['rejected']['quote_not_in_source']==1
def test_unknown_source_rejected():
 r=m.run(DOC,'k',fetcher=fetch,ai=ai_with([{'sourceId':'s9','category':'tip','claim':'資源箱は温存する','evidenceQuote':'資源箱は温存する'}]))
 assert r['claims']==[] and r['diagnostics'][0]['rejected']['unknown_source']==1
def test_invalid_category_rejected():
 r=m.run(DOC,'k',fetcher=fetch,ai=ai_with([{'sourceId':'s1','category':'opinion','claim':'資源箱は温存する','evidenceQuote':'資源箱は温存する'}]))
 assert r['claims']==[]
def test_numeric_claim_requires_same_number_in_quote():
 r=m.run(DOC,'k',fetcher=fetch,ai=ai_with([{'sourceId':'s1','category':'timeline','claim':'城レベル20を3日で目指す','evidenceQuote':'3日で目指す'}]))
 assert r['claims']==[] and r['diagnostics'][0]['rejected']['numeric_not_grounded']==1
def test_numeric_grounding_rejects_substring_number_match():
 r=m.run(DOC,'k',fetcher=lambda u:('<p>Game Aでは城レベル120を目指す。</p>',{'httpStatus':200}),ai=ai_with([{'sourceId':'s1','category':'timeline','claim':'城レベル20を目指す','evidenceQuote':'城レベル120を目指す'}]))
 assert r['claims']==[] and r['diagnostics'][0]['rejected']['numeric_not_grounded']==1
def test_duplicate_claim_same_source_removed():
 c={'sourceId':'s1','category':'tip','claim':'資源箱は温存する','evidenceQuote':'資源箱は温存する'}
 r=m.run(DOC,'k',fetcher=fetch,ai=ai_with([c,c])); assert len(r['claims'])==1 and r['diagnostics'][0]['rejected']['duplicate']==1
def test_ai_failure_fails_closed_without_claims():
 def bad(*a): raise RuntimeError('temporary')
 r=m.run(DOC,'k',fetcher=fetch,ai=bad); assert r['claims']==[] and r['apiCalls']==1 and 'aiError' in r['diagnostics'][0]
def test_fetch_failure_skips_ai_call():
 def badfetch(u): raise RuntimeError('403')
 r=m.run(DOC,'k',fetcher=badfetch,ai=lambda *a:(_ for _ in ()).throw(AssertionError()))
 assert r['apiCalls']==0 and r['claims']==[]
def test_target_must_still_exist_after_refetch():
 r=m.run(DOC,'k',fetcher=lambda u:('Different Game only',{'httpStatus':200}),ai=lambda *a:(_ for _ in ()).throw(AssertionError()))
 assert r['apiCalls']==0
def test_one_ai_call_per_game_not_per_page():
 doc={'evidence':[dict(DOC['evidence'][0]),dict(DOC['evidence'][0],url='https://guide.example/b')]}; calls=[]
 def a(*args): calls.append(1); return {'claims':[]}
 r=m.run(doc,'k',fetcher=fetch,ai=a); assert len(calls)==1 and r['apiCalls']==1
def test_max_eight_refetches_per_game():
 doc={'evidence':[dict(DOC['evidence'][0],url=f'https://guide.example/{i}') for i in range(20)]}; calls=[]
 def f(u): calls.append(u); return fetch(u)
 m.run(doc,'k',fetcher=f,ai=ai_with([])); assert len(calls)==8
def test_missing_gemini_key_fails_closed():
 try:m.run(DOC,'',fetcher=fetch,ai=ai_with([]))
 except RuntimeError as e: assert 'GEMINI_API_KEY' in str(e)
 else: raise AssertionError()
def test_non_quarantined_or_unconfirmed_evidence_ignored():
 doc={'evidence':[dict(DOC['evidence'][0],status='published'),dict(DOC['evidence'][0],targetConfirmed=False)]}
 r=m.run(doc,'k',fetcher=lambda u:(_ for _ in ()).throw(AssertionError()),ai=ai_with([])); assert r['apiCalls']==0
def test_prompt_forbids_inference_and_requires_quote():
 p=m.build_prompt('Game A',[{'sourceId':'s1','sourceType':'community_guide','text':'Game A','url':'x','game':'Game A'}])
 assert '推測' in p and 'evidenceQuote' in p and '数字' in p
def test_safe_error_redacts_keys():
 assert 'SECRET' not in m.safe_error(RuntimeError('api_key=SECRET'))
