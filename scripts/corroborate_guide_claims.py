#!/usr/bin/env python3
"""PHASE 4 V52: bounded independent corroboration for held guide claims.

Only V51 held_single_source claims are searched. Tavily discovers URLs; every
candidate is fetched directly, target-confirmed, source-site independent, and
Gemini may only map a directly quoted passage to an existing held claim. Python
then verifies quote presence, numeric grounding, and conservative lexical
overlap. Outputs remain quarantine-only.
"""
from __future__ import annotations
import json, os, re, sys, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import collect_guide_evidence as collector
import evaluate_guide_claims as gate
import extract_guide_claims as extractor

CLAIMS=ROOT/'data'/'guide_claims.json'
DECISIONS=ROOT/'data'/'guide_claim_decisions.json'
CONFIG=ROOT/'config'/'guide_research.json'
OUT=ROOT/'data'/'guide_claims_corroborated.json'
REPORT=ROOT/'data'/'guide_corroboration.json'
STATUS=ROOT/'data'/'guide_corroboration_status.json'

def now_iso(): return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def compact(s): return ''.join(ch for ch in unicodedata.normalize('NFKC',str(s or '')).casefold() if ch.isalnum())
def nums(s): return tuple(x.replace(',','') for x in re.findall(r'\d+(?:[.,]\d+)?',unicodedata.normalize('NFKC',str(s or ''))))
def numeric_grounded(claim, quote):
    required=list(nums(claim)); found=list(nums(quote))
    for value in set(required):
        if found.count(value) < required.count(value): return False
    return True
def bigrams(s):
    s=compact(s)
    return {s[i:i+2] for i in range(max(0,len(s)-1))}
def overlap_ok(claim,quote):
    a=bigrams(re.sub(r'\d+(?:[.,]\d+)?','',claim)); b=bigrams(re.sub(r'\d+(?:[.,]\d+)?','',quote))
    if not a: return False
    return len(a & b)/len(a) >= 0.35

def build_prompt(game,held,sources):
    return f'''POIGAME LAB 裏取り判定。対象ゲーム: {game}\n
既存claimを、候補ページ本文だけで裏取りする。一般知識・検索スニペット・推測は禁止。\n
support は本文が同じ攻略上の主張を明確に述べる場合だけ。数字を含むclaimは同じ数字が引用にも必要。\n
contradict は同じ対象・条件について異なる数字や明確に反対の内容を述べる場合だけ。その他はunclear。\n
必ず本文に実在する短い原文 evidenceQuote を返す。JSON以外禁止。\n
形式: {{"matches":[{{"claimId":"c1","sourceId":"u1","relation":"support|contradict|unclear","evidenceQuote":""}}]}}\nheldClaims:\n'''+json.dumps(held,ensure_ascii=False)+'\nsources:\n'+json.dumps([{'sourceId':s['sourceId'],'text':s['text'][:18000]} for s in sources],ensure_ascii=False)

def validate_match(raw,claim_by_id,source_by_id):
    if not isinstance(raw,dict): return None,'malformed'
    cid=norm(raw.get('claimId')); sid=norm(raw.get('sourceId')); rel=norm(raw.get('relation')); quote=norm(raw.get('evidenceQuote'))
    if cid not in claim_by_id or sid not in source_by_id: return None,'unknown_reference'
    if rel not in {'support','contradict','unclear'}: return None,'invalid_relation'
    if len(quote)<4 or extractor.norm_match(quote) not in extractor.norm_match(source_by_id[sid]['text']): return None,'quote_not_in_source'
    claim=claim_by_id[cid]
    if rel=='support':
        if not numeric_grounded(claim['claim'],quote): return None,'numeric_not_grounded'
        if not overlap_ok(claim['claim'],quote): return None,'insufficient_lexical_overlap'
    return {'claimId':cid,'sourceId':sid,'relation':rel,'evidenceQuote':quote},None

def run(claims_doc=None,decisions_doc=None,cfg=None,tavily_key=None,gemini_key=None,searcher=collector.tavily_search,fetcher=collector.direct_fetch,ai=extractor.live_gemini):
    claims_doc=claims_doc or json.loads(CLAIMS.read_text(encoding='utf-8'))
    decisions_doc=decisions_doc or json.loads(DECISIONS.read_text(encoding='utf-8'))
    cfg=cfg or json.loads(CONFIG.read_text(encoding='utf-8'))
    tavily_key=tavily_key if tavily_key is not None else os.getenv('TAVILY_API_KEY','')
    gemini_key=gemini_key if gemini_key is not None else os.getenv('GEMINI_API_KEY','')
    if not tavily_key: raise RuntimeError('TAVILY_API_KEY unavailable')
    if not gemini_key: raise RuntimeError('GEMINI_API_KEY unavailable')
    base=[x for x in (claims_doc.get('claims') or []) if gate.valid_claim(x)]
    held=[d for d in (decisions_doc.get('decisions') or []) if d.get('status')=='held_single_source']
    max_claims=max(1,min(6,int(cfg.get('maxCorroborationClaimsPerRun',4))))
    max_results=max(1,min(6,int(cfg.get('maxCorroborationResultsPerClaim',4))))
    max_fetches=max(1,min(16,int(cfg.get('maxCorroborationFetchesPerRun',12))))
    held=held[:max_claims]; search_calls=fetch_calls=api_calls=0; candidates=[]; seen_urls=set(); diagnostics=[]
    existing_sites_by_claim={(d['game'],d['category'],gate.text_key(d['claim'])):set(d.get('independentSources') or []) for d in held}
    for i,d in enumerate(held,1):
        diag={'claimId':f'c{i}','game':d['game'],'searchResults':0,'eligibleIndependentUrls':0,'directFetches':0}
        query=f'"{d["game"]}" {d["claim"]}'
        search_calls+=1
        try: res=searcher(query,tavily_key,max_results)
        except Exception as e:
            diag['searchError']=collector.safe_error(e); diagnostics.append(diag); continue
        items=(res.get('results') or [])[:max_results]; diag['searchResults']=len(items)
        oldsites=existing_sites_by_claim[(d['game'],d['category'],gate.text_key(d['claim']))]
        for item in items:
            if fetch_calls>=max_fetches: break
            url=collector.canonical_url(str((item or {}).get('url') or ''))
            site=gate.source_site(url)
            if not url or url in seen_urls or not site or site in oldsites or collector.blocked_url(url,cfg.get('blockedDomains') or []): continue
            seen_urls.add(url); diag['eligibleIndependentUrls']+=1; fetch_calls+=1; diag['directFetches']+=1
            try: raw,_=fetcher(url); text=collector.visible_text(raw)
            except Exception: continue
            if not collector.target_in_text(text,[d['game']]): continue
            candidates.append({'claimId':f'c{i}','game':d['game'],'category':d['category'],'claim':d['claim'],'sourceId':f'u{len(candidates)+1}','url':url,'site':site,'sourceType':collector.source_type(url,d['game'],cfg),'text':text})
        diagnostics.append(diag)
    matches=[]; rejected={}; appended=[]; contradictions=[]
    by_game={}
    for c in candidates: by_game.setdefault(c['game'],[]).append(c)
    for game,rows in sorted(by_game.items()):
        held_map={c['claimId']:{'claimId':c['claimId'],'category':c['category'],'claim':c['claim']} for c in rows}
        sources={c['sourceId']:c for c in rows}; claim_by_id={k:v for k,v in held_map.items()}
        try:
            api_calls+=1; response=ai(gemini_key,os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite'),build_prompt(game,list(held_map.values()),list(sources.values())))
        except Exception as e:
            diagnostics.append({'game':game,'aiError':collector.safe_error(e)}); continue
        proposed=response.get('matches') if isinstance(response,dict) else []
        for raw in proposed if isinstance(proposed,list) else []:
            match,reason=validate_match(raw,claim_by_id,sources)
            if reason: rejected[reason]=rejected.get(reason,0)+1; continue
            matches.append(match); src=sources[match['sourceId']]; claim=claim_by_id[match['claimId']]
            if match['relation']=='support':
                appended.append({'game':game,'category':claim['category'],'claim':claim['claim'],'evidenceQuote':match['evidenceQuote'],'sourceId':'v52:'+match['sourceId'],'url':src['url'],'sourceType':src['sourceType'],'status':'validated_quarantine'})
            elif match['relation']=='contradict':
                contradictions.append({'game':game,'category':claim['category'],'claim':claim['claim'],'url':src['url'],'evidenceQuote':match['evidenceQuote'],'status':'quarantined_contradiction'})
    unique={(x['game'],x['category'],gate.text_key(x['claim']),x['url']):x for x in base+appended}
    merged=[unique[k] for k in sorted(unique)]
    report={'phase':'PHASE4_GUIDE_CORROBORATION_V52','generatedAt':now_iso(),'inputHeldClaims':len(held),'searchCalls':search_calls,'directFetches':fetch_calls,'apiCalls':api_calls,'candidatePages':len(candidates),'validatedMatches':len(matches),'supportingClaimsAdded':len(appended),'contradictionsFound':len(contradictions),'rejected':rejected,'publicationWrites':0,'diagnostics':diagnostics,'contradictions':contradictions}
    return {'phase':'PHASE4_GUIDE_CLAIMS_CORROBORATED_V52','generatedAt':report['generatedAt'],'publicationWrites':0,'claims':merged},report

def main():
    try:
        merged,report=run(); OUT.write_text(json.dumps(merged,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        status={k:report[k] for k in ['phase','inputHeldClaims','searchCalls','directFetches','apiCalls','candidatePages','validatedMatches','supportingClaimsAdded','contradictionsFound','publicationWrites']}; status.update({'success':True,'lastRun':report['generatedAt']}); STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(status,ensure_ascii=False))
    except Exception as e:
        status={'phase':'PHASE4_GUIDE_CORROBORATION_V52','success':False,'error':collector.safe_error(e),'publicationWrites':0,'lastRun':now_iso()}; STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(status,ensure_ascii=False)); raise
if __name__=='__main__': main()
