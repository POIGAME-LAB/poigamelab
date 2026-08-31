#!/usr/bin/env python3
"""PHASE 3 V28: run strict offer collection for promoted games in quarantine.

The bridge never adds games to game_targets.json and forces the existing collector/verifier
into POIGAMELAB_PUBLISH_MODE=quarantine. Verified results are stored under
`data/research_results/`; `data/published_offers.csv` is never touched by this stage.
"""
from __future__ import annotations
import hashlib, json, os, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
QUEUE=ROOT/'data/research_queue.json'
STATUS=ROOT/'data/research_bridge_status.json'
RESULTS=ROOT/'data/research_results'

def now_iso(): return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
def load_json(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def atomic_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)
def stable_slug(name):
    import re
    raw=name or 'game'; x=re.sub(r'[^a-z0-9]+','-',raw.lower()).strip('-')
    if x and raw.isascii(): return x
    digest=hashlib.sha256(raw.encode()).hexdigest()[:10]
    return (x+'-' if x else 'game-')+digest

def select_items(queue,max_games=1):
    ready=[x for x in queue.get('items',[]) if x.get('collectorReady') and x.get('status')=='collector_ready']
    return ready[:max(0,int(max_games))]

def run_one(item, runner=subprocess.run, env=None):
    game=item['game']; slug=stable_slug(game); env=dict(env or os.environ)
    env['POIGAMELAB_PUBLISH_MODE']='quarantine'; env.setdefault('FIRECRAWL_CALL_LIMIT','2')
    target={'game':game,'aliases':item.get('aliases') or [game]}
    with tempfile.NamedTemporaryFile('w',suffix='.json',encoding='utf-8',delete=False) as f:
        json.dump(target,f,ensure_ascii=False); target_path=f.name
    try:
        cp=runner([sys.executable,str(ROOT/'scripts/collect_games.py'),'--target-json',target_path],cwd=ROOT,env=env)
    finally:
        Path(target_path).unlink(missing_ok=True)
    result_path=ROOT/'data'/f'{slug}_firecrawl_result.json'
    candidate_path=ROOT/'data'/f'{slug}_firecrawl_candidates.json'
    result=None
    if result_path.exists():
        result=load_json(result_path)
        quarantined={'game':game,'researchedAt':now_iso(),'sourceQueue':item,'collectorResult':result,
                     'quarantine':True,'autoPublish':False}
        RESULTS.mkdir(parents=True,exist_ok=True); atomic_json(RESULTS/f'{slug}.json',quarantined)
    result_path.unlink(missing_ok=True); candidate_path.unlink(missing_ok=True)
    health=(result or {}).get('health') or {}
    return {'game':game,'returncode':cp.returncode,'resultSaved':result is not None,
            'publishableCount':health.get('publishableCount',0),'collectionComplete':health.get('collectionComplete',False),
            'degradedReasons':health.get('degradedReasons') or []}

def run(queue_path=QUEUE,max_games=None,runner=subprocess.run,env=None):
    queue=load_json(queue_path) if Path(queue_path).exists() else {'items':[]}
    limit=int(max_games if max_games is not None else os.getenv('RESEARCH_MAX_GAMES','1'))
    chosen=select_items(queue,limit); results=[]
    for item in chosen: results.append(run_one(item,runner=runner,env=env))
    by_game={x['game']:x for x in results}
    for item in queue.get('items',[]):
        r=by_game.get(item.get('game'))
        if r:
            item['status']='research_complete' if r['returncode']==0 and r['resultSaved'] else 'research_failed'
            item['collectorReady']=False; item['lastResearchAt']=now_iso(); item['researchSummary']=r
    if Path(queue_path)==QUEUE: atomic_json(QUEUE,queue)
    status={'phase':'PHASE3_RESEARCH_BRIDGE_V38','runAt':now_iso(),'maxGames':limit,'selected':len(chosen),
            'results':results,'publicationTouched':False,'success':all(x['returncode']==0 and x['resultSaved'] for x in results)}
    atomic_json(STATUS,status); return status

def main():
    missing=[k for k in ('GEMINI_API_KEY',) if not os.getenv(k,'').strip()]
    if missing:
        atomic_json(STATUS,{'phase':'PHASE3_RESEARCH_BRIDGE_V38','runAt':now_iso(),'success':False,'error':'missing_required_secrets','missingSecretNames':missing,'publicationTouched':False})
        return 2
    out=run(); print(json.dumps({'selected':out['selected'],'success':out['success']},ensure_ascii=False)); return 0 if out['success'] else 1
if __name__=='__main__': raise SystemExit(main())
