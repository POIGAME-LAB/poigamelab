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
    assert p['maxFirecrawlConcurrency']==2
    assert p['maxKnownPageConcurrency']==2
    assert p['publication']['requireAutoPublishReady'] is True
    assert p['publication']['preservePreviousRowsOnTransientFailure'] is True
    assert p['games']['きのこ伝説']['enabled'] is True
    assert p['games']['メメントモリ']['enabled'] is False
