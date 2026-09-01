#!/usr/bin/env python3
"""PHASE 4 V52: bounded independent corroboration for held guide claims.

Only V51 held_single_source claims are searched. Tavily discovers URLs; every
candidate is fetched directly, target-confirmed, and source-site independent.
Python creates bounded exact-source evidence spans; Gemini may only select those
spans. V52.8 keeps V52.7's bounded two-query discovery but allocates the fixed direct-fetch
budget adaptively: every held claim gets an initial fair fetch opportunity, then
remaining fetches backfill claims that still lack a strict direct-text match. Search
metadata only orders URLs; backfill decisions use directly fetched page text. Search
snippets never become evidence, and all existing strict/anchored-paraphrase, numeric,
provenance, AI-budget, and publication gates remain deterministic/fail-closed.
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
LOGIC_VERSION='V52.8'
GENERIC_BIGRAMS={
    '攻略','達成','優先','必要','場合','条件','報酬','日数','効率','序盤','方法','目指','可能',
    'レベ','ベル','ゲー','ーム','する','した','して','ます','でき','ポイ','イン','ント',
}
GENERIC_TERMS={
    '攻略','達成','達成条件','条件','報酬','日数','効率','序盤','方法','目指','目指す','必要','必要条件',
    '優先','優先する','おすすめ','可能','ゲーム','ポイント','レベル','クリア','条件達成',
}
PARTICLE_SPLIT=re.compile(r'(?<=[\u3400-\u9fff\u30a0-\u30ffa-zA-Z0-9])(?:は|を|が|に|へ|で|と|も|や|から|まで|より)(?=[\u3400-\u9fff\u30a0-\u30ffa-zA-Z0-9])')
VERB_SUFFIXES=('してください','しておく','しておき','している','して','した','する','します','できる','なる','れる','られる','です','ます')



def now_iso(): return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def compact(s): return ''.join(ch for ch in unicodedata.normalize('NFKC',str(s or '')).casefold() if ch.isalnum())
def nums(s): return tuple(x.replace(',','') for x in re.findall(r'\d+(?:[.,]\d+)?',unicodedata.normalize('NFKC',str(s or ''))))
def numeric_grounded(claim, quote):
    required=list(nums(claim)); found=list(nums(quote))
    for value in set(required):
        if found.count(value) < required.count(value): return False
    return True

def grams(s,n):
    s=compact(s)
    return {s[i:i+n] for i in range(max(0,len(s)-n+1))}
def bigrams(s): return grams(s,2)
def overlap_ratio(claim,quote):
    a=bigrams(re.sub(r'\d+(?:[.,]\d+)?','',claim)); b=bigrams(re.sub(r'\d+(?:[.,]\d+)?','',quote))
    return (len(a & b)/len(a)) if a else 0.0
def overlap_ok(claim,quote): return overlap_ratio(claim,quote) >= 0.35
def claim_anchor_terms(claim):
    raw=unicodedata.normalize('NFKC',str(claim or '')).casefold()
    raw=re.sub(r'\d+(?:[.,]\d+)?','',raw)
    raw=re.sub(r'[^0-9a-zA-Z\u3040-\u30ff\u3400-\u9fff]+',' ',raw)
    parts=[]
    for block in raw.split():
        parts.extend(x for x in PARTICLE_SPLIT.split(block) if x)
    out=set()
    for part in parts:
        term=compact(part)
        changed=True
        while changed and term:
            changed=False
            for suffix in VERB_SUFFIXES:
                if term.endswith(suffix) and len(term)>len(suffix):
                    term=term[:-len(suffix)]; changed=True; break
        if len(term)<2 or term in GENERIC_TERMS: continue
        out.add(term)
        if len(term)>=3:
            for short in (term[:2],term[-2:]):
                if short not in GENERIC_BIGRAMS: out.add(short)
    return out

def anchor_matches(claim,quote):
    q=compact(re.sub(r'\d+(?:[.,]\d+)?','',quote))
    return {x for x in claim_anchor_terms(claim) if x and x in q}

def anchor_ok(claim,quote):
    # Generic guide vocabulary alone is not enough. At least one deterministic
    # claim-derived content anchor must literally occur in the exact source span.
    return bool(anchor_matches(claim,quote))


def claim_windows(claim_id, source_id, claim, text, window_chars=240, step_chars=120, max_spans=4):
    """Return bounded exact-source windows ranked for corroboration review."""
    text=norm(text)[:18000]
    if not text: return []
    window_chars=max(120,min(480,int(window_chars))); step_chars=max(60,min(window_chars,int(step_chars)))
    starts=list(range(0,max(1,len(text)),step_chars))
    last=max(0,len(text)-window_chars)
    if last not in starts: starts.append(last)
    seen=set(); ranked=[]; required=nums(claim)
    for pos in starts:
        chunk=text[pos:pos+window_chars].strip()
        if len(chunk)<4 or chunk in seen: continue
        seen.add(chunk)
        anchors=len(anchor_matches(claim,chunk))
        if anchors < 1: continue
        lexical=overlap_ratio(claim,chunk)
        trigrams=len(grams(re.sub(r'\d+(?:[.,]\d+)?','',claim),3) & grams(re.sub(r'\d+(?:[.,]\d+)?','',chunk),3))
        same_numbers=1 if required and numeric_grounded(claim,chunk) else 0
        ranked.append((anchors,trigrams,lexical,same_numbers,-pos,chunk))
    ranked.sort(reverse=True)
    out=[]
    for rank,(_,_,_,_,_,chunk) in enumerate(ranked[:max_spans],1):
        out.append({'spanId':f'{source_id}:{claim_id}:s{rank}','claimId':claim_id,'sourceId':source_id,'text':chunk})
    return out


def build_evidence_spans(held_map, sources):
    spans=[]; considered=with_spans=no_anchor=0; strict_pairs=anchor_only_pairs=0
    for source in sources:
        for cid,claim in held_map.items():
            if source['site'] in set(claim.get('existingSites') or []):
                continue
            considered+=1
            pair_spans=claim_windows(cid,source['sourceId'],claim['claim'],source['text'])
            if pair_spans:
                with_spans+=1; spans.extend(pair_spans)
                if any(overlap_ok(claim['claim'],x['text']) for x in pair_spans): strict_pairs+=1
                else: anchor_only_pairs+=1
            else:
                no_anchor+=1
    return spans,considered,with_spans,no_anchor,strict_pairs,anchor_only_pairs


def pair_tasks_from_spans(spans):
    grouped={}
    for row in spans:
        key=(row['claimId'],row['sourceId'])
        grouped.setdefault(key,[]).append(row['spanId'])
    return [
        {'claimId':cid,'sourceId':sid,'allowedSpanIds':sorted(ids)}
        for (cid,sid),ids in sorted(grouped.items())
    ]


def build_prompt(game,held,spans):
    pair_tasks=pair_tasks_from_spans(spans)
    header=f"""POIGAME LAB 裏取り判定。対象ゲーム: {game}

既存claimを、Pythonが直接取得本文から切り出した evidenceSpans だけで裏取りする。一般知識・検索スニペット・推測は禁止。

support は span がclaimと同じ実用上の攻略内容を明確に述べる場合だけ。同じ単語・同じ話題があるだけならunclear。contradict は同じ対象・条件について異なる数字や明確に反対の場合だけ。その他はunclear。

重要: pairTasks に列挙した claimId/sourceId の各組について、必ず1行ずつ判定を返す。省略しない。各組では allowedSpanIds の中から最も判断材料になる spanId を1つだけ選ぶ。証拠文を自分で書き写したり言い換えたりせず、claimId/sourceId/spanId の組み合わせを変更・創作しない。JSON以外禁止。

形式: {{"matches":[{{"claimId":"c1","sourceId":"u1","spanId":"u1:c1:s1","relation":"support|contradict|unclear"}}]}}
heldClaims:
"""
    compact_rows=[{'claimId':x['claimId'],'sourceId':x['sourceId'],'spanId':x['spanId'],'text':x['text']} for x in spans]
    return header+json.dumps(held,ensure_ascii=False)+'\npairTasks:\n'+json.dumps(pair_tasks,ensure_ascii=False)+'\nevidenceSpans:\n'+json.dumps(compact_rows,ensure_ascii=False)


def build_review_prompt(game, claim_by_id, source_by_id, span_by_id, candidates):
    rows=[]
    for x in candidates:
        rows.append({
            'claimId':x['claimId'],'sourceId':x['sourceId'],'spanId':x['spanId'],'relation':x['relation'],
            'claim':claim_by_id[x['claimId']]['claim'],'span':span_by_id[x['spanId']]['text'],
        })
    return f"""POIGAME LAB 裏取りの独立再確認。対象ゲーム: {game}

以下は別の判定工程が候補にしたclaimと、Pythonが直接取得本文から固定したspanの組み合わせ。一般知識・検索スニペット・推測は禁止。
support はspanがclaimと同じ実用上の攻略内容を明確に述べる場合だけ。同じ話題・同じ名詞だけならreject。
contradict は同じ対象・条件について明確に反対、または数値条件が衝突する場合だけ。それ以外はreject。
claimId/sourceId/spanId/relationは変更しない。各候補を confirm または reject のどちらかで返す。JSON以外禁止。

形式: {{"reviews":[{{"claimId":"c1","sourceId":"u1","spanId":"u1:c1:s1","relation":"support","verdict":"confirm|reject"}}]}}
candidates:
"""+json.dumps(rows,ensure_ascii=False)


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
    if not anchor_ok(claim['claim'],quote): return None,'insufficient_distinctive_anchor'
    if rel=='support' and not numeric_grounded(claim['claim'],quote): return None,'numeric_not_grounded'
    return {
        'claimId':cid,'sourceId':sid,'spanId':span_id,'relation':rel,'evidenceQuote':quote,
        'strictLexical':overlap_ok(claim['claim'],quote),
    },None


def distinctive_query_terms(claim):
    """Return deterministic non-generic terms used only for discovery queries/ranking."""
    raw=unicodedata.normalize('NFKC',str(claim or '')).casefold()
    raw=re.sub(r'[^0-9a-zA-Z\u3040-\u30ff\u3400-\u9fff]+',' ',raw)
    parts=[]
    for block in raw.split():
        parts.extend(x for x in PARTICLE_SPLIT.split(block) if x)
    out=[]; seen=set()
    for part in parts:
        term=compact(part)
        if not term or term.isdigit(): continue
        changed=True
        while changed and term:
            changed=False
            for suffix in VERB_SUFFIXES:
                if term.endswith(suffix) and len(term)>len(suffix):
                    term=term[:-len(suffix)]; changed=True; break
        if len(term)<2 or term in GENERIC_TERMS or term in seen: continue
        seen.add(term); out.append(term)
    out.sort(key=lambda x:(-len(x),x))
    return out


def corroboration_queries(game, claim, max_queries=2):
    """Bounded claim-targeted discovery queries. Search metadata is never evidence."""
    max_queries=max(1,min(2,int(max_queries)))
    queries=[f'"{game}" {claim}']
    terms=distinctive_query_terms(claim)
    number_terms=list(dict.fromkeys(nums(claim)))
    focused=[f'"{game}"']
    focused.extend(number_terms[:2])
    for term in terms[:3]:
        focused.append(f'"{term}"' if len(term)>=3 else term)
    if len(focused)>1:
        focused.append('攻略')
        q=' '.join(focused)
        if compact(q)!=compact(queries[0]): queries.append(q)
    return queries[:max_queries]


def discovery_relevance(game, claim, item, rank=0):
    """Rank URL discovery only; title/snippet never becomes factual evidence."""
    if not isinstance(item,dict): return 0,0
    meta=norm(str(item.get('title') or '')+' '+str(item.get('content') or '')+' '+str(item.get('url') or ''))
    cm=compact(meta); score=max(0,3-int(rank)); signals=0
    gm=compact(game)
    if gm and gm in cm: score+=5
    claim_compact=compact(re.sub(r'\d+(?:[.,]\d+)?','',claim))
    if len(claim_compact)>=4 and claim_compact in cm:
        score+=10; signals+=3
    meta_nums=nums(meta)
    for n in set(nums(claim)):
        if n in meta_nums: score+=4; signals+=1
    for term in distinctive_query_terms(claim)[:4]:
        if term in cm: score+=3; signals+=1
    return score,signals



def ranked_discovery_by_claim(pool, held_info):
    """Return deterministic per-claim discovery queues; metadata is ranking-only."""
    per_claim={}
    for cid,d in held_info:
        oldsites=set(d.get('independentSources') or [])
        rows=[]
        for key,row in pool.items():
            if row['game']!=d['game'] or row['site'] in oldsites: continue
            score=(row.get('scores') or {}).get(cid)
            if score is None: continue
            rows.append((score,row['url'],key))
        rows.sort(key=lambda x:(-x[0],x[1]))
        per_claim[cid]=rows
    return per_claim


def direct_text_match_kind(claim, text):
    """Probe fetched text only. Returns strict, anchor, or none without using search metadata."""
    spans=claim_windows('probe','probe',claim,text,max_spans=4)
    if not spans: return 'none'
    if any(overlap_ok(claim,x['text']) for x in spans): return 'strict'
    return 'anchor'

def select_discovery_pool(pool, held_info, max_fetches, per_claim_limit=4):
    """Round-robin ranked discovery so one claim cannot consume the fetch budget."""
    max_fetches=max(1,int(max_fetches)); per_claim_limit=max(1,int(per_claim_limit))
    selected=[]; selected_keys=set(); covered=set(); selected_by_claim={cid:0 for cid,_ in held_info}
    per_claim={}
    for cid,d in held_info:
        rows=[]
        oldsites=set(d.get('independentSources') or [])
        for key,row in pool.items():
            if row['game']!=d['game'] or row['site'] in oldsites: continue
            score=(row.get('scores') or {}).get(cid)
            if score is None: continue
            rows.append((score,row['url'],key))
        rows.sort(key=lambda x:(-x[0],x[1]))
        per_claim[cid]=rows
    offsets={cid:0 for cid,_ in held_info}
    while len(selected)<max_fetches:
        advanced=False
        for cid,_ in held_info:
            if selected_by_claim[cid]>=per_claim_limit: continue
            rows=per_claim.get(cid) or []; idx=offsets[cid]
            while idx<len(rows) and rows[idx][2] in selected_keys: idx+=1
            offsets[cid]=idx
            if idx>=len(rows): continue
            key=rows[idx][2]; offsets[cid]=idx+1
            if key in selected_keys: continue
            selected.append(pool[key]); selected_keys.add(key); covered.add(cid); selected_by_claim[cid]+=1; advanced=True
            if len(selected)>=max_fetches: break
        if not advanced: break
    return selected,covered


def apply_semantic_review(response, candidates):
    expected={(x['claimId'],x['sourceId'],x['spanId'],x['relation']):x for x in candidates}
    if not isinstance(response,dict) or not isinstance(response.get('reviews'),list):
        return [],{'semantic_review_malformed':len(candidates)}
    verdicts={}; rejected={}
    for raw in (response.get('reviews') or [])[:80]:
        if not isinstance(raw,dict):
            rejected['semantic_review_malformed_item']=rejected.get('semantic_review_malformed_item',0)+1; continue
        key=(norm(raw.get('claimId')),norm(raw.get('sourceId')),norm(raw.get('spanId')),norm(raw.get('relation')))
        verdict=norm(raw.get('verdict'))
        if key not in expected:
            rejected['semantic_review_unknown_reference']=rejected.get('semantic_review_unknown_reference',0)+1; continue
        if verdict not in {'confirm','reject'}:
            rejected['semantic_review_invalid_verdict']=rejected.get('semantic_review_invalid_verdict',0)+1; continue
        verdicts.setdefault(key,[]).append(verdict)
    confirmed=[]
    for key,row in expected.items():
        vals=verdicts.get(key) or []
        if len(vals)>1:
            rejected['semantic_review_duplicate']=rejected.get('semantic_review_duplicate',0)+(len(vals)-1)
            rejected['semantic_review_rejected_or_missing']=rejected.get('semantic_review_rejected_or_missing',0)+1
        elif vals==['confirm']:
            confirmed.append(row)
        else:
            rejected['semantic_review_rejected_or_missing']=rejected.get('semantic_review_rejected_or_missing',0)+1
    return confirmed,rejected


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
    held=held[:max_claims]; search_calls=fetch_calls=api_calls=0; candidates=[]; diagnostics=[]
    max_queries_per_claim=max(1,min(2,int(cfg.get('maxCorroborationSearchesPerClaim',1))))
    max_search_calls=max(1,min(8,int(cfg.get('maxCorroborationSearchCallsPerRun',max_claims*max_queries_per_claim))))
    funnel={
        'orphanHeldDecisions':orphan_held,'searchErrors':0,'malformedSearchResponses':0,'malformedSearchItems':0,
        'searchResults':0,'invalidOrUnsupportedUrls':0,'duplicateUrls':0,
        'sameSourceSiteUrls':0,'sameSourceRetainedForOtherClaim':0,'blockedOrUnsafeUrls':0,'eligibleIndependentUrls':0,
        'searchQueriesPlanned':0,'searchQueriesExecuted':0,'searchQueryVariantsUsed':0,
        'discoveryUrlsUnique':0,'discoverySelectedForFetch':0,'discoveryBalancedClaimsCovered':0,
        'discoveryInitialFetches':0,'discoveryBackfillFetches':0,'backfillClaimsTargeted':0,
        'backfillStrictGains':0,'backfillAnchorGains':0,'directTextStrictClaimHits':0,
        'directTextAnchorOnlyClaimHits':0,'directTextNoSpanClaimHits':0,'discoveryAllStrictReachedBeforeBudget':0,
        'fetchErrors':0,'targetMissing':0,'candidatePages':0,'aiErrors':0,'aiMalformedResponses':0,
        'aiProposedMatches':0,'aiProposalsDropped':0,'aiRejectedMatches':0,'aiValidatedSupport':0,
        'aiValidatedContradict':0,'aiValidatedUnclear':0,'candidatePagesUnreferencedByAI':0,
        'sourceClaimPairsConsidered':0,'sourceClaimPairs':0,'sourceClaimPairsNoLexicalSpan':0,
        'sourceClaimPairsStrictLexical':0,'sourceClaimPairsAnchorOnly':0,'evidenceSpans':0,'sourcesWithoutEligibleSpans':0,
        'semanticReviewCalls':0,'semanticReviewErrors':0,'semanticReviewMalformedResponses':0,
        'semanticReviewCandidates':0,'semanticReviewConfirmed':0,'semanticReviewRejected':0,
        'classificationCalls':0,'classificationClaims':0,'pairTasksExpected':0,'pairTasksReturned':0,
        'pairTasksMissing':0,'pairTasksDuplicateRows':0,'aiCallBudget':max(2,min(8,int(cfg.get('maxCorroborationAiCallsPerRun',8)))),
        'aiBudgetExhaustedPairs':0,
    }
    held_info=[(f'c{i}',d) for i,d in enumerate(held,1)]
    existing_sites_by_claim={(d['game'],d['category'],gate.text_key(d['claim'])):set(d.get('independentSources') or []) for d in held}
    diag_by_claim={cid:{'claimId':cid,'game':d['game'],'searchQueries':0,'searchResults':0,'invalidOrUnsupportedUrls':0,'duplicateUrls':0,'sameSourceSiteUrls':0,'blockedOrUnsafeUrls':0,'eligibleIndependentUrls':0,'directFetches':0,'fetchErrors':0,'targetMissing':0,'candidatePages':0} for cid,d in held_info}
    discovery_pool={}
    query_plan={cid:corroboration_queries(d['game'],d['claim'],max_queries_per_claim) for cid,d in held_info}
    funnel['searchQueriesPlanned']=sum(len(v) for v in query_plan.values())
    for qidx in range(max_queries_per_claim):
        if search_calls>=max_search_calls: break
        for cid,d in held_info:
            queries=query_plan.get(cid) or []
            if qidx>=len(queries): continue
            if search_calls>=max_search_calls: break
            query=queries[qidx]
            search_calls+=1; funnel['searchQueriesExecuted']+=1; diag_by_claim[cid]['searchQueries']+=1
            if qidx>0: funnel['searchQueryVariantsUsed']+=1
            try: res=searcher(query,tavily_key,max_results)
            except Exception as e:
                diag_by_claim[cid].setdefault('searchErrors',[]).append(collector.safe_error(e)); funnel['searchErrors']+=1; continue
            if not isinstance(res,dict) or not isinstance(res.get('results') or [],list):
                diag_by_claim[cid]['searchMalformed']=True; funnel['malformedSearchResponses']+=1; continue
            items=(res.get('results') or [])[:max_results]; diag_by_claim[cid]['searchResults']+=len(items); funnel['searchResults']+=len(items)
            for rank,item in enumerate(items):
                if not isinstance(item,dict):
                    funnel['malformedSearchItems']+=1; continue
                url=collector.canonical_url(str(item.get('url') or '')); site=gate.source_site(url)
                if not url or not site:
                    diag_by_claim[cid]['invalidOrUnsupportedUrls']+=1; funnel['invalidOrUnsupportedUrls']+=1; continue
                if collector.blocked_url(url,cfg.get('blockedDomains') or []):
                    diag_by_claim[cid]['blockedOrUnsafeUrls']+=1; funnel['blockedOrUnsafeUrls']+=1; continue
                key=(d['game'],url)
                row=discovery_pool.get(key)
                if row is None:
                    row={'game':d['game'],'url':url,'site':site,'scores':{},'signals':{},'originClaims':set()}
                    discovery_pool[key]=row
                else:
                    funnel['duplicateUrls']+=1; diag_by_claim[cid]['duplicateUrls']+=1
                row['originClaims'].add(cid)
                # Rank metadata is discovery-only. Cross-claim ranking requires at least
                # one claim-specific signal so broad snippets cannot redirect evidence.
                for other_cid,other in held_info:
                    if other['game']!=d['game']: continue
                    score,signals=discovery_relevance(other['game'],other['claim'],item,rank)
                    if other_cid==cid or signals>0:
                        row['scores'][other_cid]=max(score,row['scores'].get(other_cid,-1))
                        row['signals'][other_cid]=max(signals,row['signals'].get(other_cid,0))
                oldsites=existing_sites_by_claim[(d['game'],d['category'],gate.text_key(d['claim']))]
                if site in oldsites:
                    diag_by_claim[cid]['sameSourceSiteUrls']+=1; funnel['sameSourceSiteUrls']+=1
    # Remove URLs that cannot be independent for any held claim of the same game.
    for key,row in list(discovery_pool.items()):
        independent_for=[]
        for cid,d in held_info:
            if d['game']!=row['game']: continue
            oldsites=existing_sites_by_claim[(d['game'],d['category'],gate.text_key(d['claim']))]
            if row['site'] not in oldsites: independent_for.append(cid)
        if not independent_for:
            discovery_pool.pop(key,None); continue
        if any(cid not in independent_for for cid in row['originClaims']):
            funnel['sameSourceRetainedForOtherClaim']+=1
        for cid in independent_for:
            if cid in row['scores']: diag_by_claim[cid]['eligibleIndependentUrls']+=1
    funnel['eligibleIndependentUrls']=len(discovery_pool)
    funnel['discoveryUrlsUnique']=len(discovery_pool)

    # V52.8: spend the same fixed fetch budget in two stages. First give each
    # held claim one fair opportunity. Then use directly fetched page text—not
    # search snippets—to backfill only claims that still lack a strict match.
    per_claim=ranked_discovery_by_claim(discovery_pool,held_info)
    offsets={cid:0 for cid,_ in held_info}; selected_by_claim={cid:0 for cid,_ in held_info}
    fetched_keys=set(); covered=set(); backfill_targeted=set()
    quality={cid:{'candidate':0,'anchor':0,'strict':0} for cid,_ in held_info}

    def next_row_for_claim(cid):
        rows=per_claim.get(cid) or []; idx=offsets[cid]
        while idx<len(rows):
            _,_,key=rows[idx]; idx+=1; offsets[cid]=idx
            if key in fetched_keys: continue
            if selected_by_claim[cid]>=max_results: return None,None
            return key,discovery_pool[key]
        offsets[cid]=idx
        return None,None

    def fetch_discovery_row(cid,key,row,stage):
        nonlocal fetch_calls
        if fetch_calls>=max_fetches or key in fetched_keys: return False
        before={k:(v['anchor'],v['strict']) for k,v in quality.items()}
        fetched_keys.add(key); selected_by_claim[cid]+=1; covered.add(cid); fetch_calls+=1
        funnel['discoverySelectedForFetch']+=1
        if stage=='initial': funnel['discoveryInitialFetches']+=1
        else:
            funnel['discoveryBackfillFetches']+=1; backfill_targeted.add(cid)
        diag_by_claim[cid]['directFetches']+=1
        try: raw,_=fetcher(row['url']); text=collector.visible_text(raw)
        except Exception:
            funnel['fetchErrors']+=1; diag_by_claim[cid]['fetchErrors']+=1; return True
        if not collector.target_in_text(text,[row['game']]):
            funnel['targetMissing']+=1; diag_by_claim[cid]['targetMissing']+=1; return True
        candidates.append({'game':row['game'],'sourceId':f'u{len(candidates)+1}','url':row['url'],'site':row['site'],'sourceType':collector.source_type(row['url'],row['game'],cfg),'text':text})
        funnel['candidatePages']+=1; diag_by_claim[cid]['candidatePages']+=1
        for other_cid,other in held_info:
            if other['game']!=row['game']: continue
            oldsites=existing_sites_by_claim[(other['game'],other['category'],gate.text_key(other['claim']))]
            if row['site'] in oldsites: continue
            quality[other_cid]['candidate']=1
            kind=direct_text_match_kind(other['claim'],text)
            if kind!='none': quality[other_cid]['anchor']=1
            if kind=='strict': quality[other_cid]['strict']=1
        if stage=='backfill':
            funnel['backfillStrictGains']+=sum(1 for k,v in quality.items() if not before[k][1] and v['strict'])
            funnel['backfillAnchorGains']+=sum(1 for k,v in quality.items() if not before[k][0] and v['anchor'])
        return True

    # Initial fair round: at most one direct fetch owned by each held claim.
    for cid,_ in held_info:
        if fetch_calls>=max_fetches: break
        key,row=next_row_for_claim(cid)
        if row is not None: fetch_discovery_row(cid,key,row,'initial')

    # Adaptive backfill: choose one claim at a time and recompute after every
    # directly fetched page. This lets a newly found strict page immediately free
    # the next slot for a weaker claim instead of waiting for a full round.
    exhausted=set(); order_index={cid:i for i,(cid,_) in enumerate(held_info)}
    while fetch_calls<max_fetches:
        available=[cid for cid,_ in held_info if cid not in exhausted and selected_by_claim[cid]<max_results]
        if not available: break
        pending=[cid for cid in available if not quality[cid]['strict']]
        if pending:
            def weakness_key(cid):
                q=quality[cid]
                tier=0 if not q['candidate'] else (1 if not q['anchor'] else 2)
                return (tier,selected_by_claim[cid],order_index[cid])
            cid=min(pending,key=weakness_key)
        else:
            funnel['discoveryAllStrictReachedBeforeBudget']=1
            cid=min(available,key=lambda x:(selected_by_claim[x],order_index[x]))
        key,row=next_row_for_claim(cid)
        if row is None:
            exhausted.add(cid); continue
        fetch_discovery_row(cid,key,row,'backfill')

    funnel['discoveryBalancedClaimsCovered']=len(covered)
    funnel['backfillClaimsTargeted']=len(backfill_targeted)
    funnel['directTextStrictClaimHits']=sum(1 for v in quality.values() if v['strict'])
    funnel['directTextAnchorOnlyClaimHits']=sum(1 for v in quality.values() if v['anchor'] and not v['strict'])
    funnel['directTextNoSpanClaimHits']=sum(1 for v in quality.values() if not v['anchor'])
    diagnostics.extend(diag_by_claim[cid] for cid,_ in held_info)
    matches=[]; rejected={}; appended=[]; contradictions=[]
    by_game={}
    for c in candidates: by_game.setdefault(c['game'],[]).append(c)
    held_by_game={}
    for i,d in enumerate(held,1):
        held_by_game.setdefault(d['game'],[]).append((f'c{i}',d))
    for game,rows in sorted(by_game.items()):
        held_map={cid:{'claimId':cid,'category':d['category'],'claim':d['claim'],'existingSites':sorted(existing_sites_by_claim.get((d['game'],d['category'],gate.text_key(d['claim'])),set()))} for cid,d in held_by_game.get(game,[])}
        sources={c['sourceId']:c for c in rows}; claim_by_id={k:v for k,v in held_map.items()}
        evidence_spans,pairs_considered,pair_count,no_anchor,strict_pairs,anchor_only_pairs=build_evidence_spans(held_map,list(sources.values()))
        span_by_id={x['spanId']:x for x in evidence_spans}
        funnel['sourceClaimPairsConsidered']+=pairs_considered; funnel['sourceClaimPairs']+=pair_count
        funnel['sourceClaimPairsNoLexicalSpan']+=no_anchor; funnel['sourceClaimPairsStrictLexical']+=strict_pairs
        funnel['sourceClaimPairsAnchorOnly']+=anchor_only_pairs; funnel['evidenceSpans']+=len(evidence_spans)
        eligible_source_ids={x['sourceId'] for x in evidence_spans}
        funnel['sourcesWithoutEligibleSpans']+=max(0,len(sources)-len(eligible_source_ids))
        if not evidence_spans:
            continue
        referenced_sources=set(); validated_candidates=[]
        spans_by_claim={}
        for span in evidence_spans:
            spans_by_claim.setdefault(span['claimId'],[]).append(span)
        ai_call_budget=funnel['aiCallBudget']
        for cid in sorted(claim_by_id):
            claim_spans=spans_by_claim.get(cid) or []
            if not claim_spans:
                continue
            expected_pairs={(cid,x['sourceId']) for x in claim_spans}
            funnel['classificationClaims']+=1
            funnel['pairTasksExpected']+=len(expected_pairs)
            if api_calls>=ai_call_budget:
                funnel['pairTasksMissing']+=len(expected_pairs)
                funnel['aiBudgetExhaustedPairs']+=len(expected_pairs)
                continue
            try:
                api_calls+=1; funnel['classificationCalls']+=1
                response=ai(gemini_key,os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite'),build_prompt(game,[claim_by_id[cid]],claim_spans))
            except Exception as e:
                funnel['aiErrors']+=1; funnel['pairTasksMissing']+=len(expected_pairs)
                diagnostics.append({'game':game,'claimId':cid,'aiError':collector.safe_error(e)}); continue
            if not isinstance(response,dict) or not isinstance(response.get('matches'),list):
                funnel['aiMalformedResponses']+=1; proposed=[]
            else:
                all_proposed=response.get('matches') or []
                proposed=all_proposed[:80]
                funnel['aiProposalsDropped']+=max(0,len(all_proposed)-len(proposed))
            funnel['aiProposedMatches']+=len(proposed)
            returned_pairs=set(); raw_pair_counts={}
            for raw in proposed:
                if isinstance(raw,dict):
                    raw_cid=norm(raw.get('claimId')); raw_sid=norm(raw.get('sourceId'))
                    pair=(raw_cid,raw_sid)
                    if pair in expected_pairs:
                        referenced_sources.add(raw_sid)
                        returned_pairs.add(pair); raw_pair_counts[pair]=raw_pair_counts.get(pair,0)+1
                    else:
                        rejected['classification_pair_not_requested']=rejected.get('classification_pair_not_requested',0)+1
                        funnel['aiRejectedMatches']+=1; continue
                match,reason=validate_match(raw,claim_by_id,sources,span_by_id)
                if reason:
                    rejected[reason]=rejected.get(reason,0)+1; funnel['aiRejectedMatches']+=1; continue
                validated_candidates.append(match)
            funnel['pairTasksReturned']+=len(returned_pairs)
            funnel['pairTasksMissing']+=len(expected_pairs-returned_pairs)
            funnel['pairTasksDuplicateRows']+=sum(max(0,n-1) for n in raw_pair_counts.values())
        grouped={}
        for match in validated_candidates:
            grouped.setdefault((match['claimId'],match['sourceId']),[]).append(match)
        preliminary=[]
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
            preliminary.append(match)
        actionable=[x for x in preliminary if x['relation'] in {'support','contradict'}]
        unclear=[x for x in preliminary if x['relation']=='unclear']
        # V52.6 keeps V52.5 acceptance rules unchanged. Classification is now
        # claim-scoped and pair-complete, preventing one large prompt from silently
        # leaving most independent source/claim pairs unassessed.
        confirmed=[x for x in actionable if x.get('strictLexical')]
        review_candidates=[x for x in actionable if not x.get('strictLexical')]
        if review_candidates:
            funnel['semanticReviewCandidates']+=len(review_candidates)
            if api_calls>=ai_call_budget:
                funnel['semanticReviewRejected']+=len(review_candidates)
                rejected['semantic_review_budget_exhausted']=rejected.get('semantic_review_budget_exhausted',0)+len(review_candidates)
            else:
                try:
                    api_calls+=1; funnel['semanticReviewCalls']+=1
                    review_response=ai(gemini_key,os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite'),build_review_prompt(game,claim_by_id,sources,span_by_id,review_candidates))
                    reviewed,review_rejected=apply_semantic_review(review_response,review_candidates)
                    if 'semantic_review_malformed' in review_rejected:
                        funnel['semanticReviewMalformedResponses']+=1
                    confirmed.extend(reviewed); funnel['semanticReviewConfirmed']+=len(reviewed)
                    rejected_count=sum(review_rejected.values()); funnel['semanticReviewRejected']+=rejected_count
                    for reason,count in review_rejected.items(): rejected[reason]=rejected.get(reason,0)+count
                except Exception as e:
                    funnel['semanticReviewErrors']+=1; funnel['semanticReviewRejected']+=len(review_candidates)
                    rejected['semantic_review_error']=rejected.get('semantic_review_error',0)+len(review_candidates)
                    diagnostics.append({'game':game,'semanticReviewError':collector.safe_error(e)})
        final_matches=confirmed+unclear
        for match in final_matches:
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
