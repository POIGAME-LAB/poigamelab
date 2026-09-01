import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
import pytest
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

def test_v501_summary_identifies_ai_no_proposals_without_changing_gate():
 r=m.run(DOC,'k',fetcher=fetch,ai=ai_with([]))
 s=m.summarize_result(r)
 assert s['zeroClaimReason']=='ai_no_proposals'
 assert s['totals']['refetchedSources']==1
 assert s['totals']['proposed']==0
 assert s['totals']['validated']==0
 assert s['rejected']=={}

def test_v501_summary_identifies_all_proposals_rejected():
 r=m.run(DOC,'k',fetcher=fetch,ai=ai_with([{'sourceId':'s1','category':'tip','claim':'課金必須','evidenceQuote':'課金必須'}]))
 s=m.summarize_result(r)
 assert s['zeroClaimReason']=='all_proposals_rejected'
 assert s['totals']['proposed']==1
 assert s['totals']['validated']==0
 assert s['rejected']=={'quote_not_in_source':1}

def test_v501_summary_identifies_ai_error_without_leaking_error_text():
 def bad(*a): raise RuntimeError('authorization api_key=SECRET')
 r=m.run(DOC,'k',fetcher=fetch,ai=bad)
 s=m.summarize_result(r)
 assert s['zeroClaimReason']=='ai_error'
 assert s['totals']['aiErrors']==1
 assert s['games'][0]['aiError'] is True
 assert 'SECRET' not in str(s)

def test_v501_summary_identifies_malformed_claims_payload():
 r=m.run(DOC,'k',fetcher=fetch,ai=lambda *a:{'claims':'not-a-list'},sleeper=lambda _:None)
 s=m.summarize_result(r)
 assert s['zeroClaimReason']=='ai_malformed_claims_payload'
 assert s['totals']['malformedClaimsPayloads']==2
 assert s['totals']['aiAttempts']==2
 assert s['totals']['aiRetries']==1

def test_v501_summary_identifies_no_refetched_sources_and_target_missing():
 r=m.run(DOC,'k',fetcher=lambda u:('Different Game only',{'httpStatus':200}),ai=lambda *a:(_ for _ in ()).throw(AssertionError()))
 s=m.summarize_result(r)
 assert s['zeroClaimReason']=='no_refetched_sources'
 assert s['totals']['targetMissing']==1
 assert s['totals']['aiCalls']==0

def test_v501_summary_success_has_no_zero_claim_reason():
 r=m.run(DOC,'k',fetcher=fetch,ai=ai_with([{'sourceId':'s1','category':'tip','claim':'資源箱は温存する','evidenceQuote':'資源箱は温存する'}]))
 s=m.summarize_result(r)
 assert s['zeroClaimReason'] is None
 assert s['totals']['validated']==1

def test_v501_summary_aggregates_multiple_game_diagnostics_safely():
 doc={'evidence':[dict(DOC['evidence'][0]),{'game':'Game B','url':'https://other.example/b','sourceType':'community_guide','targetConfirmed':True,'status':'quarantined'}]}
 def f(url):
  if 'other.example' in url: return '<p>Game Bでは素材を温存する。</p>',{'httpStatus':200}
  return fetch(url)
 r=m.run(doc,'k',fetcher=f,ai=ai_with([]))
 s=m.summarize_result(r)
 assert s['totals']['games']==2
 assert s['totals']['inputEvidence']==2
 assert s['totals']['refetchedSources']==2
 assert s['totals']['aiCalls']==2
 assert len(s['games'])==2


def test_v502_transient_ai_failure_retries_once_and_recovers():
 calls=[]
 def flaky(*args):
  calls.append(1)
  if len(calls)==1: raise m.GeminiCallError('upstream_http',True,'temporary upstream')
  return {'claims':[{'sourceId':'s1','category':'tip','claim':'資源箱は温存する','evidenceQuote':'資源箱は温存する'}]}
 r=m.run(DOC,'k',fetcher=fetch,ai=flaky,sleeper=lambda _:None)
 d=r['diagnostics'][0]; s=m.summarize_result(r)
 assert len(calls)==2 and r['apiCalls']==2 and len(r['claims'])==1
 assert d['aiAttempts']==2 and d['aiRetries']==1 and d['aiTransientFailures']==1 and d['aiRecoveredAfterRetry']==1
 assert d['retryKinds']=={'upstream_http':1} and 'aiError' not in d
 assert s['totals']['aiRecoveredAfterRetry']==1 and s['retryKinds']=={'upstream_http':1}
 assert m.extraction_complete(s) is True


def test_v502_retry_exhaustion_is_bounded_and_incomplete():
 calls=[]
 def down(*args):
  calls.append(1)
  raise m.GeminiCallError('rate_limited',True,'429')
 r=m.run(DOC,'k',fetcher=fetch,ai=down,sleeper=lambda _:None)
 d=r['diagnostics'][0]; s=m.summarize_result(r)
 assert len(calls)==2 and r['apiCalls']==2 and r['claims']==[]
 assert d['aiAttempts']==2 and d['aiRetries']==1 and d['aiTransientFailures']==2
 assert d['aiErrorKind']=='rate_limited' and d['retryKinds']=={'rate_limited':1}
 assert s['zeroClaimReason']=='ai_error' and s['totals']['aiErrors']==1
 assert m.extraction_complete(s) is False


def test_v502_nonretryable_ai_failure_never_retries():
 calls=[]
 def auth(*args):
  calls.append(1)
  raise m.GeminiCallError('auth_http',False,'403')
 r=m.run(DOC,'k',fetcher=fetch,ai=auth,sleeper=lambda _:None)
 d=r['diagnostics'][0]
 assert len(calls)==1 and r['apiCalls']==1
 assert d['aiAttempts']==1 and d['aiRetries']==0 and d['aiErrorKind']=='auth_http'


def test_v502_malformed_claims_payload_gets_one_bounded_retry():
 calls=[]
 def flaky(*args):
  calls.append(1)
  if len(calls)==1: return {'claims':'bad-shape'}
  return {'claims':[{'sourceId':'s1','category':'tip','claim':'資源箱は温存する','evidenceQuote':'資源箱は温存する'}]}
 r=m.run(DOC,'k',fetcher=fetch,ai=flaky,sleeper=lambda _:None)
 d=r['diagnostics'][0]
 assert len(calls)==2 and r['apiCalls']==2 and len(r['claims'])==1
 assert d['malformedClaimsPayload']==1 and d['aiRecoveredAfterRetry']==1
 assert d['retryKinds']=={'malformed_claims_payload':1}


def test_v502_network_error_is_retryable_but_still_bounded():
 calls=[]
 def flaky(*args):
  calls.append(1)
  if len(calls)==1: raise URLError('temporary DNS')
  return {'claims':[]}
 r=m.run(DOC,'k',fetcher=fetch,ai=flaky,sleeper=lambda _:None)
 d=r['diagnostics'][0]
 assert len(calls)==2 and r['apiCalls']==2 and d['aiRecoveredAfterRetry']==1
 assert d['retryKinds']=={'network_error':1}


def test_v502_http_status_classification_is_conservative(monkeypatch):
 def raise_429(*args,**kwargs): raise HTTPError('https://example.invalid',429,'rate',None,None)
 monkeypatch.setattr(m,'urlopen',raise_429)
 with pytest.raises(m.GeminiCallError) as e:
  m.live_gemini('k','model','prompt')
 assert e.value.kind=='rate_limited' and e.value.retryable is True
 def raise_401(*args,**kwargs): raise HTTPError('https://example.invalid',401,'auth',None,None)
 monkeypatch.setattr(m,'urlopen',raise_401)
 with pytest.raises(m.GeminiCallError) as e2:
  m.live_gemini('k','model','prompt')
 assert e2.value.kind=='auth_http' and e2.value.retryable is False


def test_v502_main_writes_failure_status_and_exits_nonzero_on_unrecovered_ai(monkeypatch,tmp_path):
 result={'phase':'PHASE4_GUIDE_CLAIMS_V50','generatedAt':'2026-09-01T00:00:00+00:00','publicationWrites':0,'apiCalls':2,'claims':[],
         'diagnostics':[{'game':'Game A','inputEvidence':1,'refetchedSources':1,'fetchErrors':0,'targetMissing':0,'aiCalls':1,'aiAttempts':2,'aiRetries':1,
                         'aiTransientFailures':1,'aiRecoveredAfterRetry':0,'proposed':0,'validated':0,'rejected':{},'malformedClaimsPayload':0,
                         'retryKinds':{'upstream_http':1},'aiError':'Gemini call failed','aiErrorKind':'upstream_http'}]}
 monkeypatch.setattr(m,'run',lambda:result)
 monkeypatch.setattr(m,'OUT',tmp_path/'claims.json')
 monkeypatch.setattr(m,'STATUS',tmp_path/'status.json')
 with pytest.raises(SystemExit) as ex: m.main()
 assert ex.value.code==2
 status=json.loads((tmp_path/'status.json').read_text())
 assert status['logicVersion']=='V50.2' and status['success'] is False
 assert status['diagnosticSummary']['zeroClaimReason']=='ai_error'
 assert (tmp_path/'claims.json').exists()


def test_v502_success_after_retry_keeps_workflow_status_successful(monkeypatch,tmp_path):
 result={'phase':'PHASE4_GUIDE_CLAIMS_V50','generatedAt':'2026-09-01T00:00:00+00:00','publicationWrites':0,'apiCalls':2,
         'claims':[{'game':'Game A'}],
         'diagnostics':[{'game':'Game A','inputEvidence':1,'refetchedSources':1,'fetchErrors':0,'targetMissing':0,'aiCalls':1,'aiAttempts':2,'aiRetries':1,
                         'aiTransientFailures':1,'aiRecoveredAfterRetry':1,'proposed':1,'validated':1,'rejected':{},'malformedClaimsPayload':0,
                         'retryKinds':{'network_error':1}}]}
 monkeypatch.setattr(m,'run',lambda:result)
 monkeypatch.setattr(m,'OUT',tmp_path/'claims.json')
 monkeypatch.setattr(m,'STATUS',tmp_path/'status.json')
 m.main()
 status=json.loads((tmp_path/'status.json').read_text())
 assert status['success'] is True and status['apiCalls']==2
 assert status['diagnosticSummary']['totals']['aiRecoveredAfterRetry']==1


def test_v502_workflow_uploads_quarantine_artifact_even_if_extraction_stops():
 workflow=(ROOT/'.github/workflows/collect-guide-evidence.yml').read_text()
 block=workflow.split('- name: Upload quarantined evidence artifact',1)[1].split('- name:',1)[0]
 assert 'if: always()' in block and 'actions/upload-artifact@v4' in block


def test_v502_raw_http_errors_are_classified_before_urlerror_fallback():
 e503=HTTPError('https://example.invalid',503,'upstream',None,None)
 e401=HTTPError('https://example.invalid',401,'auth',None,None)
 assert m.classify_ai_exception(e503)==('upstream_http',True)
 assert m.classify_ai_exception(e401)==('auth_http',False)


def test_v502_malformed_top_level_interaction_response_is_retryable(monkeypatch):
 class Resp:
  def __enter__(self): return self
  def __exit__(self,*args): return False
  def read(self): return b'[]'
 monkeypatch.setattr(m,'urlopen',lambda *a,**k:Resp())
 with pytest.raises(m.GeminiCallError) as ex:
  m.live_gemini('k','model','prompt')
 assert ex.value.kind=='response_format' and ex.value.retryable is True
