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
def ai_support(key,model,prompt): return {'matches':[{'claimId':'c1','sourceId':'u1','relation':'support','evidenceQuote':'資源箱は温存する'}]}

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
 c,d=docs(); bad=lambda *a:{'matches':[{'claimId':'c1','sourceId':'u1','relation':'support','evidenceQuote':'存在しない引用'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=bad)
 assert r['supportingClaimsAdded']==0 and r['rejected']['quote_not_in_source']==1

def test_numeric_claim_requires_same_number_in_quote():
 c,d=docs('城レベル20を目指す'); bad=lambda *a:{'matches':[{'claimId':'c1','sourceId':'u1','relation':'support','evidenceQuote':'城レベル10を目指す'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 城レベル10を目指す'),ai=bad)
 assert r['supportingClaimsAdded']==0 and r['rejected']['numeric_not_grounded']==1

def test_numeric_grounding_uses_exact_tokens_not_substrings():
 c,d=docs('城レベル20を目指す'); bad=lambda *a:{'matches':[{'claimId':'c1','sourceId':'u1','relation':'support','evidenceQuote':'城レベル120を目指す'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 城レベル120を目指す'),ai=bad)
 assert r['supportingClaimsAdded']==0 and r['rejected']['numeric_not_grounded']==1

def test_semantically_unrelated_quote_rejected_by_overlap_guard():
 c,d=docs(); bad=lambda *a:{'matches':[{'claimId':'c1','sourceId':'u1','relation':'support','evidenceQuote':'毎日ログインすると報酬がもらえる'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 毎日ログインすると報酬がもらえる'),ai=bad)
 assert r['supportingClaimsAdded']==0 and r['rejected']['insufficient_lexical_overlap']==1

def test_contradiction_is_quarantined_not_appended():
 c,d=docs('城レベル20を目指す'); a=lambda *x:{'matches':[{'claimId':'c1','sourceId':'u1','relation':'contradict','evidenceQuote':'城レベル10を目指す'}]}
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
   {'claimId':'c1','sourceId':'u1','relation':'support','evidenceQuote':'攻略項目甲を優先する'},
   {'claimId':'c2','sourceId':'u2','relation':'support','evidenceQuote':'攻略項目乙を優先する'},
   {'claimId':'c3','sourceId':'u3','relation':'support','evidenceQuote':'攻略項目丙を優先する'},
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
 bad=lambda *a:{'matches':[{'claimId':'c1','sourceId':'u1','relation':'support','evidenceQuote':'存在しない引用'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=bad)
 assert r['diagnosticCounts']['aiProposedMatches']==1
 assert r['diagnosticCounts']['aiRejectedMatches']==1
 assert r['rejected']['quote_not_in_source']==1


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
 def ai(*a): return {'matches':[{'claimId':'c1','sourceId':'u2','relation':'support','evidenceQuote':'資源箱は温存する'}]}
 merged,r=m.run(claims,decisions,cfg(),'t','g',searcher=se,fetcher=fe,ai=ai)
 assert len(merged['claims'])==2
 assert r['supportingClaimsAdded']==0
 assert r['rejected']['not_independent_for_claim']==1


def test_contradiction_requires_same_claim_context():
 c,d=docs('資源箱は温存する')
 unrelated=lambda *a:{'matches':[{'claimId':'c1','sourceId':'u1','relation':'contradict','evidenceQuote':'毎日ログインすると報酬がもらえる'}]}
 _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch('Game A 毎日ログインすると報酬がもらえる'),ai=unrelated)
 assert r['contradictionsFound']==0
 assert r['rejected']['contradiction_context_mismatch']==1


def test_report_always_exposes_diagnostic_counts_without_publication():
 c,d=docs(); _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=ai_support)
 assert isinstance(r['diagnosticCounts'],dict)
 assert r['diagnosticCounts']['aiValidatedSupport']==1
 assert r['publicationWrites']==0


def test_v523_logic_version_is_reported_for_live_audit():
 c,d=docs(); _,r=m.run(c,d,cfg(),'t','g',searcher=search(),fetcher=fetch(),ai=ai_support)
 assert r['logicVersion']=='V52.3'


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
