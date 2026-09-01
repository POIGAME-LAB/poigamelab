#!/usr/bin/env python3
"""PHASE 4 V52: bounded independent corroboration for held guide claims.

Only V51 held_single_source claims are searched. Tavily discovers URLs; every
candidate is fetched directly, target-confirmed, source-site independent, and
Gemini may only select a Python-created evidence span for an existing held claim.
Python pre-filters independent source/claim pairs, verifies exact span identity,
numeric grounding, and conservative lexical overlap. Outputs remain quarantine-only.
"""
from __future__ import annotations
import json, os, re, sys, unicodedata
from datetime import datetime, timezone
from pathlib import Path

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
LOGIC_VERSION='V52.4'

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

def claim_windows(claim_id, source_id, claim, text, window_chars=240, step_chars=120, max_spans=4):
    """Return bounded exact text windows ranked by the deterministic overlap gate.

    Gemini never writes evidence text in V52.4; it can only select one of these
    Python-created spans. Windows overlap so a short supporting sentence near a
    boundary is still likely to be available without sending the whole page as
    free-form quote material.
    """
    text=norm(text)[:18000]
    if not text: return []
    window_chars=max(120,min(480,int(window_chars))); step_chars=max(60,min(window_chars,int(step_chars)))
    starts=list(range(0,max(1,len(text)),step_chars))
    last=max(0,len(text)-window_chars)
    if last not in starts: starts.append(last)
    seen=set(); ranked=[]
    claim_no_nums=re.sub(r'\d+(?:[.,]\d+)?','',claim)
    a=bigrams(claim_no_nums)
    required=nums(claim)
    for pos in starts:
        chunk=text[pos:pos+window_chars].strip()
        if len(chunk)<4 or chunk in seen: continue
        seen.add(chunk)
        b=bigrams(re.sub(r'\d+(?:[.,]\d+)?','',chunk))
        lexical=(len(a & b)/len(a)) if a else 0.0
        same_numbers=1 if required and numeric_grounded(claim,chunk) else 0
        if lexical >= 0.35:
            ranked.append((lexical,same_numbers,-pos,chunk))
    ranked.sort(reverse=True)
    out=[]
    for rank,(_,_,_,chunk) in enumerate(ranked[:max_spans],1):
        out.append({'spanId':f'{source_id}:{claim_id}:s{rank}','claimId':claim_id,'sourceId':source_id,'text':chunk})
    return out


def build_evidence_spans(held_map, sources):
    spans=[]; considered=with_spans=no_lexical=0
    for source in sources:
        for cid,claim in held_map.items():
            if source['site'] in set(claim.get('existingSites') or []):
                continue
            considered+=1
            pair_spans=claim_windows(cid,source['sourceId'],claim['claim'],source['text'])
            if pair_spans:
                with_spans+=1; spans.extend(pair_spans)
            else:
                no_lexical+=1
    return spans,considered,with_spans,no_lexical


def build_prompt(game,held,spans):
    header=f"""POIGAME LAB 裏取り判定。対象ゲーム: {game}

既存claimを、Pythonが直接取得本文から切り出した evidenceSpans だけで裏取りする。一般知識・検索スニペット・推測は禁止。

support は同じ攻略上の主張を明確に述べる場合だけ。contradict は同じ対象・条件について異なる数字や明確に反対の場合だけ。その他はunclear。

証拠文を自分で書き写したり言い換えたりせず、必ず与えられた spanId を1つ選ぶ。claimId/sourceId/spanId の組み合わせを変更・創作しない。JSON以外禁止。

形式: {{"matches":[{{"claimId":"c1","sourceId":"u1","spanId":"u1:c1:s1","relation":"support|contradict|unclear"}}]}}
heldClaims:
"""
    compact=[{'claimId':x['claimId'],'sourceId':x['sourceId'],'spanId':x['spanId'],'text':x['text']} for x in spans]
    return header+json.dumps(held,ensure_ascii=False)+'\nevidenceSpans:\n'+json.dumps(compact,ensure_ascii=False)


def validate_match(raw,claim_by_id,source_by_id,span_by_id):
    if not isinstance(raw,dict): return None,'malformed'
    cid=norm(raw.get('claimId')); sid=norm(raw.get('sourceId')); span_id=norm(raw.get('spanId')); rel=norm(raw.get('relation'))
    if cid not in claim_by_id or sid not in source_by_id: return None,'unknown_reference'
    if span_id not in span_by_id: return None,'unknown_span'
    if rel not in {'support','contradict','unclear'}: return None,'invalid_relation'
    span=span_by_id[span_id]
    if span.get('claimId')!=cid or span.get('sourceId')!=sid: return None,'span_pair_mismatch'
    claim=claim_by_id[cid]
    if source_by_id[sid]['site'] in set(claim.get('existingSites') or []): return None,'not_independent_for_claim'
    quote=span['text']
    if rel=='support':
        if not numeric_grounded(claim['claim'],quote): return None,'numeric_not_grounded'
        if not overlap_ok(claim['claim'],quote): return None,'insufficient_lexical_overlap'
    elif rel=='contradict' and not overlap_ok(claim['claim'],quote):
        return None,'contradiction_context_mismatch'
    return {'claimId':cid,'sourceId':sid,'spanId':span_id,'relation':rel,'evidenceQuote':quote},None

def run(claims_doc=None,decisions_doc=None,cfg=None,tavily_key=None,gemini_key=None,searcher=collector.tavily_search,fetcher=collector.direct_fetch,ai=extractor.live_gemini):
    claims_doc=claims_doc or json.loads(CLAIMS.read_text(encoding='utf-8'))
    decisions_doc=decisions_doc or json.loads(DECISIONS.read_text(encoding='utf-8'))
    cfg=cfg or json.loads(CONFIG.read_text(encoding='utf-8'))
    tavily_key=tavily_key if tavily_key is not None else os.getenv('TAVILY_API_KEY','')
    gemini_key=gemini_key if gemini_key is not None else os.getenv('GEMINI_API_KEY','')
    if not tavily_key: raise RuntimeError('TAVILY_API_KEY unavailable')
    if not gemini_key: raise RuntimeError('GEMINI_API_KEY unavailable')
    base=[x for x in (claims_doc.get('claims') or []) if gate.valid_claim(x)]
    all_held=[d for d in (decisions_doc.get('decisions') or []) if isinstance(d,dict) and d.get('status')=='held_single_source']
    base_keys={(x['game'],x['category'],gate.text_key(x['claim'])) for x in base}
    held=[d for d in all_held if (d.get('game'),d.get('category'),gate.text_key(d.get('claim'))) in base_keys]
    orphan_held=len(all_held)-len(held); total_held=len(all_held); eligible_held=len(held)
    max_claims=max(1,min(6,int(cfg.get('maxCorroborationClaimsPerRun',4))))
    max_results=max(1,min(6,int(cfg.get('maxCorroborationResultsPerClaim',4))))
    max_fetches=max(1,min(16,int(cfg.get('maxCorroborationFetchesPerRun',12))))
    held=held[:max_claims]; search_calls=fetch_calls=api_calls=0; candidates=[]; seen_urls=set(); diagnostics=[]
    funnel={
        'orphanHeldDecisions':orphan_held,'searchErrors':0,'malformedSearchResponses':0,'malformedSearchItems':0,
        'searchResults':0,'invalidOrUnsupportedUrls':0,'duplicateUrls':0,
        'sameSourceSiteUrls':0,'blockedOrUnsafeUrls':0,'eligibleIndependentUrls':0,
        'fetchErrors':0,'targetMissing':0,'candidatePages':0,'aiErrors':0,'aiMalformedResponses':0,
        'aiProposedMatches':0,'aiProposalsDropped':0,'aiRejectedMatches':0,'aiValidatedSupport':0,
        'aiValidatedContradict':0,'aiValidatedUnclear':0,'candidatePagesUnreferencedByAI':0,
        'sourceClaimPairsConsidered':0,'sourceClaimPairs':0,'sourceClaimPairsNoLexicalSpan':0,
        'evidenceSpans':0,'sourcesWithoutEligibleSpans':0,
    }
    existing_sites_by_claim={(d['game'],d['category'],gate.text_key(d['claim'])):set(d.get('independentSources') or []) for d in held}
    for i,d in enumerate(held,1):
        diag={'claimId':f'c{i}','game':d['game'],'searchResults':0,'invalidOrUnsupportedUrls':0,'duplicateUrls':0,'sameSourceSiteUrls':0,'blockedOrUnsafeUrls':0,'eligibleIndependentUrls':0,'directFetches':0,'fetchErrors':0,'targetMissing':0,'candidatePages':0}
        query=f'"{d["game"]}" {d["claim"]}'
        search_calls+=1
        try: res=searcher(query,tavily_key,max_results)
        except Exception as e:
            diag['searchError']=collector.safe_error(e); funnel['searchErrors']+=1; diagnostics.append(diag); continue
        if not isinstance(res,dict) or not isinstance(res.get('results') or [],list):
            diag['searchMalformed']=True; funnel['malformedSearchResponses']+=1; diagnostics.append(diag); continue
        items=(res.get('results') or [])[:max_results]; diag['searchResults']=len(items); funnel['searchResults']+=len(items)
        oldsites=existing_sites_by_claim[(d['game'],d['category'],gate.text_key(d['claim']))]
        for item in items:
            if fetch_calls>=max_fetches: break
            if not isinstance(item,dict):
                funnel['malformedSearchItems']+=1; continue
            url=collector.canonical_url(str((item or {}).get('url') or ''))
            site=gate.source_site(url)
            if not url or not site:
                diag['invalidOrUnsupportedUrls']+=1; funnel['invalidOrUnsupportedUrls']+=1; continue
            if url in seen_urls:
                diag['duplicateUrls']+=1; funnel['duplicateUrls']+=1; continue
            if site in oldsites:
                diag['sameSourceSiteUrls']+=1; funnel['sameSourceSiteUrls']+=1; continue
            if collector.blocked_url(url,cfg.get('blockedDomains') or []):
                diag['blockedOrUnsafeUrls']+=1; funnel['blockedOrUnsafeUrls']+=1; continue
            seen_urls.add(url); diag['eligibleIndependentUrls']+=1; funnel['eligibleIndependentUrls']+=1; fetch_calls+=1; diag['directFetches']+=1
            try: raw,_=fetcher(url); text=collector.visible_text(raw)
            except Exception:
                diag['fetchErrors']+=1; funnel['fetchErrors']+=1; continue
            if not collector.target_in_text(text,[d['game']]):
                diag['targetMissing']+=1; funnel['targetMissing']+=1; continue
            candidates.append({'claimId':f'c{i}','game':d['game'],'category':d['category'],'claim':d['claim'],'sourceId':f'u{len(candidates)+1}','url':url,'site':site,'sourceType':collector.source_type(url,d['game'],cfg),'text':text})
            diag['candidatePages']+=1; funnel['candidatePages']+=1
        diagnostics.append(diag)
    matches=[]; rejected={}; appended=[]; contradictions=[]
    by_game={}
    for c in candidates: by_game.setdefault(c['game'],[]).append(c)
    held_by_game={}
    for i,d in enumerate(held,1):
        held_by_game.setdefault(d['game'],[]).append((f'c{i}',d))
    for game,rows in sorted(by_game.items()):
        held_map={cid:{'claimId':cid,'category':d['category'],'claim':d['claim'],'existingSites':sorted(existing_sites_by_claim.get((d['game'],d['category'],gate.text_key(d['claim'])),set()))} for cid,d in held_by_game.get(game,[])}
        sources={c['sourceId']:c for c in rows}; claim_by_id={k:v for k,v in held_map.items()}
        evidence_spans,pairs_considered,pair_count,no_lexical=build_evidence_spans(held_map,list(sources.values()))
        span_by_id={x['spanId']:x for x in evidence_spans}
        funnel['sourceClaimPairsConsidered']+=pairs_considered; funnel['sourceClaimPairs']+=pair_count
        funnel['sourceClaimPairsNoLexicalSpan']+=no_lexical; funnel['evidenceSpans']+=len(evidence_spans)
        eligible_source_ids={x['sourceId'] for x in evidence_spans}
        funnel['sourcesWithoutEligibleSpans']+=max(0,len(sources)-len(eligible_source_ids))
        if not evidence_spans:
            continue
        try:
            api_calls+=1; response=ai(gemini_key,os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite'),build_prompt(game,list(held_map.values()),evidence_spans))
        except Exception as e:
            funnel['aiErrors']+=1; diagnostics.append({'game':game,'aiError':collector.safe_error(e)}); continue
        if not isinstance(response,dict) or not isinstance(response.get('matches'),list):
            funnel['aiMalformedResponses']+=1; proposed=[]
        else:
            all_proposed=response.get('matches') or []
            proposed=all_proposed[:80]
            funnel['aiProposalsDropped']+=max(0,len(all_proposed)-len(proposed))
        funnel['aiProposedMatches']+=len(proposed)
        referenced_sources=set(); validated_candidates=[]
        for raw in proposed:
            if isinstance(raw,dict) and norm(raw.get('sourceId')) in sources: referenced_sources.add(norm(raw.get('sourceId')))
            match,reason=validate_match(raw,claim_by_id,sources,span_by_id)
            if reason:
                rejected[reason]=rejected.get(reason,0)+1; funnel['aiRejectedMatches']+=1; continue
            validated_candidates.append(match)
        grouped={}
        for match in validated_candidates:
            grouped.setdefault((match['claimId'],match['sourceId']),[]).append(match)
        for pair,group in sorted(grouped.items()):
            relations={x['relation'] for x in group}
            if len(relations)>1:
                rejected['ambiguous_pair_relations']=rejected.get('ambiguous_pair_relations',0)+len(group)
                funnel['aiRejectedMatches']+=len(group); continue
            group=sorted(group,key=lambda x:x['spanId'])
            match=group[0]
            if len(group)>1:
                rejected['duplicate_ai_match']=rejected.get('duplicate_ai_match',0)+(len(group)-1)
                funnel['aiRejectedMatches']+=len(group)-1
            matches.append(match); src=sources[match['sourceId']]; claim=claim_by_id[match['claimId']]
            if match['relation']=='support':
                funnel['aiValidatedSupport']+=1
                appended.append({'game':game,'category':claim['category'],'claim':claim['claim'],'evidenceQuote':match['evidenceQuote'],'sourceId':'v52:'+match['sourceId'],'url':src['url'],'sourceType':src['sourceType'],'status':'validated_quarantine'})
            elif match['relation']=='contradict':
                funnel['aiValidatedContradict']+=1
                contradictions.append({'game':game,'category':claim['category'],'claim':claim['claim'],'url':src['url'],'evidenceQuote':match['evidenceQuote'],'status':'quarantined_contradiction'})
            else:
                funnel['aiValidatedUnclear']+=1
        funnel['candidatePagesUnreferencedByAI']+=max(0,len(eligible_source_ids)-(len(referenced_sources & eligible_source_ids)))
    unique={(x['game'],x['category'],gate.text_key(x['claim']),x['url']):x for x in base+appended}
    merged=[unique[k] for k in sorted(unique)]
    report={'phase':'PHASE4_GUIDE_CORROBORATION_V52','logicVersion':LOGIC_VERSION,'generatedAt':now_iso(),'totalHeldClaims':total_held,'eligibleHeldClaims':eligible_held,'inputHeldClaims':len(held),'inputClaims':len(base),'outputClaims':len(merged),'searchCalls':search_calls,'directFetches':fetch_calls,'apiCalls':api_calls,'candidatePages':len(candidates),'validatedMatches':len(matches),'supportingClaimsAdded':len(appended),'contradictionsFound':len(contradictions),'rejected':rejected,'diagnosticCounts':funnel,'publicationWrites':0,'diagnostics':diagnostics,'contradictions':contradictions}
    return {'phase':'PHASE4_GUIDE_CLAIMS_CORROBORATED_V52','generatedAt':report['generatedAt'],'publicationWrites':0,'claims':merged},report

def main():
    try:
        merged,report=run(); OUT.write_text(json.dumps(merged,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        status={k:report[k] for k in ['phase','logicVersion','totalHeldClaims','eligibleHeldClaims','inputHeldClaims','inputClaims','outputClaims','searchCalls','directFetches','apiCalls','candidatePages','validatedMatches','supportingClaimsAdded','contradictionsFound','publicationWrites']}; status['diagnosticCounts']=report['diagnosticCounts']; status['rejected']=report['rejected']; status.update({'success':True,'lastRun':report['generatedAt']}); STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(status,ensure_ascii=False))
    except Exception as e:
        status={'phase':'PHASE4_GUIDE_CORROBORATION_V52','success':False,'error':collector.safe_error(e),'publicationWrites':0,'lastRun':now_iso()}; STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(status,ensure_ascii=False)); raise
if __name__=='__main__': main()
