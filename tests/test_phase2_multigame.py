import importlib.util, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('probe',ROOT/'scripts/firecrawl_township_probe.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_slug_paths_are_distinct():
    assert m.slugify_game('Township')=='township'
    assert m.slugify_game('きのこ伝説')=='kinoko-densetsu'
    assert m.slugify_game('メメントモリ')=='memento-mori'
    assert m.slugify_game('ワーキングヒーロー')=='working-hero'

def test_all_games_registered():
    data=json.loads((ROOT/'config/game_targets.json').read_text())
    games=[x['game'] for x in data['games']]
    required={'Township','きのこ伝説','メメントモリ','ワーキングヒーロー'}
    assert required.issubset(set(games))
    assert len(games)==len(set(games))

def test_non_township_does_not_inherit_known_township_urls():
    text=(ROOT/'scripts/collect_games.py').read_text()
    assert "known=target.get('known_urls_by_source') or {}" in text
    assert "source['known_target_urls']=urls" in text
    assert "target['game']!='Township'" in text

def test_dynamic_merge_game():
    old=m.CURRENT_TARGET
    try:
        m.CURRENT_TARGET={'game':'メメントモリ','aliases':['メメントモリ']}
        got=m.merge_offers([{'offers':[]}])
        assert got['game']=='メメントモリ'
    finally:
        m.CURRENT_TARGET=old

def test_config_restore_even_on_failure():
    text=(ROOT/'scripts/collect_games.py').read_text()
    assert 'finally:' in text and "CFG.write_text(original" in text
