#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/'config/refresh_policy.json'
TARGETS=ROOT/'config/game_targets.json'
STATUS=ROOT/'data/refresh_status.json'

def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')

def slugify_game(name):
    table={'Township':'township','きのこ伝説':'kinoko-densetsu','メメントモリ':'memento-mori','ワーキングヒーロー':'working-hero'}
    return table.get(name,'')

def main():
    policy=json.loads(POLICY.read_text(encoding='utf-8'))
    target_db=json.loads(TARGETS.read_text(encoding='utf-8'))['games']
    enabled=[x['game'] for x in target_db if (policy.get('games',{}).get(x['game']) or {}).get('enabled') is True]

    missing=[k for k in ('FIRECRAWL_API_KEY','GEMINI_API_KEY') if not os.getenv(k,'').strip()]
    started=now_iso()
    status={'phase':'PHASE2_AUTO_REFRESH_V23','startedAt':started,'enabledGames':enabled,
            'results':[],'success':False}
    if missing:
        status['error']='missing_required_secrets'
        status['missingSecretNames']=missing
        STATUS.parent.mkdir(parents=True,exist_ok=True)
        STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
        print('ERROR: GitHub Secrets / environment に必要なAPIキーがありません。',file=sys.stderr)
        return 2

    env=os.environ.copy()
    env['FIRECRAWL_CALL_LIMIT']=str(policy.get('maxFirecrawlConcurrency',2))
    env['POIGAMELAB_KNOWN_PAGE_WORKERS']=str(policy.get('maxKnownPageConcurrency',2))
    env['POIGAMELAB_KNOWN_CACHE_SECONDS']=str(policy.get('knownOfficialCacheSeconds',1800))

    failed=False
    for game in enabled:
        print(f'\\n### 自動更新: {game}')
        cp=subprocess.run([sys.executable,str(ROOT/'scripts/collect_games.py'),game],
                          cwd=ROOT,env=env)
        item={'game':game,'returncode':cp.returncode}
        result_path=ROOT/'data'/f'{slugify_game(game)}_firecrawl_result.json'
        if result_path.exists():
            try:
                result=json.loads(result_path.read_text(encoding='utf-8'))
                health=result.get('health') or {}
                item['publishableCount']=health.get('publishableCount')
                item['collectionComplete']=health.get('collectionComplete')
                item['degradedReasons']=health.get('degradedReasons') or []
            except Exception as e:
                item['resultReadError']=str(e)
        if cp.returncode != 0:
            failed=True
        status['results'].append(item)

    status['finishedAt']=now_iso()
    status['success']=not failed
    STATUS.parent.mkdir(parents=True,exist_ok=True)
    tmp=STATUS.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(STATUS)

    print('\\n### 自動更新まとめ')
    for x in status['results']:
        mark='OK' if x['returncode']==0 else 'ERROR'
        print(f"  {mark}: {x['game']} / 掲載候補 {x.get('publishableCount','?')}件")
    return 1 if failed else 0

if __name__=='__main__':
    raise SystemExit(main())
