#!/usr/bin/env python3
"""Approve one offer candidate and upsert it into offers.csv.
Usage: python scripts/approve_offer.py "Township" coincome 10500 "https://..."
"""
import csv, sys
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if len(sys.argv)<5:
    raise SystemExit('Usage: approve_offer.py GAME SITE REWARD URL')
game,site,reward,url=sys.argv[1:5]
path=ROOT/'offers.csv'
with path.open(encoding='utf-8',newline='') as f:
    rows=list(csv.DictReader(f)); fields=list(rows[0].keys()) if rows else []
for field in ['sourceUrl','verified']:
    if field not in fields: fields.append(field)
updated=False
for r in rows:
    if r.get('game')==game and r.get('site')==site:
        r['reward']=str(int(reward)); r['url']=url; r['sourceUrl']=url; r['verified']='true'; r['updatedAt']=date.today().isoformat(); updated=True
if not updated:
    rows.append({'game':game,'site':site,'provider':'','reward':str(int(reward)),'condition':'指定条件クリア','platform':'iOS|Android','type':'通常','deadline':'','updatedAt':date.today().isoformat(),'url':url,'sourceUrl':url,'verified':'true'})
with path.open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
print('approved:',game,site,reward,url)
