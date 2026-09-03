import json, threading, time, importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_global_firecrawl_limit_is_two():
    text=(ROOT/'scripts/firecrawl_township_probe.py').read_text()
    assert 'FIRECRAWL_CALL_LIMIT = max(1, min(2' in text
    assert 'with FIRECRAWL_CALL_SEMAPHORE:' in text

def test_known_pages_parallel_but_bounded():
    text=(ROOT/'scripts/firecrawl_township_probe.py').read_text()
    assert 'POIGAMELAB_KNOWN_PAGE_WORKERS' in text
    assert 'ThreadPoolExecutor(max_workers=page_workers' in text
    assert 'page_workers=max(1,min(2' in text

def test_refresh_policy_safe_defaults():
    p=json.loads((ROOT/'config/refresh_policy.json').read_text())
    assert p['scheduledMode']=='direct-http-api-free'
    sources=json.loads((ROOT/'config/point_sources.json').read_text())['sources']
    by_id={source['id']:source for source in sources}
    requested=set(p['comparisonSources'])
    for game in p['games'].values():
        if game['enabled'] is True:
            requested.update(game.get('supplementalSources') or [])
    for source_id in requested:
        source=by_id[source_id]
        assert 0 <= source['direct_listing_limit'] <= 2
        assert 0 < source['direct_detail_limit'] <= 6
    # The manual API fallback still supplies the original bounded defaults.
    fallback=(ROOT/'scripts/auto_refresh.py').read_text()
    assert "policy.get('maxFirecrawlConcurrency',2)" in fallback
    assert "policy.get('maxKnownPageConcurrency',2)" in fallback
    assert p['publication']['requireAutoPublishReady'] is True
    assert p['publication']['preservePreviousRowsOnTransientFailure'] is True
    assert p['publication']['directRefreshNeverCreatesNewPublishedRows'] is True
    assert p['minimumConfirmedSourcesForComparison'] >= 2
    assert p['games']['きのこ伝説']['enabled'] is True
    assert p['games']['メメントモリ']['enabled'] is True
