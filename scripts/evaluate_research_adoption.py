#!/usr/bin/env python3
"""PHASE 3 V29: API-free final adoption gate for quarantined game research.

Consumes data/research_results/*.json and writes data/adoption_candidates.json.
This stage NEVER edits games.csv, game_targets.json, offers.csv, or published_offers.csv.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/'data/research_results'
OUT=ROOT/'data/adoption_candidates.json'
CONFIG=ROOT/'config/trend_discovery.json'
REQUIRED_CHECKS={
    'registered_domain','first_party_registered_source','url_present','evidence_present',
    'evidence_domains_registered','evidence_same_offer_identity','exact_identity_candidate_present',
    'reward_valid','reward_consistent','condition_present'
}

def now_iso(): return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
def load_json(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def atomic_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)

def offer_is_strict(offer):
    checks=offer.get('deterministic_checks') or {}
    return offer.get('auto_publish_ready') is True and all(checks.get(k) is True for k in REQUIRED_CHECKS)

def evaluate(payload,cfg):
    reasons=[]
    result=payload.get('collectorResult') or {}
    health=result.get('health') or {}
    verified=(result.get('verified') or {}).get('offers') or []
    strict=[o for o in verified if offer_is_strict(o)]
    sources={o.get('registered_source') for o in strict if o.get('registered_source')}
    min_offers=int(cfg.get('minimumVerifiedOffersForAdoption',2))
    min_sources=int(cfg.get('minimumVerifiedSourcesForAdoption',2))
    if payload.get('quarantine') is not True or payload.get('autoPublish') is not False:
        reasons.append('not_quarantined')
    if health.get('collectionComplete') is not True:
        reasons.append('collection_incomplete')
    if health.get('degradedReasons'):
        reasons.append('degraded_collection')
    if len(strict) < min_offers:
        reasons.append('insufficient_strict_offers')
    if len(sources) < min_sources:
        reasons.append('insufficient_verified_sources')
    if any(o.get('auto_publish_ready') is True and not offer_is_strict(o) for o in verified):
        reasons.append('publishable_offer_missing_strict_checks')
    return {
        'game':payload.get('game') or (result.get('verified') or {}).get('game') or '',
        'eligible':not reasons,
        'status':'adoption_ready' if not reasons else 'hold',
        'reasons':reasons,
        'strictOfferCount':len(strict),
        'verifiedSourceCount':len(sources),
        'verifiedSources':sorted(sources),
        'researchedAt':payload.get('researchedAt'),
        'sourceQueue':payload.get('sourceQueue') or {},
    }

def run(results_dir=RESULTS,output=OUT,config=CONFIG):
    cfg=load_json(config)
    decisions=[]
    if Path(results_dir).exists():
        for p in sorted(Path(results_dir).glob('*.json')):
            try: decisions.append(evaluate(load_json(p),cfg))
            except Exception as e: decisions.append({'game':p.stem,'eligible':False,'status':'hold','reasons':['invalid_research_result'],'error':type(e).__name__})
    out={'schemaVersion':1,'phase':'PHASE3_ADOPTION_GATE_V29','generatedAt':now_iso(),'apiCalls':0,
         'autoPublish':False,'autoAddGame':False,
         'summary':{'researchedGames':len(decisions),'adoptionReady':sum(1 for x in decisions if x.get('eligible')),'held':sum(1 for x in decisions if not x.get('eligible'))},
         'items':decisions}
    atomic_json(Path(output),out); return out

def main():
    out=run(); print(json.dumps(out['summary'],ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
