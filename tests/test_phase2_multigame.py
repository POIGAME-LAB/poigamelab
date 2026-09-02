import importlib.util, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('probe',ROOT/'scripts/firecrawl_township_probe.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_slug_paths_are_distinct():
    assert m.slugify_game('Township')=='township'
    assert m.slugify_game('きのこ伝説')=='kinoko-densetsu'
    assert m.slugify_game('メメントモリ')=='memento-mori'
    assert m.slugify_game('ワーキングヒーロー')=='working-hero'
    assert m.slugify_game('ホワイトアウト・サバイバル').startswith('game-')

def test_all_games_registered():
    data=json.loads((ROOT/'config/game_targets.json').read_text())
    games=[x['game'] for x in data['games']]
    required={'Township','きのこ伝説','メメントモリ','ワーキングヒーロー','ホワイトアウト・サバイバル'}
    assert required.issubset(set(games))
    assert len(games)==len(set(games))

def test_new_refresh_targets_have_known_first_party_urls():
    data=json.loads((ROOT/'config/game_targets.json').read_text())
    by_game={x['game']:x for x in data['games']}
    assert len(by_game['メメントモリ']['known_urls_by_source']['warau'])==2
    assert len(by_game['ワーキングヒーロー']['known_urls_by_source']['hapitas'])==2
    assert len(by_game['ホワイトアウト・サバイバル']['known_urls_by_source']['warau'])==2
    assert len(by_game['ホワイトアウト・サバイバル']['known_urls_by_source']['moppy'])==1

def test_hapitas_is_registered_first_party_source():
    cfg=json.loads((ROOT/'config/point_sources.json').read_text())
    src={x['id']:x for x in cfg['sources']}
    assert 'hapitas' in src
    assert 'hapitas.jp' in src['hapitas']['search_domains']
    assert '/item/detail/itemid/' in src['hapitas']['direct_detail_url_hints']

def test_non_township_does_not_inherit_known_township_urls():
    text=(ROOT/'scripts/collect_games.py').read_text()
    assert "known=target.get('known_urls_by_source') or {}" in text
    assert "source['known_target_urls']=urls" in text
    assert "target['game']!='Township'" in text

def test_source_allowlist_is_validated_and_applied():
    text=(ROOT/'scripts/collect_games.py').read_text()
    assert "ap.add_argument('--sources'" in text
    assert "unknown=[x for x in requested_sources if x not in registered]" in text
    assert "cfg['sources']=[s for s in cfg.get('sources',[]) if s.get('id') in requested_sources]" in text

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
