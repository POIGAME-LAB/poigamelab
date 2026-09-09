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
    required={'Township','きのこ伝説','メメントモリ','ワーキングヒーロー','ホワイトアウト・サバイバル','東京ディバンカー','パズル＆サバイバル','キングショット','放置少女','エバーテイル'}
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



def test_kinoko_known_sources_include_current_hapitas_pair():
    data=json.loads((ROOT/'config/game_targets.json').read_text())
    by_game={x['game']:x for x in data['games']}
    kinoko=by_game['きのこ伝説']['known_urls_by_source']
    assert set(kinoko['hapitas'])=={
        'https://hapitas.jp/item/detail/itemid/102450',
        'https://hapitas.jp/item/detail/itemid/102451',
        'https://hapitas.jp/item/detail/itemid/99850',
    }
    assert 'https://hapitas.jp/item/detail/itemid/100403' not in kinoko['hapitas']


def test_mementomori_known_sources_include_current_hapitas_pair():
    data=json.loads((ROOT/'config/game_targets.json').read_text())
    by_game={x['game']:x for x in data['games']}
    memento=by_game['メメントモリ']['known_urls_by_source']
    assert set(memento)=={'moppy','hapitas','warau'}
    assert set(memento['moppy'])=={
        'https://pc.moppy.jp/ad/detail.php?site_id=160690',
        'https://pc.moppy.jp/ad/detail.php?site_id=160688',
    }
    assert set(memento['hapitas'])=={
        'https://hapitas.jp/item/detail/itemid/99420',
        'https://hapitas.jp/item/detail/itemid/99421',
        'https://hapitas.jp/item/detail/itemid/101349',
    }
    assert set(memento['warau'])=={
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=206501',
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=206500',
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=206037',
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205982',
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=206035',
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205975',
    }


def test_new_game_known_sources_are_isolated():
    data=json.loads((ROOT/'config/game_targets.json').read_text())
    by_game={x['game']:x for x in data['games']}
    tokyo=by_game['東京ディバンカー']['known_urls_by_source']
    puzzles=by_game['パズル＆サバイバル']['known_urls_by_source']
    assert set(tokyo)=={'moppy','hapitas'}
    assert set(puzzles)=={'moppy','warau','hapitas'}
    assert all('15827' in u or '158257' in u for u in tokyo['moppy'])
    assert set(tokyo['warau'])=={
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=191400',
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=191401',
    }
    assert all('16036' in u for u in puzzles['moppy'])
    assert set(puzzles['hapitas']) == {
        'https://hapitas.jp/item/detail/itemid/98148',
        'https://hapitas.jp/item/detail/itemid/99158',
    }
    assert set(puzzles['warau']) == {
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=206425',
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205361',
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=206488',
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=206460',
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=205557',
    }


def test_kingshot_known_sources_are_isolated():
    data=json.loads((ROOT/'config/game_targets.json').read_text())
    by_game={x['game']:x for x in data['games']}
    kingshot=by_game['キングショット']['known_urls_by_source']
    assert set(kingshot)=={'moppy','hapitas','warau'}
    assert set(kingshot['moppy']) == {
        'https://pc.moppy.jp/ad/detail.php?site_id=161855',
        'https://pc.moppy.jp/ad/detail.php?site_id=161854',
    }
    assert set(kingshot['hapitas']) == {
        'https://hapitas.jp/item/detail/itemid/101355',
        'https://hapitas.jp/item/detail/itemid/101354',
    }
    assert set(kingshot['warau']) == {
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=204984',
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=204983',
    }


def test_v32_game_known_sources_are_isolated():
    data=json.loads((ROOT/'config/game_targets.json').read_text())
    by_game={x['game']:x for x in data['games']}

    houchi=by_game['放置少女']['known_urls_by_source']
    assert set(houchi)=={'moppy','warau','hapitas'}
    assert houchi['moppy']==['https://pc.moppy.jp/ad/detail.php?site_id=147270']
    assert set(houchi['warau'])=={
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=177971',
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=206411',
    }
    assert houchi['hapitas']==[
        'https://hapitas.jp/item/detail/itemid/91475',
    ]

    evertale=by_game['エバーテイル']['known_urls_by_source']
    assert set(evertale)=={'moppy','hapitas','warau'}
    assert set(evertale['moppy'])=={
        'https://pc.moppy.jp/ad/detail.php?site_id=158276',
        'https://pc.moppy.jp/ad/detail.php?site_id=158275',
    }
    assert set(evertale['hapitas'])=={
        'https://hapitas.jp/item/detail/itemid/91344',
        'https://hapitas.jp/item/detail/itemid/91343',
        'https://hapitas.jp/item/detail/itemid/91331',
        'https://hapitas.jp/item/detail/itemid/91345',
    }
    assert evertale['warau']==[
        'https://www.warau.jp/contents/point/pointEntrance.php?point_id=188016',
    ]
