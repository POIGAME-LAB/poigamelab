#!/usr/bin/env python3
"""PHASE 4 V50: extract evidence-bound guide claims into quarantine.

Gemini may propose claims, but Python only accepts a claim when its sourceId is
known and its evidenceQuote is literally present in the directly re-fetched
page. Nothing here writes public game/site data.
"""
from __future__ import annotations
import json, os, re, sys, unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import collect_guide_evidence as collector

EVIDENCE=ROOT/'data'/'guide_evidence.json'
OUT=ROOT/'data'/'guide_claims.json'
STATUS=ROOT/'data'/'guide_claim_status.json'
ALLOWED={'requirement','timeline','priority','resource','warning','mechanic','tip'}

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

def live_gemini(key, model, prompt):
    from urllib.request import Request, urlopen
    payload=json.dumps({'model':model,'input':prompt,'store':False}).encode()
    req=Request('https://generativelanguage.googleapis.com/v1beta/interactions',data=payload,
      headers={'Content-Type':'application/json','User-Agent':'POIGAME-LAB/1.0','x-goog-api-key':key})
    with urlopen(req,timeout=180) as r: res=json.loads(r.read().decode('utf-8',errors='replace'))
    return parse_json_text(extract_interaction_text(res))

def build_prompt(game,sources):
    compact=[{'sourceId':s['sourceId'],'sourceType':s['sourceType'],'text':s['text'][:24000]} for s in sources]
    return f'''POIGAME LABの攻略情報抽出。対象ゲーム: {game}\n
与えた本文だけから攻略上の主張を抽出する。推測・一般知識・検索スニペットは禁止。\n
各claimは sourceId と、そのページ本文に実在する短い evidenceQuote（原文）を必須にする。\n
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
    return {'game':src['game'],'category':cat,'claim':claim,'evidenceQuote':quote,'sourceId':sid,
      'url':src['url'],'sourceType':src['sourceType'],'status':'validated_quarantine'},None

def run(evidence_doc=None, api_key=None, fetcher=collector.direct_fetch, ai=live_gemini, model=None):
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
        sources=[]; fetch_errors=0
        for i,row in enumerate(by_game[game][:8],1):
            try:
                raw,_=fetcher(row['url']); text=collector.visible_text(raw)
            except Exception:
                fetch_errors+=1; continue
            if not collector.target_in_text(text,[game]): continue
            sources.append({'sourceId':f's{i}','game':game,'url':row['url'],'sourceType':row.get('sourceType','community_guide'),'text':text})
        diag={'game':game,'inputEvidence':len(by_game[game]),'refetchedSources':len(sources),'fetchErrors':fetch_errors,'aiCalls':0,'proposed':0,'validated':0,'rejected':{}}
        if not sources: diagnostics.append(diag); continue
        try:
            api_calls+=1; diag['aiCalls']=1
            response=ai(api_key,model or os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite'),build_prompt(game,sources))
        except Exception as e:
            diag['aiError']=safe_error(e); diagnostics.append(diag); continue
        proposed=response.get('claims') if isinstance(response,dict) else []
        if not isinstance(proposed,list): proposed=[]
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

def main():
    try:
        result=run(); OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        status={'phase':result['phase'],'success':True,'claimCount':len(result['claims']),'apiCalls':result['apiCalls'],'publicationWrites':0,'lastRun':result['generatedAt']}
        STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(status,ensure_ascii=False))
    except Exception as e:
        status={'phase':'PHASE4_GUIDE_CLAIMS_V50','success':False,'error':safe_error(e),'publicationWrites':0,'lastRun':now_iso()}
        STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(status,ensure_ascii=False)); raise
if __name__=='__main__': main()
