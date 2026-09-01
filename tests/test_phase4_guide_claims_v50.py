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
 assert status['logicVersion']=='V50.4' and status['success'] is False
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


def test_v503_prompt_requires_atomic_independently_corroboratable_claims():
 p=m.build_prompt('Game A',[{'sourceId':'s1','sourceType':'community_guide','text':'Game A','url':'x','game':'Game A'}])
 assert '1 claim = 1つ' in p
 assert '事実・仕様' in p and '助言' in p
 assert '無理に分割・一般化せず' in p


def test_v503_rejects_fact_plus_advice_compound_claim():
 text='Game A 市場ではランダムな商品をコインで買うことができ、材料不足の時に活用するのがおすすめです。'
 raw={'sourceId':'s1','category':'tip','claim':'市場では商品をコインで買うことができ材料不足の時に活用するのがおすすめ','evidenceQuote':'市場ではランダムな商品をコインで買うことができ、材料不足の時に活用するのがおすすめです。'}
 r=m.run(DOC,'k',fetcher=lambda u:(text,{'httpStatus':200}),ai=ai_with([raw]))
 assert r['claims']==[]
 assert r['diagnostics'][0]['rejected']['non_atomic_fact_plus_advice']==1


def test_v503_rejects_bundled_multi_action_advice():
 text='Game A ヘリコプター注文と列車を回すのが攻略の中心でした。'
 raw={'sourceId':'s1','category':'tip','claim':'ヘリコプター注文と列車を回すのが攻略の中心','evidenceQuote':'ヘリコプター注文と列車を回すのが攻略の中心でした。'}
 r=m.run(DOC,'k',fetcher=lambda u:(text,{'httpStatus':200}),ai=ai_with([raw]))
 assert r['claims']==[]
 assert r['diagnostics'][0]['rejected']['non_atomic_bundled_advice']==1


def test_v503_allows_atomic_fact_and_atomic_advice_separately_from_same_quote():
 text='Game A 市場では商品をコインで買えます。不足時は市場を活用するのがおすすめです。'
 rows=[
  {'sourceId':'s1','category':'mechanic','claim':'市場では商品をコインで買える','evidenceQuote':'市場では商品をコインで買えます。'},
  {'sourceId':'s1','category':'tip','claim':'不足時は市場を活用するのがおすすめ','evidenceQuote':'不足時は市場を活用するのがおすすめです。'},
 ]
 r=m.run(DOC,'k',fetcher=lambda u:(text,{'httpStatus':200}),ai=ai_with(rows))
 assert len(r['claims'])==2
 assert {x['category'] for x in r['claims']}=={'mechanic','tip'}


def test_v503_rejects_overlong_claim_as_non_atomic():
 long_claim='資源を温存する。'*40
 text='Game A '+long_claim
 raw={'sourceId':'s1','category':'tip','claim':long_claim,'evidenceQuote':long_claim}
 r=m.run(DOC,'k',fetcher=lambda u:(text,{'httpStatus':200}),ai=ai_with([raw]))
 assert r['claims']==[]
 assert r['diagnostics'][0]['rejected']['non_atomic_too_long']==1


def test_v503_rejects_bundled_negative_actions_as_one_tip():
 text='Game A 中盤まで工場は建てすぎず島も解放しない方が良い。'
 raw={'sourceId':'s1','category':'tip','claim':'中盤まで工場は建てすぎず島も解放しない方が良い','evidenceQuote':'中盤まで工場は建てすぎず島も解放しない方が良い。'}
 r=m.run(DOC,'k',fetcher=lambda u:(text,{'httpStatus':200}),ai=ai_with([raw]))
 assert r['claims']==[]
 assert r['diagnostics'][0]['rejected']['non_atomic_bundled_advice']==1



def _v504_row(claim, category, url='https://guide.example/a', source_type='community_guide'):
 return {'game':'Game A','category':category,'claim':claim,'evidenceQuote':claim,'sourceId':'s1','url':url,'sourceType':source_type,'status':'validated_quarantine'}


def test_v504_prompt_is_poikatsu_first_and_bounded_before_corroboration():
 p=m.build_prompt('Game A',[{'sourceId':'s1','sourceType':'community_guide','text':'Game A','url':'x','game':'Game A'}])
 assert 'ポイ活案件の条件達成' in p
 assert '一般的なゲーム紹介' in p
 assert '最大18件' in p and '最大12種類' in p


def test_v504_selection_caps_unique_groups_but_keeps_independent_evidence_rows():
 rows=[]
 # Same timeline proposition from two independent sites must survive together.
 rows.append(_v504_row('レベル20を10日で達成した','timeline','https://a.example/guide'))
 rows.append(_v504_row('レベル20を10日で達成した','timeline','https://b.example/guide'))
 for i in range(20):
  rows.append(_v504_row(f'通常プレイの小技{i}','mechanic',f'https://m{i}.example/guide'))
 selected,stats=m.select_poikatsu_claims(rows)
 groups={m.poi_claim_group_key(x) for x in selected}
 assert stats['selectedGroups']==m.MAX_POI_CLAIM_GROUPS_PER_GAME==12
 assert len(groups)==12 and stats['droppedGroups']==9
 same=[x for x in selected if x['claim']=='レベル20を10日で達成した']
 assert len(same)==2


def test_v504_selection_protects_rare_poikatsu_coverage_categories_from_many_mechanics():
 rows=[
  _v504_row('レベル30到達が案件条件','requirement'),
  _v504_row('15日目にレベル30へ到達した','timeline'),
  _v504_row('経験値が多い注文を優先する','priority'),
  _v504_row('コイン不足に注意する','warning'),
  _v504_row('キャッシュは時短用に温存する','resource'),
  _v504_row('ログイン時は注文を確認する','tip'),
 ]
 rows += [_v504_row(f'パズル盤面の通常仕様{i}','mechanic') for i in range(30)]
 selected,stats=m.select_poikatsu_claims(rows)
 cats={x['category'] for x in selected}
 assert {'requirement','timeline','priority','warning','resource','tip','mechanic'} <= cats
 assert stats['selectedGroups']==12


def test_v504_progress_mechanic_outranks_puzzle_only_mechanic():
 progress=_v504_row('注文達成で経験値を獲得できる','mechanic')
 puzzle=_v504_row('マッチ3でプロペラを作れる','mechanic')
 assert m.poi_relevance_score(progress) > m.poi_relevance_score(puzzle)


def test_v504_run_reports_preselection_and_dropped_group_counts():
 text='Game A ' + ' '.join([f'攻略情報{i}' for i in range(20)])
 proposed=[]
 for i in range(20):
  proposed.append({'sourceId':'s1','category':'tip','claim':f'攻略情報{i}','evidenceQuote':f'攻略情報{i}'})
 r=m.run(DOC,'k',fetcher=lambda u:(text,{'httpStatus':200}),ai=ai_with(proposed))
 d=r['diagnostics'][0]; s=m.summarize_result(r)
 assert d['validatedPreSelection']==20
 assert d['candidateClaimGroups']==20 and d['selectedClaimGroups']==12 and d['poiSelectionDroppedGroups']==8
 assert len(r['claims'])==12 and d['validated']==12
 assert s['totals']['validatedPreSelection']==20 and s['totals']['selectedClaimGroups']==12
