import csv, json, importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pub',ROOT/'scripts/publish_verified_offers.py')
pub=importlib.util.module_from_spec(spec); spec.loader.exec_module(pub)

def row(game,key,reward):
    return {'offerKey':key,'game':game,'site':'warau','provider':'','reward':reward,
            'condition':'ok','platform':'iOS','type':'StepUp','deadline':'',
            'updatedAt':'2026-08-31','url':'https://example.invalid/id',
            'sourceUrl':'https://example.invalid/id','verified':'true'}

def test_complete_snapshot_removes_disappeared_offer(tmp_path):
    out=tmp_path/'published.csv'; ex=tmp_path/'exceptions.json'
    pub.write_outputs([row('きのこ伝説','old-a',100),row('きのこ伝説','old-b',200)],[],out,ex)
    pub.write_outputs([row('きのこ伝説','old-a',150)],[],out,ex,replace_game_snapshot=True)
    rows=list(csv.DictReader(out.open(encoding='utf-8')))
    assert [x['offerKey'] for x in rows]==['old-a']
    assert rows[0]['reward']=='150'

def test_degraded_snapshot_preserves_missing_previous_offer(tmp_path):
    out=tmp_path/'published.csv'; ex=tmp_path/'exceptions.json'
    pub.write_outputs([row('きのこ伝説','a',100),row('きのこ伝説','b',200)],[],out,ex)
    pub.write_outputs([row('きのこ伝説','a',150)],[],out,ex,replace_game_snapshot=False)
    rows={x['offerKey']:x for x in csv.DictReader(out.open(encoding='utf-8'))}
    assert set(rows)=={'a','b'}
    assert rows['a']['reward']=='150'
    assert rows['b']['reward']=='200'

def test_complete_snapshot_preserves_other_games(tmp_path):
    out=tmp_path/'published.csv'; ex=tmp_path/'exceptions.json'
    pub.write_outputs([row('Township','town',999),row('きのこ伝説','kino-old',100)],[],out,ex)
    pub.write_outputs([row('きのこ伝説','kino-new',200)],[],out,ex,replace_game_snapshot=True)
    rows={x['offerKey']:x for x in csv.DictReader(out.open(encoding='utf-8'))}
    assert set(rows)=={'town','kino-new'}

def test_scheduled_policy_uses_all_six_standard_comparison_sources():
    policy=json.loads((ROOT/'config/refresh_policy.json').read_text())
    assert policy['comparisonSources']==[
        'moppy','warau','chobirich','coincome','mikoshi','gendama'
    ]
    expected={'Township','きのこ伝説','メメントモリ','ワーキングヒーロー','ホワイトアウト・サバイバル','東京ディバンカー','パズル＆サバイバル','キングショット','放置少女','エバーテイル'}
    assert expected == {g for g,cfg in policy['games'].items() if cfg['enabled'] is True}
    assert policy['minimumConfirmedSourcesForComparison'] >= 2
    assert policy['scheduledMode']=='direct-http-api-free'
    assert policy['publication']['directRefreshNeverCreatesNewPublishedRows'] is True

def test_working_heroes_can_keep_hapitas_as_supplemental_not_standard():
    policy=json.loads((ROOT/'config/refresh_policy.json').read_text())
    assert 'hapitas' not in policy['comparisonSources']
    assert policy['games']['ワーキングヒーロー']['supplementalSources']==['hapitas']

def test_workflow_is_api_free_and_daily():
    text=(ROOT/'.github/workflows/refresh-verified-offers.yml').read_text()
    assert 'cron: "17 21 * * *"' in text
    assert 'poigamelab-production-writer' in text
    assert 'python scripts/direct_offer_refresh.py' in text
    assert 'FIRECRAWL_API_KEY' not in text
    assert 'GEMINI_API_KEY' not in text
    assert 'TAVILY_API_KEY' not in text
    assert 'data/comparison_refresh_status.json' in text
    assert 'data/comparison_review_queue.json' in text

def test_legacy_six_hour_workflow_not_active():
    assert not (ROOT/'.github/workflows/collect-data.yml').exists()
    assert (ROOT/'docs/history/collect-data.legacy.yml').exists()


def test_new_games_join_daily_refresh_without_expanding_standard_sources():
    policy=json.loads((ROOT/'config/refresh_policy.json').read_text())
    assert policy['comparisonSources']==[
        'moppy','warau','chobirich','coincome','mikoshi','gendama'
    ]
    assert policy['games']['東京ディバンカー']=={
        'enabled':True,
        'supplementalSources':['hapitas'],
        'adoptedBy':'V31',
    }
    assert policy['games']['パズル＆サバイバル']=={
        'enabled':True,
        'supplementalSources':[],
        'adoptedBy':'V31',
    }
    assert policy['games']['キングショット']=={
        'enabled':True,
        'supplementalSources':['hapitas'],
        'adoptedBy':'V31',
    }
    assert 'hapitas' not in policy['comparisonSources']


def test_new_game_enrollment_keeps_single_daily_api_free_workflow():
    text=(ROOT/'.github/workflows/refresh-verified-offers.yml').read_text()
    assert text.count('cron: "17 21 * * *"') == 1
    assert 'workflow_dispatch:' in text
    assert 'python scripts/direct_offer_refresh.py' in text
    assert 'FIRECRAWL_API_KEY' not in text
    assert 'GEMINI_API_KEY' not in text
    assert 'TAVILY_API_KEY' not in text


def test_v32_games_join_daily_refresh_with_same_schedule():
    policy=json.loads((ROOT/'config/refresh_policy.json').read_text())
    assert policy['games']['放置少女']=={
        'enabled':True,
        'supplementalSources':[],
        'adoptedBy':'V32',
    }
    assert policy['games']['エバーテイル']=={
        'enabled':True,
        'supplementalSources':['hapitas'],
        'adoptedBy':'V32',
    }
    assert 'hapitas' not in policy['comparisonSources']
    text=(ROOT/'.github/workflows/refresh-verified-offers.yml').read_text()
    assert text.count('cron: "17 21 * * *"') == 1
