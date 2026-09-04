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
    required={'Township','きのこ伝説','メメントモリ','ワーキングヒーロー','ホワイトアウト・サバイバル','東京ディバンカー','パズル＆サバイバル','キングショット'}
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


def test_new_game_known_sources_are_isolated():
    data=json.loads((ROOT/'config/game_targets.json').read_text())
    by_game={x['game']:x for x in data['games']}
    tokyo=by_game['東京ディバンカー']['known_urls_by_source']
    puzzles=by_game['パズル＆サバイバル']['known_urls_by_source']
    assert set(tokyo)=={'moppy','hapitas'}
    assert set(puzzles)=={'moppy','warau'}
    assert all('15827' in u or '158257' in u for u in tokyo['moppy'])
    assert all('16036' in u for u in puzzles['moppy'])
    assert all('point_id=205' in u for u in puzzles['warau'])


def test_kingshot_known_sources_are_isolated():
    data=json.loads((ROOT/'config/game_targets.json').read_text())
    by_game={x['game']:x for x in data['games']}
    kingshot=by_game['キングショット']['known_urls_by_source']
    assert set(kingshot)=={'moppy','hapitas'}
    assert set(kingshot['moppy']) == {
        'https://pc.moppy.jp/ad/detail.php?site_id=161855',
        'https://pc.moppy.jp/ad/detail.php?site_id=161854',
    }
    assert set(kingshot['hapitas']) == {
        'https://hapitas.jp/item/detail/itemid/101355',
        'https://hapitas.jp/item/detail/itemid/101354',
    }
