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

def _is_firecrawl_payment_required(error):
    text=str(error or '').lower()
    return '402' in text and 'payment required' in text

def optional_firecrawl_only_degradation(result, health):
    """Allow V29 to distinguish optional Firecrawl billing exhaustion from evidence failure.

    This is deliberately narrow and research-only: every persisted degraded reason
    must be a source ``search_failed`` whose final Firecrawl search ended with HTTP
    402, while a public first-party discovery strategy was actually attempted and
    completed far enough to provide deterministic diagnostics.  It does *not*
    claim the unavailable source has no offer.  Fatal/partial collector states,
    non-402 errors, unknown reasons, or missing diagnostics fail closed.
    """
    degraded=list(health.get('degradedReasons') or [])
    if not degraded:
        return False, []
    diagnostics=result.get('diagnostics') or []
    by_source={d.get('source_id'):d for d in diagnostics if isinstance(d,dict) and d.get('source_id')}
    warnings=[]
    for reason in degraded:
        if not isinstance(reason,str) or not reason.endswith(':search_failed'):
            return False, []
        sid=reason.rsplit(':',1)[0]
        d=by_source.get(sid)
        if not d or d.get('fatalError'):
            return False, []
        search=d.get('search')
        if not isinstance(search,dict) or search.get('ok') is not False or not _is_firecrawl_payment_required(search.get('error')):
            return False, []
        if search.get('partialAccepted') is True:
            return False, []
        direct_http=d.get('direct_http') or {}
        indexed=d.get('indexed_official') or {}
        public_attempted=direct_http.get('attempted') is True or indexed.get('attempted') is True
        public_completed=(direct_http.get('allListingsFetched') is True or indexed.get('searchCompleted') is True)
        if not (public_attempted and public_completed):
            return False, []
        warnings.append(f'{sid}:optional_firecrawl_402')
    return True, sorted(set(warnings))

def evaluate(payload,cfg):
    reasons=[]
    result=payload.get('collectorResult') or {}
    health=result.get('health') or {}
    verified=(result.get('verified') or {}).get('offers') or []
    strict=[o for o in verified if offer_is_strict(o)]
    sources={o.get('registered_source') for o in strict if o.get('registered_source')}
    min_offers=int(cfg.get('minimumVerifiedOffersForAdoption',2))
    min_sources=int(cfg.get('minimumVerifiedSourcesForAdoption',2))
    optional_only, coverage_warnings=optional_firecrawl_only_degradation(result,health)
    evidence_sufficient=len(strict) >= min_offers and len(sources) >= min_sources
    coverage_override=optional_only and evidence_sufficient
    if payload.get('quarantine') is not True or payload.get('autoPublish') is not False:
        reasons.append('not_quarantined')
    if health.get('collectionComplete') is not True and not coverage_override:
        reasons.append('collection_incomplete')
    if health.get('degradedReasons') and not coverage_override:
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
        'coverageOverrideApplied':coverage_override,
        'coverageWarnings':coverage_warnings if coverage_override else [],
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
    out=run()
    print(json.dumps(out['summary'],ensure_ascii=False))
    for item in out.get('items',[]):
        if item.get('eligible'):
            print(f"[adoption] {item.get('game')}: READY strict={item.get('strictOfferCount',0)} sources={item.get('verifiedSourceCount',0)}")
        else:
            reasons=','.join(item.get('reasons') or []) or 'unknown'
            sources=','.join(item.get('verifiedSources') or []) or '-'
            print(f"[adoption] {item.get('game')}: HOLD reasons={reasons} strict={item.get('strictOfferCount',0)} sources={item.get('verifiedSourceCount',0)} [{sources}]")
    return 0
if __name__=='__main__': raise SystemExit(main())
