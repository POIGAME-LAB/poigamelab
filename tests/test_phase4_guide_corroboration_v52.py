import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cor',ROOT/'scripts'/'corroborate_guide_claims.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def claim(text='資源箱は温存する',url='https://a.example/post'):
 return {'game':'Game A','category':'tip','claim':text,'evidenceQuote':text,'sourceId':'s1','url':url,'sourceType':'community_guide','status':'validated_quarantine'}
def docs(text='資源箱は温存する'):
 c=claim(text); return {'claims':[c]},{'decisions':[{'game':'Game A','category':'tip','claim':text,'status':'held_single_source','independentSources':['a.example']}]}
def cfg(): return {'blockedDomains':['moppy.jp'],'officialDomainsByGame':{},'maxCorroborationClaimsPerRun':4,'maxCorroborationResultsPerClaim':4,'maxCorroborationFetchesPerRun':12}
def search(url='https://b.example/guide'):
 return lambda q,k,n:{'results':[{'url':url,'title':'ignored','content':'ignored snippet'}]}
def fetch(text='Game A 攻略では資源箱は温存するのがおすすめです'):
 return lambda u:(f'<html><body>{text}</body></html>',{'httpStatus':200})
def ai_support(key,model,prompt): return {'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'}]}

def test_independent_direct_quote_adds_corroboration():
 c,d=docs(); merged,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=ai_support)
 assert r['supportingClaimsAdded']==1 and len(merged['claims'])==2 and r['publicationWrites']==0

def test_same_site_is_not_fetched_or_counted():
 c,d=docs(); merged,r=m.run(c,d,cfg(),'t','g',searcher=search('https://blog.a.example/other'),fetcher=lambda u:(_ for _ in ()).throw(AssertionError()),ai=ai_support)
 assert r['directFetches']==0 and r['apiCalls']==0 and len(merged['claims'])==1

def test_search_snippet_never_becomes_evidence():
 c,d=docs(); merged,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A unrelated page'),ai=ai_support)
 assert r['candidatePages']==1 and r['supportingClaimsAdded']==0

def test_target_missing_skips_ai():
 c,d=docs(); merged,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('資源箱は温存する'),ai=lambda *a:(_ for _ in ()).throw(AssertionError()))
 assert r['apiCalls']==0 and r['supportingClaimsAdded']==0

def test_quote_must_exist_in_direct_page():
 c,d=docs(); bad=lambda *a:{'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:invented','relation':'support'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=bad)
 assert r['supportingClaimsAdded']==0 and r['rejected']['unknown_span']==1

def test_numeric_claim_requires_same_number_in_quote():
 c,d=docs('城レベル20を目指す'); bad=lambda *a:{'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 城レベル10を目指す'),ai=bad)
 assert r['supportingClaimsAdded']==0 and r['rejected']['numeric_not_grounded']==1

def test_numeric_grounding_uses_exact_tokens_not_substrings():
 c,d=docs('城レベル20を目指す'); bad=lambda *a:{'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 城レベル120を目指す'),ai=bad)
 assert r['supportingClaimsAdded']==0 and r['rejected']['numeric_not_grounded']==1

def test_semantically_unrelated_quote_rejected_by_overlap_guard():
 c,d=docs(); bad=lambda *a:{'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 毎日ログインすると報酬がもらえる'),ai=bad)
 assert r['supportingClaimsAdded']==0 and r['apiCalls']==0
 assert r['diagnosticCounts']['sourceClaimPairsNoLexicalSpan']==1

def test_contradiction_is_quarantined_not_appended():
 c,d=docs('城レベル20を目指す'); a=lambda *x:{'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'contradict'}]}
 merged,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 城レベル10を目指す'),ai=a)
 assert r['contradictionsFound']==1 and len(merged['claims'])==1

def test_search_failure_fails_closed_for_claim():
 c,d=docs(); _,r=m.run(c,d,cfg(),'t','g',searcher=lambda *a:(_ for _ in ()).throw(RuntimeError('x')),fetcher=fetch(),ai=ai_support)
 assert r['supportingClaimsAdded']==0 and r['apiCalls']==0

def test_ai_failure_fails_closed():
 c,d=docs(); _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=lambda *a:(_ for _ in ()).throw(RuntimeError('x')))
 assert r['supportingClaimsAdded']==0 and r['apiCalls']==1

def test_bounds_claim_searches_and_direct_fetches():
 cs=[]; ds=[]
 for i in range(10):
  x=claim(f'攻略項目{i}を優先する',f'https://old{i}.example/a'); cs.append(x); ds.append({'game':'Game A','category':'tip','claim':x['claim'],'status':'held_single_source','independentSources':[f'old{i}.example']})
 calls={'s':0,'f':0}
 def se(q,k,n): calls['s']+=1; return {'results':[{'url':f'https://new{calls["s"]}-{j}.example/a'} for j in range(6)]}
 def fe(u): calls['f']+=1; return ('<body>Game A 攻略情報です</body>',{})
 _,r=m.run({'claims':cs},{'decisions':ds},cfg(),'t','g',searcher=se,fetcher=fe,ai=lambda *a:{'matches':[]})
 assert r['searchCalls']==4 and r['directFetches']<=12 and calls['f']<=12

def test_backend_cannot_exceed_per_claim_result_bound():
 c,d=docs(); seen={'f':0}
 def se(q,k,n): return {'results':[{'url':f'https://extra{i}.example/a'} for i in range(50)]}
 def fe(u): seen['f']+=1; return ('<body>Game A unrelated</body>',{})
 _,r=m.run(c,d,cfg(),'t','g',searcher=se,fetcher=fe,ai=lambda *a:{'matches':[]})
 assert seen['f']<=4 and r['directFetches']<=4

def test_only_held_single_source_is_researched():
 c,d=docs(); d['decisions'][0]['status']='supported_quarantine'
 _,r=m.run(c,d,cfg(),'t','g',searcher=lambda *a:(_ for _ in ()).throw(AssertionError()),fetcher=fetch(),ai=ai_support)
 assert r['inputHeldClaims']==0 and r['searchCalls']==0 and r['apiCalls']==0

def test_blocked_point_site_never_fetched():
 c,d=docs(); _,r=m.run(c,d,cfg(),'t','g',searcher=search('https://moppy.jp/x'),fetcher=lambda u:(_ for _ in ()).throw(AssertionError()),ai=ai_support)
 assert r['directFetches']==0

def test_localhost_never_fetched():
 c,d=docs(); _,r=m.run(c,d,cfg(),'t','g',searcher=search('http://127.0.0.1/x'),fetcher=lambda u:(_ for _ in ()).throw(AssertionError()),ai=ai_support)
 assert r['directFetches']==0

def test_missing_keys_fail_closed():
 c,d=docs()
 try: m.run(c,d,cfg(),'','g',searcher=search(),fetcher=fetch(),ai=ai_support); assert False
 except RuntimeError as e: assert 'TAVILY' in str(e)
 try: m.run(c,d,cfg(),'t','',searcher=search(),fetcher=fetch(),ai=ai_support); assert False
 except RuntimeError as e: assert 'GEMINI' in str(e)

def test_corroborated_output_can_upgrade_v51_without_publication():
 c,d=docs(); merged,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=ai_support)
 gated=m.gate.evaluate(merged); decision=gated['decisions'][0]
 assert decision['status']=='supported_quarantine' and decision['independentSourceCount']==2
 assert gated['publicationWrites']==0 and gated['publicationEligibleClaims']==0

def test_live_shape_seven_base_claims_three_supports_upgrade_three_groups():
 labels=['甲','乙','丙','丁','戊','己','庚']; cs=[]; ds=[]
 for i,label in enumerate(labels):
  text=f'攻略項目{label}を優先する'
  row=claim(text,f'https://old{i}.example/a'); cs.append(row)
  ds.append({'game':'Game A','category':'tip','claim':text,'status':'held_single_source','independentSources':[f'old{i}.example']})
 state={'search':0}
 def se(q,k,n):
  i=state['search']; state['search']+=1
  return {'results':[{'url':f'https://new{i}.example/guide'}]}
 def fe(url):
  i=int(url.split('new',1)[1].split('.',1)[0])
  return (f'<body>Game A 攻略項目{labels[i]}を優先する</body>',{})
 def ai(key,model,prompt):
  return {'matches':[
   {'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'},
   {'claimId':'c2','sourceId':'u2','spanId':'u2:c2:s1','relation':'support'},
   {'claimId':'c3','sourceId':'u3','spanId':'u3:c3:s1','relation':'support'},
  ]}
 merged,r=m.run({'claims':cs},{'decisions':ds},cfg(),'t','g',searcher=se,fetcher=fe,ai=ai)
 assert r['inputClaims']==7 and r['supportingClaimsAdded']==3 and r['outputClaims']==10
 gated=m.gate.evaluate(merged)
 assert gated['counts']['decisionGroups']==7
 assert gated['counts']['supportedQuarantine']==3
 assert gated['counts']['heldSingleSource']==4

def test_workflow_re_evaluation_uses_explicit_corroborated_input_and_phase_guard():
 text=(ROOT/'.github'/'workflows'/'collect-guide-evidence.yml').read_text(encoding='utf-8')
 line='python scripts/evaluate_guide_claims.py --input data/guide_claims_corroborated.json --expect-phase PHASE4_GUIDE_CLAIMS_CORROBORATED_V52'
 assert line in text

def test_diagnostic_funnel_explains_pre_ai_candidate_losses():
 c,d=docs()
 custom=cfg(); custom['maxCorroborationResultsPerClaim']=6
 urls=[
  'https://a.example/same-source',
  'https://moppy.jp/blocked',
  'http://127.0.0.1/private',
  'https://b.example/fetch-fails',
  'https://c.example/target-missing',
  'https://d.example/good',
 ]
 def se(q,k,n): return {'results':[{'url':u} for u in urls]}
 def fe(url):
  if 'fetch-fails' in url: raise RuntimeError('network down')
  if 'target-missing' in url: return ('<body>資源箱は温存する</body>',{})
  return ('<body>Game A 資源箱は温存する</body>',{})
 _,r=m.run(c,d,custom,'t','g',searcher=se,fetcher=fe,ai=lambda *a:{'matches':[]})
 f=r['diagnosticCounts']
 assert f['searchResults']==6
 assert f['sameSourceSiteUrls']==1
 assert f['blockedOrUnsafeUrls']==1
 assert f['invalidOrUnsupportedUrls']==1
 assert f['fetchErrors']==1
 assert f['targetMissing']==1
 assert f['candidatePages']==1
 assert r['candidatePages']==1


def test_diagnostics_show_when_ai_returns_no_proposals_for_candidate_pages():
 c,d=docs(); custom=cfg(); custom['maxCorroborationResultsPerClaim']=2
 def se(q,k,n): return {'results':[{'url':'https://b.example/one'},{'url':'https://c.example/two'}]}
 _,r=m.run(c,d,custom,'t','g',searcher=se,fetcher=fetch(),ai=lambda *a:{'matches':[]})
 f=r['diagnosticCounts']
 assert r['candidatePages']==2
 assert f['aiProposedMatches']==0
 assert f['candidatePagesUnreferencedByAI']==2
 assert f['aiValidatedSupport']==0


def test_diagnostics_surface_ai_validation_rejection_reason():
 c,d=docs()
 bad=lambda *a:{'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:invented','relation':'support'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=bad)
 assert r['diagnosticCounts']['aiProposedMatches']==1
 assert r['diagnosticCounts']['aiRejectedMatches']==1
 assert r['rejected']['unknown_span']==1


def test_cross_claim_mapping_cannot_bypass_independent_source_guard():
 c1=claim('資源箱は温存する','https://a.example/original')
 c2=claim('建設枠を優先する','https://b.example/original')
 claims={'claims':[c1,c2]}
 decisions={'decisions':[
  {'game':'Game A','category':'tip','claim':c1['claim'],'status':'held_single_source','independentSources':['a.example']},
  {'game':'Game A','category':'tip','claim':c2['claim'],'status':'held_single_source','independentSources':['b.example']},
 ]}
 state={'n':0}
 def se(q,k,n):
  state['n']+=1
  if state['n']==1: return {'results':[{'url':'https://c.example/own-candidate'}]}
  return {'results':[{'url':'https://a.example/from-other-claim'}]}
 def fe(url): return ('<body>Game A 資源箱は温存する 建設枠を優先する</body>',{})
 def ai(*a): return {'matches':[{'claimId':'c1','sourceId':'u2','spanId':'u2:c1:s1','relation':'support'}]}
 merged,r=m.run(claims,decisions,cfg(),'t','g',searcher=se,fetcher=fe,ai=ai)
 assert len(merged['claims'])==2
 assert r['supportingClaimsAdded']==0
 assert r['rejected']['classification_pair_not_requested']==2
 assert r['diagnosticCounts']['pairTasksMissing']==3


def test_contradiction_requires_same_claim_context():
 c,d=docs('資源箱は温存する')
 unrelated=lambda *a:{'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'contradict'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 毎日ログインすると報酬がもらえる'),ai=unrelated)
 assert r['contradictionsFound']==0 and r['apiCalls']==0
 assert r['diagnosticCounts']['sourceClaimPairsNoLexicalSpan']==1


def test_report_always_exposes_diagnostic_counts_without_publication():
 c,d=docs(); _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=ai_support)
 assert isinstance(r['diagnosticCounts'],dict)
 assert r['diagnosticCounts']['aiValidatedSupport']==1
 assert r['publicationWrites']==0


def test_v528_logic_version_is_reported_for_live_audit():
 c,d=docs(); _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=ai_support)
 assert r['logicVersion']=='V52.8'


def test_orphan_held_decision_is_not_researched_or_resurrected():
 c,_=docs()
 stale={'decisions':[{'game':'Game A','category':'tip','claim':'現在のclaimsに存在しない攻略','status':'held_single_source','independentSources':['old.example']}]}
 merged,r=m.run(c,stale,cfg(),'t','g',searcher=lambda *a:(_ for _ in ()).throw(AssertionError()),fetcher=fetch(),ai=ai_support)
 assert len(merged['claims'])==1
 assert r['totalHeldClaims']==1 and r['eligibleHeldClaims']==0 and r['inputHeldClaims']==0
 assert r['diagnosticCounts']['orphanHeldDecisions']==1


def test_malformed_search_response_fails_closed_with_diagnostic():
 c,d=docs(); _,r=m.run(c,d,cfg(),'t','g',searcher=lambda *a:{'results':'not-a-list'},fetcher=lambda *a:(_ for _ in ()).throw(AssertionError()),ai=ai_support)
 assert r['supportingClaimsAdded']==0 and r['directFetches']==0 and r['apiCalls']==0
 assert r['diagnosticCounts']['malformedSearchResponses']==1


def test_malformed_search_item_fails_closed_without_crash():
 c,d=docs(); _,r=m.run(c,d,cfg(),'t','g',searcher=lambda *a:{'results':['not-an-object']},fetcher=lambda *a:(_ for _ in ()).throw(AssertionError()),ai=ai_support)
 assert r['supportingClaimsAdded']==0 and r['directFetches']==0
 assert r['diagnosticCounts']['malformedSearchItems']==1


def test_malformed_ai_response_is_diagnostic_not_support():
 c,d=docs(); _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=lambda *a:{'matches':'not-a-list'})
 assert r['supportingClaimsAdded']==0 and r['apiCalls']==1
 assert r['diagnosticCounts']['aiMalformedResponses']==1
 assert r['diagnosticCounts']['candidatePagesUnreferencedByAI']==1


def test_v524_prompt_uses_python_span_ids_not_ai_written_quotes():
 held=[{'claimId':'c1','category':'tip','claim':'資源箱は温存する','existingSites':['a.example']}]
 spans=[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','text':'Game A 攻略では資源箱は温存する'}]
 p=m.build_prompt('Game A',held,spans)
 assert 'spanId' in p and 'evidenceSpans' in p
 assert 'evidenceQuote' not in p


def test_claim_windows_are_exact_bounded_source_substrings():
 text='Game A '+('前置きです。'*80)+'攻略では資源箱は温存する。'+('後半です。'*80)
 spans=m.claim_windows('c1','u1','資源箱は温存する',text)
 assert spans and len(spans)<=4
 assert all(x['text'] in m.norm(text) for x in spans)
 assert all(len(x['text'])<=240 for x in spans)
 assert any('資源箱は温存する' in x['text'] for x in spans)


def test_ai_cannot_invent_evidence_text_when_selecting_valid_span():
 c,d=docs()
 def ai(*a):
  return {'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support','evidenceQuote':'AIが勝手に作った文章'}]}
 merged,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=ai)
 assert r['supportingClaimsAdded']==1
 added=[x for x in merged['claims'] if x['url']=='https://b.example/guide'][0]
 assert 'AIが勝手に作った文章' not in added['evidenceQuote']
 assert added['evidenceQuote'] in m.norm('Game A 攻略では資源箱は温存するのがおすすめです')


def test_unknown_span_id_fails_closed_without_quote_fallback():
 c,d=docs()
 def ai(*a): return {'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:not-real','relation':'support','evidenceQuote':'資源箱は温存する'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=ai)
 assert r['supportingClaimsAdded']==0
 assert r['rejected']['unknown_span']==1


def test_span_pair_mismatch_is_rejected_even_when_ids_exist():
 claims={'c1':{'claimId':'c1','claim':'資源箱は温存する','category':'tip','existingSites':[]},'c2':{'claimId':'c2','claim':'建設枠を優先する','category':'tip','existingSites':[]}}
 sources={'u1':{'sourceId':'u1','site':'b.example','text':'Game A 資源箱は温存する 建設枠を優先する'}}
 spans={
  'u1:c1:s1':{'spanId':'u1:c1:s1','claimId':'c1','sourceId':'u1','text':'資源箱は温存する'},
  'u1:c2:s1':{'spanId':'u1:c2:s1','claimId':'c2','sourceId':'u1','text':'建設枠を優先する'},
 }
 raw={'claimId':'c1','sourceId':'u1','spanId':'u1:c2:s1','relation':'support'}
 match,reason=m.validate_match(raw,claims,sources,spans)
 assert match is None and reason=='span_pair_mismatch'


def test_independence_is_applied_before_spans_are_exposed_to_ai():
 held={
  'c1':{'claimId':'c1','claim':'資源箱は温存する','category':'tip','existingSites':['a.example']},
  'c2':{'claimId':'c2','claim':'建設枠を優先する','category':'tip','existingSites':['b.example']},
 }
 sources=[
  {'sourceId':'u1','site':'a.example','text':'Game A 資源箱は温存する 建設枠を優先する'},
  {'sourceId':'u2','site':'c.example','text':'Game A 資源箱は温存する 建設枠を優先する'},
 ]
 spans,considered,with_spans,no_lexical,strict_pairs,anchor_only_pairs=m.build_evidence_spans(held,sources)
 ids={x['spanId'] for x in spans}
 assert not any(x.startswith('u1:c1:') for x in ids)
 assert any(x.startswith('u1:c2:') for x in ids)
 assert any(x.startswith('u2:c1:') for x in ids)
 assert any(x.startswith('u2:c2:') for x in ids)
 assert considered==3 and with_spans==3 and no_lexical==0


def test_source_found_for_one_claim_can_corroborate_another_independent_held_claim():
 c1=claim('資源箱は温存する','https://a.example/original')
 c2=claim('建設枠を優先する','https://b.example/original')
 claims={'claims':[c1,c2]}
 decisions={'decisions':[
  {'game':'Game A','category':'tip','claim':c1['claim'],'status':'held_single_source','independentSources':['a.example']},
  {'game':'Game A','category':'tip','claim':c2['claim'],'status':'held_single_source','independentSources':['b.example']},
 ]}
 state={'n':0}
 def se(q,k,n):
  state['n']+=1
  if state['n']==1: return {'results':[{'url':'https://c.example/shared-guide'}]}
  return {'results':[]}
 def fe(url): return ('<body>Game A 建設枠を優先する</body>',{})
 def ai(*a): return {'matches':[{'claimId':'c2','sourceId':'u1','spanId':'u1:c2:s1','relation':'support'}]}
 merged,r=m.run(claims,decisions,cfg(),'t','g',searcher=se,fetcher=fe,ai=ai)
 assert r['supportingClaimsAdded']==1
 gated=m.gate.evaluate(merged)
 statuses={d['claim']:d['status'] for d in gated['decisions']}
 assert statuses['建設枠を優先する']=='supported_quarantine'
 assert statuses['資源箱は温存する']=='held_single_source'


def test_no_lexical_span_skips_ai_instead_of_sending_unusable_evidence():
 c,d=docs('資源箱は温存する')
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 毎日ログインすると報酬がもらえる'),ai=lambda *a:(_ for _ in ()).throw(AssertionError()))
 f=r['diagnosticCounts']
 assert r['apiCalls']==0 and r['supportingClaimsAdded']==0
 assert f['sourceClaimPairsConsidered']==1
 assert f['sourceClaimPairs']==0
 assert f['sourceClaimPairsNoLexicalSpan']==1
 assert f['evidenceSpans']==0


def test_duplicate_ai_matches_from_same_claim_source_count_once():
 c,d=docs()
 def ai(*a):
  return {'matches':[
   {'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'},
   {'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'},
  ]}
 merged,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=ai)
 assert r['supportingClaimsAdded']==1
 assert r['validatedMatches']==1
 assert r['rejected']['duplicate_ai_match']==1
 assert len(merged['claims'])==2


def test_conflicting_ai_relations_for_same_claim_source_fail_closed():
 c,d=docs('城レベル20を目指す')
 def ai(*a):
  return {'matches':[
   {'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'},
   {'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'contradict'},
  ]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 城レベル20を目指す'),ai=ai)
 assert r['supportingClaimsAdded']==0 and r['contradictionsFound']==0
 assert r['validatedMatches']==0
 assert r['rejected']['ambiguous_pair_relations']==2


def test_ai_proposal_count_is_bounded_and_overflow_diagnosed():
 c,d=docs()
 def ai(*a):
  one={'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'}
  return {'matches':[dict(one) for _ in range(100)]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=ai)
 f=r['diagnosticCounts']
 assert f['aiProposedMatches']==80
 assert f['aiProposalsDropped']==20
 assert r['supportingClaimsAdded']==1
 assert r['rejected']['duplicate_ai_match']==79


def test_unreferenced_candidate_count_excludes_sources_never_exposed_as_spans():
 c,d=docs()
 custom=cfg(); custom['maxCorroborationResultsPerClaim']=2
 def se(q,k,n): return {'results':[{'url':'https://b.example/related'},{'url':'https://c.example/other'}]}
 def fe(url):
  if 'related' in url: return ('<body>Game A 資源箱は温存する</body>',{})
  return ('<body>Game A 毎日ログインすると報酬がもらえる</body>',{})
 _,r=m.run(c,d,custom,'t','g',searcher=se,fetcher=fe,ai=lambda *a:{'matches':[]})
 f=r['diagnosticCounts']
 assert r['candidatePages']==2
 assert f['sourcesWithoutEligibleSpans']==1
 assert f['candidatePagesUnreferencedByAI']==1


def test_span_scanning_keeps_previous_18000_character_page_bound():
 text='Game A '+('あ'*17990)+' 資源箱は温存する'
 spans=m.claim_windows('c1','u1','資源箱は温存する',text)
 assert not any('資源箱は温存する' in x['text'] for x in spans)


def test_max_live_shape_span_payload_is_bounded():
 held={f'c{i}':{'claimId':f'c{i}','claim':f'攻略項目{i}を優先する','category':'tip','existingSites':[]} for i in range(1,5)}
 sources=[{'sourceId':f'u{j}','site':f's{j}.example','text':'Game A '+' '.join(f'攻略項目{i}を優先する' for i in range(1,5))} for j in range(1,13)]
 spans,considered,with_spans,no_lexical,strict_pairs,anchor_only_pairs=m.build_evidence_spans(held,sources)
 assert considered==48 and with_spans==48 and no_lexical==0
 assert len(spans)<=48*4
 assert sum(len(x['text']) for x in spans)<=48*4*240


def test_v525_anchor_only_paraphrase_requires_second_review_and_can_support():
 c,d=docs('資源箱は温存する')
 calls=[]
 def ai(key,model,prompt):
  calls.append(prompt)
  if '独立再確認' in prompt:
   return {'reviews':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support','verdict':'confirm'}]}
  return {'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'}]}
 merged,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 資源箱を残しておくと後半で使いやすい'),ai=ai)
 f=r['diagnosticCounts']
 assert r['supportingClaimsAdded']==1 and len(merged['claims'])==2
 assert r['apiCalls']==2 and f['semanticReviewCalls']==1 and f['semanticReviewConfirmed']==1
 assert f['sourceClaimPairsAnchorOnly']==1 and f['sourceClaimPairsStrictLexical']==0


def test_v525_anchor_only_support_fails_closed_when_second_review_rejects():
 c,d=docs('資源箱は温存する')
 def ai(key,model,prompt):
  if '独立再確認' in prompt:
   return {'reviews':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support','verdict':'reject'}]}
  return {'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'}]}
 merged,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 資源箱を残しておくと後半で使いやすい'),ai=ai)
 assert r['supportingClaimsAdded']==0 and len(merged['claims'])==1
 assert r['rejected']['semantic_review_rejected_or_missing']==1
 assert r['diagnosticCounts']['semanticReviewRejected']==1


def test_v525_anchor_only_support_fails_closed_when_review_is_malformed():
 c,d=docs('資源箱は温存する')
 def ai(key,model,prompt):
  if '独立再確認' in prompt: return {'reviews':'bad'}
  return {'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 資源箱を残しておくと後半で使いやすい'),ai=ai)
 assert r['supportingClaimsAdded']==0
 assert r['diagnosticCounts']['semanticReviewMalformedResponses']==1
 assert r['rejected']['semantic_review_malformed']==1


def test_v525_anchor_only_support_fails_closed_when_review_call_errors():
 c,d=docs('資源箱は温存する')
 def ai(key,model,prompt):
  if '独立再確認' in prompt: raise RuntimeError('review down')
  return {'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 資源箱を残しておくと後半で使いやすい'),ai=ai)
 assert r['supportingClaimsAdded']==0
 assert r['diagnosticCounts']['semanticReviewErrors']==1
 assert r['rejected']['semantic_review_error']==1


def test_v525_generic_words_alone_do_not_create_evidence_span_or_ai_call():
 c,d=docs('達成条件を優先する')
 text='Game A 攻略の達成条件と報酬について説明します'
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(text),ai=lambda *a:(_ for _ in ()).throw(AssertionError()))
 f=r['diagnosticCounts']
 assert r['apiCalls']==0 and r['supportingClaimsAdded']==0
 assert f['sourceClaimPairsNoLexicalSpan']==1 and f['evidenceSpans']==0


def test_v525_numeric_anchor_only_support_still_requires_exact_number_before_review():
 c,d=docs('城レベル20を目指す')
 calls={'n':0}
 def ai(key,model,prompt):
  calls['n']+=1
  return {'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 城レベル120まで上げると次に進める'),ai=ai)
 assert r['supportingClaimsAdded']==0
 assert r['rejected']['numeric_not_grounded']==1
 assert r['diagnosticCounts']['semanticReviewCalls']==0
 assert calls['n']==1


def test_v525_review_cannot_confirm_unknown_or_changed_tuple():
 c,d=docs('資源箱は温存する')
 def ai(key,model,prompt):
  if '独立再確認' in prompt:
   return {'reviews':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:fake','relation':'support','verdict':'confirm'}]}
  return {'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 資源箱を残しておくと後半で使いやすい'),ai=ai)
 assert r['supportingClaimsAdded']==0
 assert r['rejected']['semantic_review_unknown_reference']==1
 assert r['rejected']['semantic_review_rejected_or_missing']==1


def test_v525_strict_lexical_match_does_not_add_review_api_cost():
 c,d=docs('資源箱は温存する')
 merged,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 資源箱は温存する'),ai=ai_support)
 assert r['supportingClaimsAdded']==1 and len(merged['claims'])==2
 assert r['apiCalls']==1 and r['diagnosticCounts']['semanticReviewCalls']==0
 assert r['diagnosticCounts']['sourceClaimPairsStrictLexical']==1


def test_v525_duplicate_semantic_review_for_same_tuple_fails_closed():
 c,d=docs('資源箱は温存する')
 def ai(key,model,prompt):
  if '独立再確認' in prompt:
   row={'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'}
   return {'reviews':[{**row,'verdict':'confirm'},{**row,'verdict':'reject'}]}
  return {'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 資源箱を残しておくと後半で使いやすい'),ai=ai)
 assert r['supportingClaimsAdded']==0
 assert r['rejected']['semantic_review_duplicate']==1
 assert r['rejected']['semantic_review_rejected_or_missing']==1


def test_v525_semantic_review_is_batched_to_one_extra_call_per_game():
 claims=[]; decisions=[]
 for i,text in enumerate(['資源箱は温存する','建設枠を優先する','兵士枠は温存する','研究枠を優先する'],1):
  row=claim(text,f'https://old{i}.example/original'); claims.append(row)
  decisions.append({'game':'Game A','category':'tip','claim':text,'status':'held_single_source','independentSources':[f'old{i}.example']})
 state={'s':0,'ai':0}
 pages=['資源箱を残しておく','建設枠を先に使う','兵士枠を残しておく','研究枠を先に使う']
 def se(q,k,n):
  i=state['s']; state['s']+=1
  return {'results':[{'url':f'https://new{i}.example/guide'}]}
 def fe(url):
  i=int(url.split('new',1)[1].split('.',1)[0])
  return (f'<body>Game A {pages[i]}</body>',{})
 def ai(key,model,prompt):
  state['ai']+=1
  if '独立再確認' in prompt:
   return {'reviews':[
    {'claimId':f'c{i}','sourceId':f'u{i}','spanId':f'u{i}:c{i}:s1','relation':'support','verdict':'confirm'} for i in range(1,5)
   ]}
  return {'matches':[
   {'claimId':f'c{i}','sourceId':f'u{i}','spanId':f'u{i}:c{i}:s1','relation':'support'} for i in range(1,5)
  ]}
 _,r=m.run({'claims':claims},{'decisions':decisions},cfg(),'t','g',searcher=se,fetcher=fe,ai=ai)
 assert r['supportingClaimsAdded']==4
 assert r['apiCalls']==5 and state['ai']==5
 assert r['diagnosticCounts']['classificationCalls']==4
 assert r['diagnosticCounts']['semanticReviewCalls']==1



def test_v526_prompt_requires_one_decision_per_source_claim_pair():
 held=[{'claimId':'c1','category':'tip','claim':'資源箱は温存する','existingSites':['a.example']}]
 spans=[
  {'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','text':'Game A 資源箱は温存する'},
  {'claimId':'c1','sourceId':'u2','spanId':'u2:c1:s1','text':'Game A 資源箱は温存する'},
 ]
 p=m.build_prompt('Game A',held,spans)
 assert 'pairTasks' in p and '必ず1行ずつ判定を返す' in p
 assert '"sourceId": "u1"' in p and '"sourceId": "u2"' in p


def test_v526_classifies_each_claim_in_its_own_bounded_call():
 c1=claim('資源箱は温存する','https://a.example/original')
 c2=claim('建設枠を優先する','https://b.example/original')
 claims={'claims':[c1,c2]}
 decisions={'decisions':[
  {'game':'Game A','category':'tip','claim':c1['claim'],'status':'held_single_source','independentSources':['a.example']},
  {'game':'Game A','category':'tip','claim':c2['claim'],'status':'held_single_source','independentSources':['b.example']},
 ]}
 state={'s':0,'prompts':[]}
 def se(q,k,n):
  state['s']+=1
  return {'results':[{'url':f'https://new{state["s"]}.example/guide'}]}
 def fe(url): return ('<body>Game A 資源箱は温存する 建設枠を優先する</body>',{})
 def ai(key,model,prompt):
  state['prompts'].append(prompt)
  if '"claimId": "c1"' in prompt and '"claimId": "c2"' not in prompt:
   return {'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'support'},{'claimId':'c1','sourceId':'u2','spanId':'u2:c1:s1','relation':'support'}]}
  if '"claimId": "c2"' in prompt and '"claimId": "c1"' not in prompt:
   return {'matches':[{'claimId':'c2','sourceId':'u1','spanId':'u1:c2:s1','relation':'support'},{'claimId':'c2','sourceId':'u2','spanId':'u2:c2:s1','relation':'support'}]}
  raise AssertionError('claims were mixed in one classification prompt')
 merged,r=m.run(claims,decisions,cfg(),'t','g',searcher=se,fetcher=fe,ai=ai)
 f=r['diagnosticCounts']
 assert f['classificationCalls']==2 and f['classificationClaims']==2
 assert f['pairTasksExpected']==4 and f['pairTasksReturned']==4 and f['pairTasksMissing']==0
 assert r['supportingClaimsAdded']==4
 assert len(state['prompts'])==2


def test_v526_missing_pair_rows_fail_closed_and_are_diagnosed():
 c,d=docs(); custom=cfg(); custom['maxCorroborationResultsPerClaim']=2
 def se(q,k,n): return {'results':[{'url':'https://b.example/one'},{'url':'https://c.example/two'}]}
 def ai(key,model,prompt):
  return {'matches':[{'claimId':'c1','sourceId':'u1','spanId':'u1:c1:s1','relation':'unclear'}]}
 _,r=m.run(c,d,custom,'t','g',searcher=se,fetcher=fetch(),ai=ai)
 f=r['diagnosticCounts']
 assert f['pairTasksExpected']==2 and f['pairTasksReturned']==1 and f['pairTasksMissing']==1
 assert r['supportingClaimsAdded']==0


def test_v526_unrequested_cross_claim_tuple_is_rejected_before_span_validation():
 c1=claim('資源箱は温存する','https://a.example/original')
 c2=claim('建設枠を優先する','https://b.example/original')
 claims={'claims':[c1,c2]}
 decisions={'decisions':[
  {'game':'Game A','category':'tip','claim':c1['claim'],'status':'held_single_source','independentSources':['a.example']},
  {'game':'Game A','category':'tip','claim':c2['claim'],'status':'held_single_source','independentSources':['b.example']},
 ]}
 state={'s':0}
 def se(q,k,n):
  state['s']+=1
  return {'results':[{'url':f'https://new{state["s"]}.example/guide'}]}
 def fe(url): return ('<body>Game A 資源箱は温存する 建設枠を優先する</body>',{})
 def ai(key,model,prompt):
  if '"claimId": "c1"' in prompt and '"claimId": "c2"' not in prompt:
   return {'matches':[{'claimId':'c2','sourceId':'u1','spanId':'u1:c2:s1','relation':'support'}]}
  return {'matches':[]}
 _,r=m.run(claims,decisions,cfg(),'t','g',searcher=se,fetcher=fe,ai=ai)
 assert r['supportingClaimsAdded']==0
 assert r['rejected']['classification_pair_not_requested']==1


def test_v526_ai_call_budget_is_hard_bounded_and_exhaustion_fails_closed():
 claims=[]; decisions=[]
 for i,text in enumerate(['資源箱は温存する','建設枠を優先する','兵士枠は温存する','研究枠を優先する'],1):
  row=claim(text,f'https://old{i}.example/original'); claims.append(row)
  decisions.append({'game':'Game A','category':'tip','claim':text,'status':'held_single_source','independentSources':[f'old{i}.example']})
 custom=cfg(); custom['maxCorroborationAiCallsPerRun']=2
 state={'s':0,'ai':0}
 def se(q,k,n):
  state['s']+=1
  return {'results':[{'url':f'https://new{state["s"]}.example/guide'}]}
 def fe(url): return ('<body>Game A 資源箱は温存する 建設枠を優先する 兵士枠は温存する 研究枠を優先する</body>',{})
 def ai(key,model,prompt): state['ai']+=1; return {'matches':[]}
 _,r=m.run({'claims':claims},{'decisions':decisions},custom,'t','g',searcher=se,fetcher=fe,ai=ai)
 f=r['diagnosticCounts']
 assert r['apiCalls']==2 and state['ai']==2
 assert f['aiCallBudget']==2 and f['classificationCalls']==2
 assert f['aiBudgetExhaustedPairs']>0 and f['pairTasksMissing']>=f['aiBudgetExhaustedPairs']
 assert r['supportingClaimsAdded']==0


def test_v526_live_shape_pair_coverage_replaces_sparse_four_of_twenty_six_behavior():
 labels=['甲','乙','丙','丁']; claims=[]; decisions=[]
 for i,label in enumerate(labels,1):
  text=f'攻略項目{label}を優先する'
  row=claim(text,f'https://old{i}.example/original'); claims.append(row)
  decisions.append({'game':'Game A','category':'tip','claim':text,'status':'held_single_source','independentSources':[f'old{i}.example']})
 state={'s':0}
 def se(q,k,n):
  i=state['s']; state['s']+=1
  # 7 unique candidate pages over four searches, close to the observed live run.
  counts=[2,2,2,1]
  return {'results':[{'url':f'https://new{i}-{j}.example/guide'} for j in range(counts[i])]}
 def fe(url):
  return ('<body>Game A '+ ' '.join(f'攻略項目{x}を優先する' for x in labels) +'</body>',{})
 def ai(key,model,prompt):
  # V52.6 receives only one claim per classification prompt and returns every pair.
  cid=next(x for x in ('c1','c2','c3','c4') if f'"claimId": "{x}"' in prompt)
  import re
  source_ids=sorted(set(re.findall(r'"sourceId": "(u\d+)"',prompt)))
  return {'matches':[{'claimId':cid,'sourceId':sid,'spanId':f'{sid}:{cid}:s1','relation':'unclear'} for sid in source_ids]}
 _,r=m.run({'claims':claims},{'decisions':decisions},cfg(),'t','g',searcher=se,fetcher=fe,ai=ai)
 f=r['diagnosticCounts']
 assert r['candidatePages']==7
 assert f['sourceClaimPairs']>=20
 assert f['pairTasksExpected']==f['pairTasksReturned']
 assert f['pairTasksMissing']==0
 assert f['candidatePagesUnreferencedByAI']==0
 assert f['classificationCalls']==4 and r['apiCalls']==4
 assert r['supportingClaimsAdded']==0 and f['aiValidatedUnclear']==f['pairTasksExpected']



def test_v527_focused_query_diversity_preserves_numbers_and_distinctive_terms():
 qs=m.corroboration_queries('Game A','城レベル20を目指す',2)
 assert len(qs)==2 and qs[0]!=qs[1]
 assert '20' in qs[1] and '"Game A"' in qs[1]
 assert '攻略' in qs[1]


def test_v527_two_query_variants_dedupe_same_url_and_fetch_once():
 c,d=docs(); custom=cfg(); custom['maxCorroborationSearchesPerClaim']=2; custom['maxCorroborationSearchCallsPerRun']=2
 calls={'s':0,'f':0}
 def se(q,k,n):
  calls['s']+=1
  return {'results':[{'url':'https://b.example/guide','title':'Game A 資源箱 温存','content':'攻略'}]}
 def fe(u):
  calls['f']+=1
  return ('<body>Game A 資源箱は温存する</body>',{})
 _,r=m.run(c,d,custom,'t','g',searcher=se,fetcher=fe,ai=ai_support)
 f=r['diagnosticCounts']
 assert calls['s']==2 and r['searchCalls']==2
 assert calls['f']==1 and r['directFetches']==1
 assert f['duplicateUrls']==1 and f['discoveryUrlsUnique']==1
 assert f['searchQueryVariantsUsed']==1


def test_v527_search_rounds_cover_each_claim_before_second_query_when_globally_capped():
 claims=[]; decisions=[]
 for i in range(6):
  text=f'特殊語{i}を優先する'; row=claim(text,f'https://old{i}.example/a'); claims.append(row)
  decisions.append({'game':'Game A','category':'tip','claim':text,'status':'held_single_source','independentSources':[f'old{i}.example']})
 custom=cfg(); custom['maxCorroborationClaimsPerRun']=6; custom['maxCorroborationSearchesPerClaim']=2; custom['maxCorroborationSearchCallsPerRun']=8
 seen=[]
 def se(q,k,n):
  label=next(str(i) for i in range(6) if f'特殊語{i}' in q)
  seen.append(label)
  return {'results':[]}
 _,r=m.run({'claims':claims},{'decisions':decisions},custom,'t','g',searcher=se,fetcher=lambda *a:(_ for _ in ()).throw(AssertionError()),ai=lambda *a:(_ for _ in ()).throw(AssertionError()))
 assert seen[:6]==['0','1','2','3','4','5']
 assert len(seen)==8 and seen[6:]==['0','1']
 assert r['diagnosticCounts']['searchQueriesExecuted']==8


def test_v527_per_claim_fetch_bound_survives_two_query_variants():
 c,d=docs(); custom=cfg(); custom['maxCorroborationSearchesPerClaim']=2; custom['maxCorroborationSearchCallsPerRun']=2; custom['maxCorroborationResultsPerClaim']=4; custom['maxCorroborationFetchesPerRun']=12
 state={'s':0,'f':0}
 def se(q,k,n):
  base=state['s']; state['s']+=1
  return {'results':[{'url':f'https://q{base}-{i}.example/guide'} for i in range(10)]}
 def fe(u): state['f']+=1; return ('<body>Game A unrelated</body>',{})
 _,r=m.run(c,d,custom,'t','g',searcher=se,fetcher=fe,ai=lambda *a:{'matches':[]})
 assert r['searchCalls']==2
 assert state['f']<=4 and r['directFetches']<=4
 assert r['diagnosticCounts']['discoverySelectedForFetch']<=4


def test_v527_balanced_fetch_selection_prevents_first_claim_monopoly():
 claims=[]; decisions=[]
 for i in range(4):
  text=f'固有項目{i}を優先する'; row=claim(text,f'https://old{i}.example/a'); claims.append(row)
  decisions.append({'game':'Game A','category':'tip','claim':text,'status':'held_single_source','independentSources':[f'old{i}.example']})
 custom=cfg(); custom['maxCorroborationFetchesPerRun']=4; custom['maxCorroborationResultsPerClaim']=4
 state={'s':0}; fetched=[]
 def se(q,k,n):
  i=state['s']; state['s']+=1
  return {'results':[{'url':f'https://c{i}-{j}.example/guide'} for j in range(4)]}
 def fe(u): fetched.append(u); return ('<body>Game A unrelated</body>',{})
 _,r=m.run({'claims':claims},{'decisions':decisions},custom,'t','g',searcher=se,fetcher=fe,ai=lambda *a:{'matches':[]})
 assert len(fetched)==4
 assert {u.split('//c',1)[1].split('-',1)[0] for u in fetched}=={'0','1','2','3'}
 assert r['diagnosticCounts']['discoveryBalancedClaimsCovered']==4


def test_v527_same_site_for_origin_claim_can_be_retained_for_another_independent_claim():
 c1=claim('資源箱は温存する','https://a.example/original')
 c2=claim('建設枠を優先する','https://b.example/original')
 claims={'claims':[c1,c2]}
 decisions={'decisions':[
  {'game':'Game A','category':'tip','claim':c1['claim'],'status':'held_single_source','independentSources':['a.example']},
  {'game':'Game A','category':'tip','claim':c2['claim'],'status':'held_single_source','independentSources':['b.example']},
 ]}
 state={'s':0}
 def se(q,k,n):
  state['s']+=1
  if state['s']==1:
   return {'results':[{'url':'https://a.example/shared','title':'Game A 建設枠を優先する','content':'建設枠を優先する攻略'}]}
  return {'results':[]}
 def fe(u): return ('<body>Game A 建設枠を優先する</body>',{})
 def ai(key,model,prompt):
  if '"claimId": "c2"' in prompt:
   return {'matches':[{'claimId':'c2','sourceId':'u1','spanId':'u1:c2:s1','relation':'support'}]}
  return {'matches':[]}
 merged,r=m.run(claims,decisions,cfg(),'t','g',searcher=se,fetcher=fe,ai=ai)
 assert r['supportingClaimsAdded']==1
 assert r['diagnosticCounts']['sameSourceSiteUrls']==1
 assert r['diagnosticCounts']['sameSourceRetainedForOtherClaim']==1
 gated=m.gate.evaluate(merged)
 statuses={x['claim']:x['status'] for x in gated['decisions']}
 assert statuses['建設枠を優先する']=='supported_quarantine'
 assert statuses['資源箱は温存する']=='held_single_source'


def test_v527_search_metadata_only_prioritizes_fetch_and_never_becomes_evidence():
 c,d=docs(); custom=cfg(); custom['maxCorroborationSearchesPerClaim']=2; custom['maxCorroborationSearchCallsPerRun']=2; custom['maxCorroborationResultsPerClaim']=2
 state={'s':0}
 def se(q,k,n):
  state['s']+=1
  if state['s']==1:
   return {'results':[{'url':'https://bad.example/guide','title':'Game A 資源箱は温存する','content':'資源箱は温存する'}]}
  return {'results':[{'url':'https://good.example/guide','title':'Game A guide','content':'攻略'}]}
 def fe(url):
  if 'bad.example' in url: return ('<body>Game A 毎日ログインすると報酬がもらえる</body>',{})
  return ('<body>Game A 資源箱は温存する</body>',{})
 def ai(key,model,prompt):
  # Only the direct-source span from good.example can exist.
  import re
  ids=sorted(set(re.findall(r'"sourceId": "(u\d+)"',prompt)))
  assert len(ids)==1
  sid=ids[0]
  return {'matches':[{'claimId':'c1','sourceId':sid,'spanId':f'{sid}:c1:s1','relation':'support'}]}
 merged,r=m.run(c,d,custom,'t','g',searcher=se,fetcher=fe,ai=ai)
 added=[x for x in merged['claims'] if x['url']=='https://good.example/guide']
 assert len(added)==1 and added[0]['evidenceQuote'] in m.norm('Game A 資源箱は温存する')
 assert all(x['url']!='https://bad.example/guide' for x in merged['claims'][1:])
 assert r['supportingClaimsAdded']==1


def test_v527_second_query_can_recover_after_first_query_failure_without_relaxing_gate():
 c,d=docs(); custom=cfg(); custom['maxCorroborationSearchesPerClaim']=2; custom['maxCorroborationSearchCallsPerRun']=2
 state={'s':0}
 def se(q,k,n):
  state['s']+=1
  if state['s']==1: raise RuntimeError('first discovery failed')
  return {'results':[{'url':'https://b.example/guide'}]}
 merged,r=m.run(c,d,custom,'t','g',searcher=se,fetcher=fetch(),ai=ai_support)
 assert r['searchCalls']==2 and r['diagnosticCounts']['searchErrors']==1
 assert r['supportingClaimsAdded']==1 and len(merged['claims'])==2



def test_v527_discovery_metadata_ranking_can_prioritize_better_url_within_fetch_cap():
 c,d=docs(); custom=cfg(); custom['maxCorroborationFetchesPerRun']=1; custom['maxCorroborationResultsPerClaim']=2
 def se(q,k,n):
  return {'results':[
   {'url':'https://weak.example/guide','title':'Game A guide','content':'攻略'},
   {'url':'https://strong.example/guide','title':'Game A 資源箱は温存する','content':'資源箱 温存 攻略'},
  ]}
 fetched=[]
 def fe(url): fetched.append(url); return ('<body>Game A 資源箱は温存する</body>',{})
 _,r=m.run(c,d,custom,'t','g',searcher=se,fetcher=fe,ai=ai_support)
 assert fetched==['https://strong.example/guide']
 assert r['supportingClaimsAdded']==1


def test_v527_observed_six_held_four_input_shape_uses_balanced_two_query_discovery():
 labels=['甲','乙','丙','丁','戊','己']; claims=[]; decisions=[]
 for i,label in enumerate(labels,1):
  text=f'攻略対象{label}を優先する'
  row=claim(text,f'https://old{i}.example/original'); claims.append(row)
  decisions.append({'game':'Game A','category':'tip','claim':text,'status':'held_single_source','independentSources':[f'old{i}.example']})
 custom=cfg(); custom['maxCorroborationSearchesPerClaim']=2; custom['maxCorroborationSearchCallsPerRun']=8; custom['maxCorroborationFetchesPerRun']=12
 state={'s':0}
 def se(q,k,n):
  call=state['s']; state['s']+=1
  claim_index=call % 4 if call<4 else (call-4) % 4
  label=labels[claim_index]
  return {'results':[{'url':f'https://q{call}-{j}.example/guide','title':f'Game A 攻略対象{label}を優先する','content':f'攻略対象{label}'} for j in range(4)]}
 def fe(url):
  return ('<body>Game A '+ ' '.join(f'攻略対象{x}を優先する' for x in labels[:4]) +'</body>',{})
 def ai(key,model,prompt):
  import re
  cid=next(x for x in ('c1','c2','c3','c4') if f'"claimId": "{x}"' in prompt)
  pairs=sorted(set(re.findall(r'"sourceId": "(u\d+)"',prompt)))
  return {'matches':[{'claimId':cid,'sourceId':sid,'spanId':f'{sid}:{cid}:s1','relation':'unclear'} for sid in pairs]}
 _,r=m.run({'claims':claims},{'decisions':decisions},custom,'t','g',searcher=se,fetcher=fe,ai=ai)
 f=r['diagnosticCounts']
 assert r['totalHeldClaims']==6 and r['eligibleHeldClaims']==6 and r['inputHeldClaims']==4
 assert r['searchCalls']==8 and r['directFetches']==12
 assert f['searchQueryVariantsUsed']==4 and f['discoveryBalancedClaimsCovered']==4
 assert f['classificationCalls']==4 and f['pairTasksExpected']==f['pairTasksReturned'] and f['pairTasksMissing']==0
 assert r['supportingClaimsAdded']==0



def test_v527_second_query_can_displace_broad_first_query_result_under_one_fetch_cap():
 c,d=docs(); custom=cfg(); custom['maxCorroborationSearchesPerClaim']=2; custom['maxCorroborationSearchCallsPerRun']=2; custom['maxCorroborationResultsPerClaim']=1; custom['maxCorroborationFetchesPerRun']=1
 state={'s':0}; fetched=[]
 def se(q,k,n):
  state['s']+=1
  if state['s']==1:
   return {'results':[{'url':'https://broad.example/guide','title':'Game A 攻略まとめ','content':'初心者向け攻略'}]}
  return {'results':[{'url':'https://precise.example/guide','title':'Game A 資源箱は温存する','content':'資源箱を温存する攻略'}]}
 def fe(url): fetched.append(url); return ('<body>Game A 資源箱は温存する</body>',{})
 _,r=m.run(c,d,custom,'t','g',searcher=se,fetcher=fe,ai=ai_support)
 assert fetched==['https://precise.example/guide']
 assert r['searchCalls']==2 and r['directFetches']==1 and r['supportingClaimsAdded']==1



def test_v528_adaptive_backfill_prioritizes_claims_without_strict_direct_text():
 claims=[]; decisions=[]
 phrases=['資源箱は温存する','建設枠を優先する','列車注文を先に進める']
 hosts=['res','build','train']
 for i,text in enumerate(phrases,1):
  claims.append(claim(text,f'https://old{i}.example/original'))
  decisions.append({'game':'Game A','category':'tip','claim':text,'status':'held_single_source','independentSources':[f'old{i}.example']})
 custom=cfg(); custom['maxCorroborationFetchesPerRun']=5; custom['maxCorroborationResultsPerClaim']=4
 state={'s':0}; fetched=[]
 def se(q,k,n):
  call=state['s']; state['s']+=1; host=hosts[call]
  return {'results':[{'url':f'https://{host}{j}.example/guide','title':f'Game A {phrases[call]}'} for j in range(4)]}
 def fe(url):
  fetched.append(url)
  # First claim gets a strict page immediately. Other claims need backfill.
  if 'res0.example' in url: return ('<body>Game A 資源箱は温存する</body>',{})
  return ('<body>Game A 初心者向けの一般攻略情報</body>',{})
 _,r=m.run({'claims':claims},{'decisions':decisions},custom,'t','g',searcher=se,fetcher=fe,ai=lambda *a:{'matches':[]})
 f=r['diagnosticCounts']
 assert r['directFetches']==5
 assert sum('res' in x for x in fetched)==1
 assert sum('build' in x for x in fetched)==2 and sum('train' in x for x in fetched)==2
 assert f['discoveryInitialFetches']==3 and f['discoveryBackfillFetches']==2
 assert f['backfillClaimsTargeted']==2 and f['directTextStrictClaimHits']==1


def test_v528_direct_page_text_not_search_metadata_controls_backfill_priority():
 c1=claim('資源箱は温存する','https://old1.example/original')
 c2=claim('建設枠を優先する','https://old2.example/original')
 decisions={'decisions':[
  {'game':'Game A','category':'tip','claim':c1['claim'],'status':'held_single_source','independentSources':['old1.example']},
  {'game':'Game A','category':'tip','claim':c2['claim'],'status':'held_single_source','independentSources':['old2.example']},
 ]}
 custom=cfg(); custom['maxCorroborationFetchesPerRun']=3; custom['maxCorroborationResultsPerClaim']=3
 state={'s':0}; fetched=[]
 def se(q,k,n):
  state['s']+=1
  if state['s']==1:
   return {'results':[
    {'url':'https://fake-strong.example/one','title':'Game A 資源箱は温存する','content':'資源箱 温存'},
    {'url':'https://real.example/two','title':'Game A guide','content':'攻略'},
   ]}
  return {'results':[{'url':'https://build.example/one','title':'Game A 建設枠を優先する','content':'建設枠'}]}
 def fe(url):
  fetched.append(url)
  if 'fake-strong' in url: return ('<body>Game A 毎日ログインする</body>',{})
  if 'real.example' in url: return ('<body>Game A 資源箱は温存する</body>',{})
  return ('<body>Game A 建設枠を優先する</body>',{})
 _,r=m.run({'claims':[c1,c2]},decisions,custom,'t','g',searcher=se,fetcher=fe,ai=lambda *a:{'matches':[]})
 assert fetched[0]=='https://fake-strong.example/one'
 assert 'https://real.example/two' in fetched
 f=r['diagnosticCounts']
 assert f['directTextStrictClaimHits']==2 and f['backfillStrictGains']>=1


def test_v528_target_missing_initial_page_keeps_claim_weak_and_triggers_backfill():
 c,d=docs(); custom=cfg(); custom['maxCorroborationFetchesPerRun']=2; custom['maxCorroborationResultsPerClaim']=2
 def se(q,k,n): return {'results':[{'url':'https://miss.example/one'},{'url':'https://good.example/two'}]}
 fetched=[]
 def fe(url):
  fetched.append(url)
  if 'miss' in url: return ('<body>Different Game 資源箱は温存する</body>',{})
  return ('<body>Game A 資源箱は温存する</body>',{})
 _,r=m.run(c,d,custom,'t','g',searcher=se,fetcher=fe,ai=ai_support)
 f=r['diagnosticCounts']
 assert fetched==['https://miss.example/one','https://good.example/two']
 assert f['targetMissing']==1 and f['discoveryBackfillFetches']==1
 assert f['directTextStrictClaimHits']==1 and r['supportingClaimsAdded']==1


def test_v528_all_strict_initial_pages_keep_bounded_exploration_for_conflict_coverage():
 c,d=docs(); custom=cfg(); custom['maxCorroborationFetchesPerRun']=3; custom['maxCorroborationResultsPerClaim']=3
 def se(q,k,n): return {'results':[{'url':f'https://s{i}.example/g'} for i in range(3)]}
 fetched=[]
 def fe(url): fetched.append(url); return ('<body>Game A 資源箱は温存する</body>',{})
 _,r=m.run(c,d,custom,'t','g',searcher=se,fetcher=fe,ai=lambda *a:{'matches':[]})
 f=r['diagnosticCounts']
 assert len(fetched)==3 and r['directFetches']==3
 assert f['discoveryAllStrictReachedBeforeBudget']==1
 assert f['discoveryInitialFetches']==1 and f['discoveryBackfillFetches']==2


def test_v528_adaptive_probe_respects_existing_source_site_independence():
 c1=claim('資源箱は温存する','https://same.example/original')
 c2=claim('建設枠を優先する','https://other.example/original')
 decisions={'decisions':[
  {'game':'Game A','category':'tip','claim':c1['claim'],'status':'held_single_source','independentSources':['same.example']},
  {'game':'Game A','category':'tip','claim':c2['claim'],'status':'held_single_source','independentSources':['other.example']},
 ]}
 custom=cfg(); custom['maxCorroborationFetchesPerRun']=2
 state={'s':0}
 def se(q,k,n):
  state['s']+=1
  if state['s']==1: return {'results':[{'url':'https://same.example/shared'}]}
  return {'results':[{'url':'https://new.example/build'}]}
 def fe(url):
  if 'same.example' in url: return ('<body>Game A 資源箱は温存する</body>',{})
  return ('<body>Game A 建設枠を優先する</body>',{})
 _,r=m.run({'claims':[c1,c2]},decisions,custom,'t','g',searcher=se,fetcher=fe,ai=lambda *a:{'matches':[]})
 # same.example cannot make c1 strict, though its text contains c1 exactly.
 assert r['diagnosticCounts']['directTextStrictClaimHits']==1


def test_v528_backfill_never_exceeds_global_or_per_claim_fetch_caps():
 c,d=docs(); custom=cfg(); custom['maxCorroborationFetchesPerRun']=3; custom['maxCorroborationResultsPerClaim']=2
 def se(q,k,n): return {'results':[{'url':f'https://u{i}.example/g'} for i in range(6)]}
 calls={'f':0}
 def fe(url): calls['f']+=1; return ('<body>Game A general information only</body>',{})
 _,r=m.run(c,d,custom,'t','g',searcher=se,fetcher=fe,ai=lambda *a:{'matches':[]})
 assert calls['f']==2 and r['directFetches']==2
 assert r['diagnosticCounts']['discoverySelectedForFetch']==2


def test_v528_observed_v527_shape_adapts_fixed_twelve_fetch_budget_without_gate_relaxation():
 phrases=['資源箱は温存する','建設枠を優先する','列車注文を先に進める','畑の拡張を後回しにする']; claims=[]; decisions=[]
 for i,text in enumerate(phrases,1):
  claims.append(claim(text,f'https://old{i}.example/original'))
  decisions.append({'game':'Game A','category':'tip','claim':text,'status':'held_single_source','independentSources':[f'old{i}.example']})
 custom=cfg(); custom['maxCorroborationSearchesPerClaim']=2; custom['maxCorroborationSearchCallsPerRun']=8; custom['maxCorroborationFetchesPerRun']=12
 state={'s':0}; fetched=[]
 def se(q,k,n):
  call=state['s']; state['s']+=1; ci=call%4
  return {'results':[{'url':f'https://q{call}-{j}.example/g','title':f'Game A {phrases[ci]}'} for j in range(4)]}
 def fe(url):
  fetched.append(url)
  # Only the first claim has a strict page early; other claims stay weak.
  if url.startswith('https://q0-'): return ('<body>Game A 資源箱は温存する</body>',{})
  return ('<body>Game A 一般的な序盤攻略の説明</body>',{})
 _,r=m.run({'claims':claims},{'decisions':decisions},custom,'t','g',searcher=se,fetcher=fe,ai=lambda *a:{'matches':[]})
 f=r['diagnosticCounts']
 assert r['searchCalls']==8 and r['directFetches']==12
 assert f['discoveryBalancedClaimsCovered']==4 and f['directTextStrictClaimHits']==1
 assert f['discoveryInitialFetches']==4 and f['discoveryBackfillFetches']==8
 assert f['backfillClaimsTargeted']>=3
 assert r['supportingClaimsAdded']==0 and r['publicationWrites']==0


def test_v528_adaptive_backfill_can_recover_second_claim_with_same_three_fetch_budget():
 c1=claim('資源箱は温存する','https://old1.example/original')
 c2=claim('建設枠を優先する','https://old2.example/original')
 decisions={'decisions':[
  {'game':'Game A','category':'tip','claim':c1['claim'],'status':'held_single_source','independentSources':['old1.example']},
  {'game':'Game A','category':'tip','claim':c2['claim'],'status':'held_single_source','independentSources':['old2.example']},
 ]}
 custom=cfg(); custom['maxCorroborationFetchesPerRun']=3; custom['maxCorroborationResultsPerClaim']=3
 state={'s':0}; fetched=[]
 def se(q,k,n):
  state['s']+=1
  if state['s']==1:
   return {'results':[{'url':'https://r1.example/g'},{'url':'https://r2.example/g'}]}
  return {'results':[{'url':'https://b1.example/g'},{'url':'https://b2.example/g'}]}
 def fe(url):
  fetched.append(url)
  if 'r1' in url: return ('<body>Game A 資源箱は温存する</body>',{})
  if 'b2' in url: return ('<body>Game A 建設枠を優先する</body>',{})
  return ('<body>Game A 一般的な攻略説明</body>',{})
 _,r=m.run({'claims':[c1,c2]},decisions,custom,'t','g',searcher=se,fetcher=fe,ai=lambda *a:{'matches':[]})
 # Initial fair round fetches r1 and b1. The only remaining slot must go to
 # weak c2, not already-strict c1, so b2 is recovered within the same cap.
 assert fetched==['https://r1.example/g','https://b1.example/g','https://b2.example/g']
 f=r['diagnosticCounts']
 assert f['directTextStrictClaimHits']==2 and f['backfillStrictGains']==1
 assert r['directFetches']==3 and r['publicationWrites']==0
