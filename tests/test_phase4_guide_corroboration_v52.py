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
 assert r['rejected']['unknown_span']==1


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


def test_v525_logic_version_is_reported_for_live_audit():
 c,d=docs(); _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=ai_support)
 assert r['logicVersion']=='V52.5'


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
 assert r['apiCalls']==2 and state['ai']==2
 assert r['diagnosticCounts']['semanticReviewCalls']==1
