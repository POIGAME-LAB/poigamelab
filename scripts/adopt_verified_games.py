#!/usr/bin/env python3
"""PHASE 3 V30: deterministically adopt V29-approved games into production data.

No API calls. Only `adoption_ready` games are eligible. The script re-validates the
quarantined research result with the V29 strict gate before changing production files.
It is idempotent and rolls back all touched files if any write fails.
"""
from __future__ import annotations
import csv, io, json, os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from evaluate_research_adoption import evaluate, offer_is_strict
from publish_verified_offers import build_outputs, FIELDS

ROOT=Path(__file__).resolve().parents[1]
ADOPTIONS=ROOT/'data/adoption_candidates.json'
RESULTS=ROOT/'data/research_results'
GAMES=ROOT/'games.csv'
TARGETS=ROOT/'config/game_targets.json'
REFRESH=ROOT/'config/refresh_policy.json'
PUBLISHED=ROOT/'data/published_offers.csv'
STATUS=ROOT/'data/adoption_status.json'
TREND_CONFIG=ROOT/'config/trend_discovery.json'
GAME_FIELDS=['name','image','condition','days','difficulty','overview','tips','featured','addedDate']

def now_iso(): return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
def load_json(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def norm(s): return ''.join(str(s or '').casefold().split())
def atomic_text(path,text):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(text,encoding='utf-8'); os.replace(tmp,path)
def json_text(obj): return json.dumps(obj,ensure_ascii=False,indent=2)+'\n'
def csv_text(fields,rows):
    out=io.StringIO(newline=''); w=csv.DictWriter(out,fieldnames=fields); w.writeheader(); w.writerows(rows); return out.getvalue()
def read_csv(path):
    if not Path(path).exists(): return []
    with Path(path).open(encoding='utf-8',newline='') as f: return list(csv.DictReader(f))
def research_for_game(game,results_dir=RESULTS):
    for p in sorted(Path(results_dir).glob('*.json')) if Path(results_dir).exists() else []:
        try:
            payload=load_json(p)
            if norm(payload.get('game'))==norm(game): return payload
        except Exception: pass
    return None

def prepare(adoptions, results_dir, games_path, targets_path, refresh_path, published_path, cfg):
    game_rows=read_csv(games_path); targets=load_json(targets_path); refresh=load_json(refresh_path)
    pub_rows=read_csv(published_path)
    known={norm(r.get('name')) for r in game_rows}
    target_known={norm(x.get('game')) for x in targets.get('games',[])}
    pub={r.get('offerKey'):r for r in pub_rows if r.get('offerKey')}
    decisions=[]
    today=datetime.now().date().isoformat()
    for item in adoptions.get('items',[]):
        if item.get('status')!='adoption_ready' or item.get('eligible') is not True: continue
        game=(item.get('game') or '').strip(); reasons=[]
        payload=research_for_game(game,results_dir)
        if not game: reasons.append('missing_game')
        if not payload: reasons.append('research_result_missing')
        if payload:
            fresh=evaluate(payload,cfg)
            if not fresh.get('eligible'): reasons.append('v29_revalidation_failed')
        else: fresh={}
        if reasons:
            decisions.append({'game':game,'adopted':False,'reasons':reasons}); continue
        verified=deepcopy((payload.get('collectorResult',{}).get('verified') or {}))
        verified['offers']=[o for o in verified.get('offers',[]) if offer_is_strict(o)]
        result=deepcopy(payload['collectorResult']); result['verified']=verified
        rows,_=build_outputs(result)
        if len(rows) < int(cfg.get('minimumVerifiedOffersForAdoption',2)):
            decisions.append({'game':game,'adopted':False,'reasons':['strict_offer_count_changed']}); continue
        if norm(game) not in known:
            game_rows.append({'name':game,'image':'','condition':'指定条件クリア','days':'調査中','difficulty':'調査中','overview':'','tips':'','featured':'false','addedDate':today}); known.add(norm(game))
        aliases=((payload.get('sourceQueue') or {}).get('aliases') or [game])
        if norm(game) not in target_known:
            targets.setdefault('games',[]).append({'game':game,'aliases':list(dict.fromkeys([game]+aliases))}); target_known.add(norm(game))
        refresh.setdefault('games',{}).setdefault(game,{'enabled':False,'adoptedBy':'V30','reason':'new-game refresh remains disabled until controlled refresh policy is enabled'})
        for row in rows: pub[row['offerKey']]=row
        item['status']='adopted'; item['adoptedAt']=now_iso(); item['publishedOfferCount']=len(rows)
        decisions.append({'game':game,'adopted':True,'publishedOfferCount':len(rows),'refreshEnabled':bool(refresh['games'][game].get('enabled'))})
    return game_rows,targets,refresh,list(pub.values()),decisions

def run(adoptions_path=ADOPTIONS,results_dir=RESULTS,games_path=GAMES,targets_path=TARGETS,refresh_path=REFRESH,published_path=PUBLISHED,status_path=STATUS,config_path=TREND_CONFIG):
    adoptions=load_json(adoptions_path) if Path(adoptions_path).exists() else {'items':[]}
    cfg=load_json(config_path)
    paths=[Path(games_path),Path(targets_path),Path(refresh_path),Path(published_path),Path(adoptions_path)]
    backups={p:(p.read_bytes() if p.exists() else None) for p in paths}
    try:
        game_rows,targets,refresh,pub_rows,decisions=prepare(adoptions,Path(results_dir),Path(games_path),Path(targets_path),Path(refresh_path),Path(published_path),cfg)
        atomic_text(games_path,csv_text(GAME_FIELDS,game_rows))
        atomic_text(targets_path,json_text(targets)); atomic_text(refresh_path,json_text(refresh))
        atomic_text(published_path,csv_text(FIELDS,sorted(pub_rows,key=lambda x:x.get('offerKey',''))))
        atomic_text(adoptions_path,json_text(adoptions))
    except Exception:
        for p,data in backups.items():
            if data is None: p.unlink(missing_ok=True)
            else: p.write_bytes(data)
        raise
    status={'phase':'PHASE3_PRODUCTION_ADOPTION_V30','runAt':now_iso(),'apiCalls':0,'idempotent':True,
            'adopted':sum(1 for x in decisions if x.get('adopted')),'held':sum(1 for x in decisions if not x.get('adopted')),
            'newGamesRefreshEnabled':False,'results':decisions}
    atomic_text(status_path,json_text(status)); return status

def main():
    out=run(); print(json.dumps({'adopted':out['adopted'],'held':out['held']},ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
