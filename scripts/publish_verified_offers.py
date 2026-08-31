#!/usr/bin/env python3
"""POIGAME LAB Phase 1 publisher.

Reads deterministic verification output and emits:
- data/published_offers.csv: canonical machine-generated verified offers
- data/exception_queue.json: anything not safe to publish

It never edits offers.csv. Human/seed data remains separate until a later
explicit merge policy is approved.
"""
from __future__ import annotations
import csv, json, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_INPUT=ROOT/'data/township_firecrawl_result.json'
PUBLISHED=ROOT/'data/published_offers.csv'
EXCEPTIONS=ROOT/'data/exception_queue.json'
FIELDS=[
    'offerKey','game','site','provider','reward','condition','platform','type',
    'deadline','updatedAt','url','sourceUrl','verified'
]
KEEP_ID_PARAMS={'point_id','s_id','itemid','campaign_id','campaignid','id'}

def safe_identity_url(url:str)->str:
    """Stable public identity, dropping tracking/session parameters."""
    try:
        u=urlparse(url or '')
        params=[(k,v) for k,v in parse_qsl(u.query,keep_blank_values=True)
                if k.lower() in KEEP_ID_PARAMS]
        return urlunparse((u.scheme.lower(),u.netloc.lower(),u.path,'',
                           urlencode(sorted(params)),''))
    except Exception:
        return url or ''

def public_url(url:str)->str:
    # Same policy for published URLs: retain only stable offer selectors.
    return safe_identity_url(url)

def site_key(site:str)->str:
    table={'ワラウ':'warau','ちょびリッチ':'chobirich','COINCOME':'coincome','モッピー':'moppy'}
    return table.get(site, re.sub(r'[^a-z0-9]+','-',(site or '').lower()).strip('-') or 'unknown')

def offer_key(game,site,platform,url):
    identity=public_url(url)
    return '|'.join([game or '',site_key(site),platform or '不明',identity])

def checks_failed(offer):
    checks=offer.get('deterministic_checks') or {}
    return [k for k,v in checks.items() if v is not True]

def build_outputs(result):
    game=((result.get('verified') or {}).get('game') or result.get('game') or 'Township')
    run_at=result.get('runAt') or datetime.now(timezone.utc).isoformat()
    updated=run_at[:10]
    published={}
    exceptions=[]
    for offer in ((result.get('verified') or {}).get('offers') or []):
        url=public_url(offer.get('url') or '')
        key=offer_key(game,offer.get('site') or '',offer.get('platform') or '',url)
        if offer.get('auto_publish_ready') is True:
            row={
              'offerKey':key,'game':game,'site':site_key(offer.get('site') or ''),
              'provider':'','reward':offer.get('reward_yen'),
              'condition':offer.get('condition') or '',
              'platform':offer.get('platform') or '不明','type':'StepUp',
              'deadline':offer.get('deadline') or '','updatedAt':updated,
              'url':url,'sourceUrl':url,'verified':'true'
            }
            # Stable key makes reruns idempotent; later data replaces same offer.
            published[key]=row
        else:
            exceptions.append({
              'offerKey':key,'game':game,'site':site_key(offer.get('site') or ''),
              'platform':offer.get('platform') or '不明',
              'url':url,'reward':offer.get('reward_yen'),
              'condition':offer.get('condition') or '',
              'failedChecks':checks_failed(offer),
              'reason':offer.get('reason') or 'deterministic gate rejected',
              'registeredSource':offer.get('registered_source'),
              'runAt':run_at
            })
    return list(published.values()),exceptions

def write_outputs(rows, exceptions, published=PUBLISHED, exception_path=EXCEPTIONS,
                  replace_game_snapshot=False):
    """Write published data safely.

    Complete collection:
      replace the current game's snapshot, so disappeared offers can be removed.
    Degraded/transient collection:
      merge fresh successes only, preserving previously verified rows.
    """
    published.parent.mkdir(parents=True, exist_ok=True)
    merged = {}
    if published.exists():
        try:
            with published.open(encoding='utf-8', newline='') as f:
                for old in csv.DictReader(f):
                    if old.get('offerKey'):
                        merged[old['offerKey']] = old
        except Exception:
            merged = {}

    current_games = {x.get('game') for x in rows if x.get('game')} | {
        x.get('game') for x in exceptions if x.get('game')
    }

    if replace_game_snapshot and current_games:
        merged = {
            key: old for key, old in merged.items()
            if old.get('game') not in current_games
        }

    for row in rows:
        merged[row['offerKey']] = row

    # Atomic replace prevents a partially-written CSV from becoming site data.
    tmp = published.with_suffix(published.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in sorted(merged.values(), key=lambda x: x['offerKey']):
            w.writerow(row)
    tmp.replace(published)

    existing = []
    if exception_path.exists():
        try:
            existing = (json.loads(exception_path.read_text(encoding='utf-8')).get('exceptions') or [])
        except Exception:
            existing = []

    current_keys = {x.get('offerKey') for x in exceptions}
    if replace_game_snapshot:
        kept = [x for x in existing if x.get('game') not in current_games]
    else:
        # During degraded runs, keep earlier exceptions and only refresh exact keys seen now.
        kept = [x for x in existing if x.get('offerKey') not in current_keys]
    all_exceptions = kept + exceptions

    payload = {
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'count': len(all_exceptions),
        'exceptions': all_exceptions
    }
    etmp = exception_path.with_suffix(exception_path.suffix + '.tmp')
    etmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    etmp.replace(exception_path)


def publish(input_path=DEFAULT_INPUT,published=PUBLISHED,exception_path=EXCEPTIONS):
    result=json.loads(Path(input_path).read_text(encoding='utf-8'))
    rows,exceptions=build_outputs(result)
    complete=bool((result.get('health') or {}).get('collectionComplete', False))
    write_outputs(rows,exceptions,Path(published),Path(exception_path),
                  replace_game_snapshot=complete)
    return rows,exceptions

def main():
    if not DEFAULT_INPUT.exists():
        raise SystemExit(f'入力がありません: {DEFAULT_INPUT}')
    rows,exceptions=publish()
    print('[Publisher] 完了')
    print(f'      掲載データ: {len(rows)}件 -> data/published_offers.csv')
    print(f'      例外キュー: {len(exceptions)}件 -> data/exception_queue.json')
    print('      offers.csv は変更していません')

if __name__=='__main__':
    main()
