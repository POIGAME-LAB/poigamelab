import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('adopt_v47',ROOT/'scripts'/'evaluate_research_adoption.py')
adopt=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(adopt)
CFG={'minimumVerifiedOffersForAdoption':2,'minimumVerifiedSourcesForAdoption':2}

def offer(source):
    return {'registered_source':source,'auto_publish_ready':True,'deterministic_checks':{k:True for k in adopt.REQUIRED_CHECKS}}

def diagnostic(sid,error='HTTP Error 402: Payment Required',indexed_complete=True,direct_complete=False):
    return {
        'source_id':sid,
        'mode':'discovery',
        'fatalError':None,
        'direct_http':{'attempted':True,'allListingsFetched':direct_complete},
        'indexed_official':{'attempted':True,'searchCompleted':indexed_complete},
        'search':{'ok':False,'error':error},
    }

def payload(diags,degraded,offers=None):
    return {
        'game':'ホワイトアウト・サバイバル','quarantine':True,'autoPublish':False,
        'collectorResult':{
            'diagnostics':diags,
            'health':{'collectionComplete':False,'degradedReasons':degraded},
            'verified':{'game':'ホワイトアウト・サバイバル','offers':offers or [offer('moppy'),offer('warau'),offer('warau')]},
        },
    }

def test_live_shaped_402_only_degradation_is_safe_after_two_strict_sources():
    p=payload(
        [diagnostic('chobirich'),diagnostic('coincome',direct_complete=True)],
        ['chobirich:search_failed','coincome:search_failed'],
    )
    d=adopt.evaluate(p,CFG)
    assert d['eligible'] is True
    assert d['coverageOverrideApplied'] is True
    assert d['coverageWarnings']==['chobirich:optional_firecrawl_402','coincome:optional_firecrawl_402']

def test_402_exception_does_not_help_when_independent_source_threshold_is_missing():
    p=payload([diagnostic('chobirich')],['chobirich:search_failed'],offers=[offer('warau'),offer('warau')])
    d=adopt.evaluate(p,CFG)
    assert d['eligible'] is False
    assert d['coverageOverrideApplied'] is False
    assert 'collection_incomplete' in d['reasons']
    assert 'degraded_collection' in d['reasons']
    assert 'insufficient_verified_sources' in d['reasons']

def test_non_402_search_failure_remains_hold():
    p=payload([diagnostic('coincome','HTTP Error 500: Internal Server Error')],['coincome:search_failed'])
    d=adopt.evaluate(p,CFG)
    assert d['eligible'] is False and d['coverageOverrideApplied'] is False

def test_public_discovery_must_have_completed_before_402_can_be_optional():
    p=payload([diagnostic('chobirich',indexed_complete=False,direct_complete=False)],['chobirich:search_failed'])
    d=adopt.evaluate(p,CFG)
    assert d['eligible'] is False and 'degraded_collection' in d['reasons']

def test_unknown_degraded_reason_can_never_be_overridden():
    p=payload([diagnostic('chobirich')],['chobirich:search_failed','coincome:known_page_failed'])
    d=adopt.evaluate(p,CFG)
    assert d['eligible'] is False and d['coverageOverrideApplied'] is False

def test_fatal_state_can_never_be_overridden_even_with_402():
    d0=diagnostic('chobirich'); d0['fatalError']='boom'
    p=payload([d0],['chobirich:search_failed'])
    d=adopt.evaluate(p,CFG)
    assert d['eligible'] is False and d['coverageOverrideApplied'] is False

def test_phase2_completeness_semantics_are_not_changed_by_v47():
    spec=importlib.util.spec_from_file_location('probe_v47',ROOT/'scripts'/'firecrawl_township_probe.py')
    probe=importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
    ok,reasons=probe.assess_collection_completeness([diagnostic('chobirich')])
    assert ok is False
    assert reasons==['chobirich:search_failed']
