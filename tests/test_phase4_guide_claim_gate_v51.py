import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('gate',ROOT/'scripts'/'evaluate_guide_claims.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def c(claim='資源箱は温存する',url='https://guide-a.example/a',source='community_guide',category='tip',status='validated_quarantine'):
 return {'game':'Game A','category':category,'claim':claim,'evidenceQuote':claim,'sourceId':'s1','url':url,'sourceType':source,'status':status}

def ev(rows): return m.evaluate({'claims':rows})

def test_single_community_claim_is_held():
 r=ev([c()]); d=r['decisions'][0]; assert d['status']=='held_single_source' and not d['publicationEligible']

def test_two_independent_sites_support_same_claim_in_quarantine():
 r=ev([c(),c(url='https://guide-b.example/b')]); d=r['decisions'][0]
 assert d['status']=='supported_quarantine' and d['reason']=='independent_corroboration' and d['independentSourceCount']==2
 assert r['publicationWrites']==0 and r['publicationEligibleClaims']==0

def test_same_site_two_pages_do_not_count_as_independent():
 r=ev([c(url='https://www.guide.example/a'),c(url='https://blog.guide.example/b')]); d=r['decisions'][0]
 assert d['status']=='held_single_source' and d['independentSourceCount']==1

def test_official_source_can_support_without_community_corroboration():
 r=ev([c(url='https://game.example/help',source='official')]); d=r['decisions'][0]
 assert d['status']=='supported_quarantine' and d['reason']=='official_source' and d['officialSourceCount']==1

def test_punctuation_and_width_variants_group_conservatively():
 r=ev([c('城レベル１０を目指す。'),c('城レベル10を目指す',url='https://guide-b.example/b')])
 assert len(r['decisions'])==1 and r['decisions'][0]['independentSourceCount']==2

def test_numeric_variants_with_same_template_are_conflict():
 r=ev([c('城レベル10を3日で目指す'),c('城レベル20を3日で目指す',url='https://guide-b.example/b')])
 assert len(r['conflicts'])==1 and all(d['status']=='held_conflict' for d in r['decisions'])

def test_official_numeric_conflict_still_holds_both_variants():
 r=ev([c('城レベル10を3日で目指す',url='https://game.example/a',source='official'),c('城レベル20を3日で目指す',url='https://guide.example/b')])
 assert all(d['status']=='held_conflict' for d in r['decisions'])

def test_unrelated_numeric_claims_are_not_false_conflict():
 r=ev([c('城レベル10を目指す'),c('兵舎レベル20を目指す',url='https://guide-b.example/b')])
 assert r['conflicts']==[]

def test_non_numeric_different_wording_not_fuzzily_merged():
 r=ev([c('資源箱は温存する'),c('資源箱を残しておく',url='https://guide-b.example/b')])
 assert len(r['decisions'])==2 and all(d['status']=='held_single_source' for d in r['decisions'])

def test_invalid_or_nonquarantined_input_is_rejected_fail_closed():
 r=ev([c(status='published'),c(url='http://guide.example/a'),c(source='unknown')])
 assert r['decisions']==[] and r['counts']['rejectedInputClaims']==3

def test_localhost_and_literal_ip_are_not_source_sites():
 assert m.source_site('https://localhost/a')==''
 assert m.source_site('https://127.0.0.1/a')==''
 assert m.source_site('https://[::1]/a')==''

def test_japanese_multilabel_domain_subdomains_collapse():
 assert m.source_site('https://www.foo.co.jp/a')=='foo.co.jp'
 assert m.source_site('https://blog.foo.co.jp/b')=='foo.co.jp'

def test_duplicate_same_page_increases_evidence_not_independence():
 r=ev([c(),c()]); d=r['decisions'][0]
 assert d['evidenceCount']==2 and d['independentSourceCount']==1 and d['status']=='held_single_source'

def test_category_boundary_prevents_cross_category_corroboration():
 r=ev([c(category='tip'),c(url='https://guide-b.example/b',category='warning')])
 assert len(r['decisions'])==2

def test_game_boundary_prevents_cross_game_corroboration():
 x=c(url='https://guide-b.example/b'); x['game']='Game B'
 r=ev([c(),x]); assert len(r['decisions'])==2

def test_output_is_api_free_and_never_publication_eligible():
 r=ev([c(source='official')]); assert r['apiCalls']==0 and r['publicationWrites']==0 and r['publicationEligibleClaims']==0
