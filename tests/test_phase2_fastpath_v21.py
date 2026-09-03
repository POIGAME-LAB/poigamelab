import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_kinoko_known_pages_do_not_enable_partial_fastpath():
    data=json.loads((ROOT/'config/game_targets.json').read_text())
    k=next(x for x in data['games'] if x['game']=='きのこ伝説')
    assert k['known_urls_by_source']['warau']==[
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205816',
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205817']
    assert k['known_urls_by_source']['coincome']==[
        'https://cimcome.jp/campaigns/details/10037',
        'https://cimcome.jp/campaigns/details/10038']
    # collect_games.py defaults a missing opt-in to no partial acceptance.
    assert (k.get('partial_fast_path_sources') or []) == []
    collector=(ROOT/'scripts/collect_games.py').read_text()
    assert "source['allow_partial_known_fast_path']=source['id'] in (target.get('partial_fast_path_sources') or [])" in collector

def test_transient_retry_is_bounded():
    text=(ROOT/'scripts/firecrawl_township_probe.py').read_text()
    assert 'POIGAMELAB_KNOWN_PAGE_ATTEMPTS' in text
    assert 'max(1,min(2' in text
    assert '("429","500","502","503","504")' in text

def test_partial_fastpath_diagnostic():
    text=(ROOT/'scripts/firecrawl_township_probe.py').read_text()
    assert 'allow_partial_known_fast_path' in text
    assert '"partialAccepted"' in text
    assert '"knownExpected"' in text

def test_malformed_and_static_assets_blocked():
    text=(ROOT/'scripts/firecrawl_township_probe.py').read_text()
    assert 'if ")](" in raw or "](" in raw' in text
    assert 'png|jpe?g|gif|webp|svg|ico|css|js' in text
