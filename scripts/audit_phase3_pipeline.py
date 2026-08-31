#!/usr/bin/env python3
"""V31: API-free fail-closed audit for PHASE 3 production handoff."""
from __future__ import annotations
import csv, json
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
GAMES=ROOT/'games.csv'; TARGETS=ROOT/'config/game_targets.json'; REFRESH=ROOT/'config/refresh_policy.json'
PUBLISHED=ROOT/'data/published_offers.csv'; ADOPTIONS=ROOT/'data/adoption_candidates.json'; STATUS=ROOT/'data/phase3_pipeline_audit.json'

def norm(v): return ''.join(str(v or '').casefold().split())
def load_json(p, default):
    p=Path(p)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
def read_csv(p):
    p=Path(p)
    if not p.exists(): return []
    with p.open(encoding='utf-8',newline='') as f: return list(csv.DictReader(f))
def dupes(values):
    seen=set(); out=set()
    for v in values:
        if not v: continue
        if v in seen: out.add(v)
        seen.add(v)
    return sorted(out)
def audit(games_path=GAMES,targets_path=TARGETS,refresh_path=REFRESH,published_path=PUBLISHED,adoptions_path=ADOPTIONS):
    games=read_csv(games_path); targets=load_json(targets_path,{'games':[]}); refresh=load_json(refresh_path,{'games':{}}); offers=read_csv(published_path); adoptions=load_json(adoptions_path,{'items':[]})
    errors=[]; warnings=[]
    game_names=[norm(x.get('name')) for x in games]; target_names=[norm(x.get('game')) for x in targets.get('games',[])]
    for x in dupes(game_names): errors.append(f'duplicate_game:{x}')
    for x in dupes(target_names): errors.append(f'duplicate_target:{x}')
    for x in dupes([x.get('offerKey') for x in offers]): errors.append(f'duplicate_offer_key:{x}')
    known=set(game_names); target_known=set(target_names)
    for row in offers:
        game=norm(row.get('game'))
        if game and game not in known: errors.append(f'published_game_missing_games_csv:{row.get("game","")}')
        url=(row.get('url') or '').strip(); parsed=urlparse(url)
        if url and (parsed.scheme not in {'http','https'} or not parsed.netloc): errors.append(f'invalid_published_url:{row.get("offerKey","")}')
    adopted=[x for x in adoptions.get('items',[]) if x.get('status')=='adopted']
    for item in adopted:
        game=item.get('game',''); key=norm(game)
        if key not in known: errors.append(f'adopted_missing_games_csv:{game}')
        if key not in target_known: errors.append(f'adopted_missing_game_target:{game}')
        policy=(refresh.get('games') or {}).get(game)
        if not isinstance(policy,dict): errors.append(f'adopted_missing_refresh_policy:{game}')
        elif policy.get('enabled') is not False: errors.append(f'new_game_refresh_not_disabled:{game}')
        count=sum(1 for r in offers if norm(r.get('game'))==key)
        expected=int(item.get('publishedOfferCount') or 0)
        if expected < 1 or count < expected: errors.append(f'adopted_offer_count_mismatch:{game}:{count}/{expected}')
    temp=list(Path(games_path).parent.glob('*.tmp'))
    if temp: warnings.append(f'root_temp_files:{len(temp)}')
    return {'phase':'PHASE3_INTEGRATION_AUDIT_V31','success':not errors,'errors':sorted(set(errors)),'warnings':warnings,
            'counts':{'games':len(games),'targets':len(targets.get('games',[])),'publishedOffers':len(offers),'adoptedGames':len(adopted)},'apiCalls':0}
def write_status(result,path=STATUS):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)
def main():
    result=audit(); write_status(result); print(json.dumps(result,ensure_ascii=False)); return 0 if result['success'] else 1
if __name__=='__main__': raise SystemExit(main())
