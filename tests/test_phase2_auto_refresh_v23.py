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

def test_collector_emits_completeness_signal():
    text=(ROOT/'scripts/firecrawl_township_probe.py').read_text()
    assert 'assess_collection_completeness' in text
    assert '"collectionComplete": collection_complete' in text
    assert '"degradedReasons": degraded_reasons' in text

def test_auto_refresh_enables_all_five_games_with_bounded_sources():
    policy=json.loads((ROOT/'config/refresh_policy.json').read_text())
    expected={'Township','きのこ伝説','メメントモリ','ワーキングヒーロー','ホワイトアウト・サバイバル'}
    assert expected == {g for g,cfg in policy['games'].items() if cfg['enabled'] is True}
    assert policy['games']['メメントモリ']['refreshSources']==['warau']
    assert policy['games']['ワーキングヒーロー']['refreshSources']==['hapitas']
    assert policy['games']['ホワイトアウト・サバイバル']['refreshSources']==['moppy','warau']

def test_auto_refresh_passes_source_allowlist_and_uses_probe_compatible_slug():
    text=(ROOT/'scripts/auto_refresh.py').read_text()
    assert "cmd.extend(['--sources',','.join(refresh_sources)])" in text
    assert "hashlib.sha256(raw.encode('utf-8')).hexdigest()[:10]" in text

def test_workflow_has_secrets_concurrency_and_daily_schedule():
    text=(ROOT/'.github/workflows/refresh-verified-offers.yml').read_text()
    assert 'cron: "17 21 * * *"' in text
    assert 'poigamelab-production-writer' in text
    assert 'secrets.FIRECRAWL_API_KEY' in text
    assert 'secrets.GEMINI_API_KEY' in text
    assert 'python scripts/auto_refresh.py' in text

def test_legacy_six_hour_workflow_not_active():
    assert not (ROOT/'.github/workflows/collect-data.yml').exists()
    assert (ROOT/'docs/history/collect-data.legacy.yml').exists()
