#!/usr/bin/env python3
"""PHASE 4 V50: extract evidence-bound guide claims into quarantine.

Gemini may propose claims, but Python only accepts a claim when its sourceId is
known and its evidenceQuote is literally present in the directly re-fetched
page. Nothing here writes public game/site data.

V50.2 adds one bounded retry for transient/format-level Gemini failures and
marks unrecovered extraction failures as workflow failures instead of silently
continuing with an empty claim set. V50.3 adds an atomic-claim contract so one
claim carries one independently corroboratable proposition; obvious mixed
fact+advice or bundled-advice claims fail closed before V51/V52.
"""
from __future__ import annotations
import json, os, re, socket, sys, time, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import collect_guide_evidence as collector

EVIDENCE=ROOT/'data'/'guide_evidence.json'
OUT=ROOT/'data'/'guide_claims.json'
STATUS=ROOT/'data'/'guide_claim_status.json'
ALLOWED={'requirement','timeline','priority','resource','warning','mechanic','tip'}
LOGIC_VERSION='V50.3'
MAX_AI_ATTEMPTS_PER_GAME=2
AI_RETRY_DELAY_SECONDS=1.0
RETRYABLE_HTTP={408,425,429,500,502,503,504}

class GeminiCallError(RuntimeError):
    def __init__(self, kind, retryable, message='Gemini call failed'):
        super().__init__(message)
        self.kind=str(kind or 'unknown_error')
        self.retryable=bool(retryable)

def now_iso(): return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def norm_match(s): return re.sub(r'\s+','',str(s or '')).casefold()
def numeric_tokens(s): return tuple(x.replace(',','') for x in re.findall(r'\d+(?:[.,]\d+)?',unicodedata.normalize('NFKC',str(s or ''))))
def numeric_grounded(claim, quote):
    required=list(numeric_tokens(claim)); found=list(numeric_tokens(quote))
    for value in set(required):
        if found.count(value) < required.count(value): return False
    return True
def safe_error(e): return collector.safe_error(e)

ATOMIC_ADVICE_MARKERS=('おすすめ','推奨','活用','優先','べき','方が良い','ほうが良い')
ATOMIC_FACT_MARKERS=('でき','可能','買える','購入できる','入手できる','獲得できる','拡張できる','解放できる')

def atomicity_reason(claim, category):
    """Reject obvious multi-proposition claims without trying to semantically rewrite them."""
    s=unicodedata.normalize('NFKC',norm(claim))
    if len(s)>120: return 'non_atomic_too_long'
    if category in {'tip','priority'}:
        fact_pos=min((s.find(x) for x in ATOMIC_FACT_MARKERS if x in s),default=-1)
        advice_pos=min((s.find(x) for x in ATOMIC_ADVICE_MARKERS if x in s),default=-1)
        if fact_pos>=0 and advice_pos>fact_pos:
            return 'non_atomic_fact_plus_advice'
        if re.search(r'(?:＆|\+|＋)',s) and any(x in s for x in ATOMIC_ADVICE_MARKERS):
            return 'non_atomic_bundled_advice'
        if re.search(r'.{2,24}(?:と|や).{2,24}(?:を|が).{0,24}(?:中心|おすすめ|推奨|優先)',s):
            return 'non_atomic_bundled_advice'
        if re.search(r'.{2,30}(?:ず|ない).{1,30}(?:も|かつ).{2,30}(?:ない|ず).{0,24}(?:方が良い|ほうが良い|おすすめ|推奨)',s):
            return 'non_atomic_bundled_advice'
    return None

def extract_interaction_text(res):
    out=[]
    for step in res.get('steps',[]):
        if step.get('type')=='model_output':
            for item in step.get('content',[]):
                if item.get('type')=='text' and item.get('text'): out.append(item['text'])
    if not out: raise RuntimeError('Gemini returned no text')
    return '\n'.join(out)

def parse_json_text(text):
    text=str(text).strip()
    text=re.sub(r'^```(?:json)?\s*','',text,flags=re.I); text=re.sub(r'\s*```$','',text)
    try: return json.loads(text)
    except json.JSONDecodeError:
        m=re.search(r'\{.*\}',text,re.S)
        if not m: raise RuntimeError('Gemini response did not contain JSON')
        return json.loads(m.group(0))

def classify_ai_exception(exc):
    if isinstance(exc,GeminiCallError): return exc.kind,exc.retryable
    if isinstance(exc,HTTPError):
        code=int(getattr(exc,'code',0) or 0)
        if code in RETRYABLE_HTTP or 500 <= code <= 599:
            return ('rate_limited' if code==429 else ('timeout_http' if code==408 else 'upstream_http')),True
        return ('auth_http' if code in {401,403} else 'request_http'),False
    if isinstance(exc,(TimeoutError,socket.timeout,ConnectionError,URLError)): return 'network_error',True
    return 'unknown_error',False

def live_gemini(key, model, prompt):
    payload=json.dumps({'model':model,'input':prompt,'store':False}).encode()
    req=Request('https://generativelanguage.googleapis.com/v1beta/interactions',data=payload,
      headers={'Content-Type':'application/json','User-Agent':'POIGAME-LAB/1.0','x-goog-api-key':key})
    try:
        with urlopen(req,timeout=180) as r: raw=r.read().decode('utf-8',errors='replace')
    except HTTPError as e:
        code=int(getattr(e,'code',0) or 0)
        if code in RETRYABLE_HTTP or 500 <= code <= 599:
            kind='rate_limited' if code==429 else ('timeout_http' if code==408 else 'upstream_http')
            raise GeminiCallError(kind,True,f'Gemini HTTP {code}') from e
        kind='auth_http' if code in {401,403} else 'request_http'
        raise GeminiCallError(kind,False,f'Gemini HTTP {code}') from e
    except (TimeoutError,socket.timeout,URLError,ConnectionError) as e:
        raise GeminiCallError('network_error',True,'Gemini network failure') from e
    try:
        res=json.loads(raw)
        return parse_json_text(extract_interaction_text(res))
    except (json.JSONDecodeError,RuntimeError,TypeError,ValueError,AttributeError) as e:
        raise GeminiCallError('response_format',True,'Gemini response format failure') from e

def build_prompt(game,sources):
    compact=[{'sourceId':s['sourceId'],'sourceType':s['sourceType'],'text':s['text'][:24000]} for s in sources]
    return f'''POIGAME LABの攻略情報抽出。対象ゲーム: {game}\n
与えた本文だけから攻略上の主張を抽出する。推測・一般知識・検索スニペットは禁止。\n
各claimは sourceId と、そのページ本文に実在する短い evidenceQuote（原文）を必須にする。\n
1 claim = 1つの独立して裏取りできる主張にする。事実・仕様と、おすすめ/優先/活用などの助言を1文に混ぜない。\n
例: 「市場では商品をコインで買えるので不足時に活用がおすすめ」は、必要なら「市場では商品をコインで買える」(mechanic/resource) と「不足時に市場を活用するのがおすすめ」(tip) に分ける。同じevidenceQuoteを複数claimで使ってよい。\n
複数の行動を「AとBが攻略の中心」のように束ねた主張は避け、本文が個別に根拠を述べている場合だけ個別claimを作る。本文が個別には言っていないなら無理に分割・一般化せず、その主張を出さない。\n
categoryは requirement,timeline,priority,resource,warning,mechanic,tip のいずれか。\n
数字・日数・レベル・金額をclaimに含める場合、その数字をevidenceQuoteにも必ず含める。\n
別ゲームの情報は出さない。JSON以外禁止。\n
形式: {{"claims":[{{"sourceId":"s1","category":"tip","claim":"","evidenceQuote":""}}]}}\n
sources:\n'''+json.dumps(compact,ensure_ascii=False)

def validate_claim(raw, source_by_id):
    if not isinstance(raw,dict): return None,'malformed'
    sid=norm(raw.get('sourceId')); cat=norm(raw.get('category')); claim=norm(raw.get('claim')); quote=norm(raw.get('evidenceQuote'))
    if sid not in source_by_id: return None,'unknown_source'
    if cat not in ALLOWED: return None,'invalid_category'
    if len(claim)<4 or len(quote)<4: return None,'missing_text'
    src=source_by_id[sid]
    if norm_match(quote) not in norm_match(src['text']): return None,'quote_not_in_source'
    if not numeric_grounded(claim,quote): return None,'numeric_not_grounded'
    atomic_reason=atomicity_reason(claim,cat)
    if atomic_reason: return None,atomic_reason
    return {'game':src['game'],'category':cat,'claim':claim,'evidenceQuote':quote,'sourceId':sid,
      'url':src['url'],'sourceType':src['sourceType'],'status':'validated_quarantine'},None

def run(evidence_doc=None, api_key=None, fetcher=collector.direct_fetch, ai=live_gemini, model=None,
        sleeper=time.sleep, retry_delay=AI_RETRY_DELAY_SECONDS):
    evidence_doc=evidence_doc or json.loads(EVIDENCE.read_text(encoding='utf-8'))
    api_key=api_key if api_key is not None else os.getenv('GEMINI_API_KEY','')
    if not api_key: raise RuntimeError('GEMINI_API_KEY unavailable')
    rows=evidence_doc.get('evidence') or []
    by_game={}
    for row in rows:
        if row.get('status')!='quarantined' or not row.get('targetConfirmed'): continue
        by_game.setdefault(row.get('game',''),[]).append(row)
    all_claims=[]; diagnostics=[]; api_calls=0
    for game in sorted(k for k in by_game if k):
        sources=[]; fetch_errors=0; target_missing=0
        for i,row in enumerate(by_game[game][:8],1):
            try:
                raw,_=fetcher(row['url']); text=collector.visible_text(raw)
            except Exception:
                fetch_errors+=1; continue
            if not collector.target_in_text(text,[game]):
                target_missing+=1
                continue
            sources.append({'sourceId':f's{i}','game':game,'url':row['url'],'sourceType':row.get('sourceType','community_guide'),'text':text})
        diag={'game':game,'inputEvidence':len(by_game[game]),'refetchedSources':len(sources),'fetchErrors':fetch_errors,'targetMissing':target_missing,
              'aiCalls':0,'aiAttempts':0,'aiRetries':0,'aiTransientFailures':0,'aiRecoveredAfterRetry':0,'proposed':0,'validated':0,
              'rejected':{},'malformedClaimsPayload':0,'retryKinds':{}}
        if not sources: diagnostics.append(diag); continue
        prompt=build_prompt(game,sources)
        response=None
        for attempt in range(1,MAX_AI_ATTEMPTS_PER_GAME+1):
            api_calls+=1; diag['aiCalls']=1; diag['aiAttempts']+=1
            try:
                candidate=ai(api_key,model or os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite'),prompt)
                proposed=candidate.get('claims') if isinstance(candidate,dict) else None
                if not isinstance(proposed,list):
                    diag['malformedClaimsPayload']+=1
                    raise GeminiCallError('malformed_claims_payload',True,'Gemini claims payload malformed')
                response=candidate
                if attempt>1: diag['aiRecoveredAfterRetry']=1
                break
            except Exception as e:
                kind,retryable=classify_ai_exception(e)
                if retryable:
                    diag['aiTransientFailures']+=1
                if retryable and attempt < MAX_AI_ATTEMPTS_PER_GAME:
                    diag['aiRetries']+=1
                    diag['retryKinds'][kind]=diag['retryKinds'].get(kind,0)+1
                    if retry_delay and sleeper: sleeper(retry_delay)
                    continue
                diag['aiError']=safe_error(e); diag['aiErrorKind']=kind
                break
        if response is None:
            diagnostics.append(diag); continue
        proposed=response.get('claims') or []
        diag['proposed']=len(proposed); source_by_id={s['sourceId']:s for s in sources}; seen=set()
        for raw in proposed[:80]:
            claim,reason=validate_claim(raw,source_by_id)
            if reason:
                diag['rejected'][reason]=diag['rejected'].get(reason,0)+1; continue
            key=(claim['game'],claim['category'],norm_match(claim['claim']),claim['url'])
            if key in seen:
                diag['rejected']['duplicate']=diag['rejected'].get('duplicate',0)+1; continue
            seen.add(key); all_claims.append(claim); diag['validated']+=1
        diagnostics.append(diag)
    return {'phase':'PHASE4_GUIDE_CLAIMS_V50','generatedAt':now_iso(),'publicationWrites':0,'apiCalls':api_calls,
      'claims':all_claims,'diagnostics':diagnostics}


def summarize_result(result):
    diagnostics=result.get('diagnostics') or []
    rejected={}; retry_kinds={}
    totals={
      'games':len(diagnostics),'inputEvidence':0,'refetchedSources':0,'fetchErrors':0,'targetMissing':0,
      'aiCalls':0,'aiAttempts':0,'aiRetries':0,'aiTransientFailures':0,'aiRecoveredAfterRetry':0,'aiErrors':0,
      'malformedClaimsPayloads':0,'proposed':0,'validated':0
    }
    games=[]
    for d in diagnostics:
        for key in ('inputEvidence','refetchedSources','fetchErrors','targetMissing','aiCalls','aiAttempts','aiRetries','aiTransientFailures','aiRecoveredAfterRetry','malformedClaimsPayload','proposed','validated'):
            target='malformedClaimsPayloads' if key=='malformedClaimsPayload' else key
            totals[target]+=int(d.get(key) or 0)
        totals['aiErrors']+=1 if d.get('aiError') else 0
        for reason,count in (d.get('rejected') or {}).items(): rejected[reason]=rejected.get(reason,0)+int(count or 0)
        for kind,count in (d.get('retryKinds') or {}).items(): retry_kinds[kind]=retry_kinds.get(kind,0)+int(count or 0)
        games.append({k:d.get(k) for k in ('game','inputEvidence','refetchedSources','fetchErrors','targetMissing','aiCalls','aiAttempts','aiRetries','aiTransientFailures','aiRecoveredAfterRetry','proposed','validated','malformedClaimsPayload')})
        if d.get('aiError'):
            games[-1]['aiError']=True
            games[-1]['aiErrorKind']=d.get('aiErrorKind','unknown_error')
    claim_count=len(result.get('claims') or [])
    if claim_count:
        zero_reason=None
    elif totals['refetchedSources']==0:
        zero_reason='no_refetched_sources'
    elif any(g.get('aiErrorKind')=='malformed_claims_payload' for g in games):
        zero_reason='ai_malformed_claims_payload'
    elif totals['aiErrors']:
        zero_reason='ai_error'
    elif totals['malformedClaimsPayloads']:
        zero_reason='ai_malformed_claims_payload'
    elif totals['proposed']==0:
        zero_reason='ai_no_proposals'
    elif totals['validated']==0:
        zero_reason='all_proposals_rejected'
    else:
        zero_reason='unknown_zero_claim_state'
    return {'totals':totals,'rejected':rejected,'retryKinds':retry_kinds,'zeroClaimReason':zero_reason,'games':games}

def extraction_complete(summary):
    totals=summary.get('totals') or {}
    return int(totals.get('aiErrors') or 0)==0

def main():
    try:
        result=run()
    except Exception as e:
        status={'phase':'PHASE4_GUIDE_CLAIMS_V50','logicVersion':LOGIC_VERSION,'success':False,'error':safe_error(e),'publicationWrites':0,'lastRun':now_iso()}
        STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(status,ensure_ascii=False)); raise
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary=summarize_result(result); complete=extraction_complete(summary)
    status={'phase':result['phase'],'logicVersion':LOGIC_VERSION,'success':complete,'claimCount':len(result['claims']),'apiCalls':result['apiCalls'],'publicationWrites':0,'diagnosticSummary':summary,'lastRun':result['generatedAt']}
    STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(status,ensure_ascii=False))
    if not complete:
        raise SystemExit(2)
if __name__=='__main__': main()
