#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/'config/point_sources.json'
TARGETS=ROOT/'config/game_targets.json'

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('game', nargs='?', help='ゲーム名。省略時は全登録ゲーム')
    args=ap.parse_args()
    db=json.loads(TARGETS.read_text(encoding='utf-8'))['games']
    selected=db if not args.game else [x for x in db if x['game']==args.game]
    if not selected:
        print(f'未登録ゲーム: {args.game}',file=sys.stderr); return 2
    original=CFG.read_text(encoding='utf-8')
    base=json.loads(original)
    failures=[]
    try:
        for target in selected:
            cfg=json.loads(original)
            cfg['target']=target
            # Apply only URLs verified for THIS game; never leak one game's offer IDs to another.
            if target['game']!='Township':
                known=target.get('known_urls_by_source') or {}
                for source in cfg['sources']:
                    urls=known.get(source['id']) or []
                    source['known_target_urls']=urls
                    source['prefer_known_pages']=bool(urls)
                    if urls:
                        source['known_pages_sufficient']=len(urls)
                        source['allow_partial_known_fast_path']=source['id'] in (target.get('partial_fast_path_sources') or [])
                    else:
                        source.pop('known_pages_sufficient',None)
                        source.pop('allow_partial_known_fast_path',None)
                    source.pop('search_terms',None)
            CFG.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'\n===== {target["game"]} =====')
            r=subprocess.run([sys.executable,str(ROOT/'scripts/firecrawl_township_probe.py')],cwd=ROOT)
            if r.returncode != 0:
                failures.append({'game':target['game'],'returncode':r.returncode})
                print(f'{target["game"]}: 収集エラー ({r.returncode})',file=sys.stderr)
        return 1 if failures else 0
    finally:
        CFG.write_text(original,encoding='utf-8')

if __name__=='__main__':
    raise SystemExit(main())
