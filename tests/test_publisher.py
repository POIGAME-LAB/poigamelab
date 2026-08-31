import csv, importlib.util, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('publisher',ROOT/'scripts/publish_verified_offers.py')
p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

def offer(site,url,platform,reward,ready=True,failed=None):
    checks={'registered_domain':True,'first_party_registered_source':True,'url_present':True,
            'evidence_present':True,'evidence_domains_registered':True,'reward_valid':True,
            'condition_present':True}
    for x in failed or []: checks[x]=False
    return {'site':site,'reward_yen':reward,'condition':'60日以内にStepUp','platform':platform,
            'deadline':'60日','url':url,'evidence_urls':[url],
            'deterministic_checks':checks,'auto_publish_ready':ready,
            'registered_source':p.site_key(site),'reason':'test'}

def five_result():
    return {'runAt':'2026-08-31T17:00:00+09:00','verified':{'game':'Township','offers':[
      offer('ワラウ','https://www.warau.jp/contents/point/pointEntrance.php?point_id=204645&click_id=SECRET','Android',21670),
      offer('ワラウ','https://www.warau.jp/contents/point/pointEntrance.php?point_id=204643&user_id=SECRET','iOS',16760),
      offer('ちょびリッチ','https://www.chobirich.com/ad_details/1894712?digest=SECRET','Android',31817),
      offer('COINCOME','https://cimcome.jp/campaigns/details/9857','Android',33125),
      offer('COINCOME','https://cimcome.jp/campaigns/details/9856','iOS',30025),
    ]}}

def test_exactly_five_publishable():
    rows,exc=p.build_outputs(five_result())
    assert len(rows)==5 and exc==[]
    assert len({x['offerKey'] for x in rows})==5

def test_tracking_params_never_persist():
    rows,_=p.build_outputs(five_result())
    blob=json.dumps(rows)
    assert 'SECRET' not in blob and 'click_id' not in blob and 'user_id' not in blob and 'digest' not in blob
    assert any('point_id=204645' in x['url'] for x in rows)

def test_rejected_offer_goes_exception_queue_only():
    r=five_result()
    r['verified']['offers'].append(offer('ちょびリッチ','https://www.chobirich.com/x','iOS',None,False,['reward_valid']))
    rows,exc=p.build_outputs(r)
    assert len(rows)==5 and len(exc)==1
    assert exc[0]['failedChecks']==['reward_valid']

def test_same_identity_updates_not_duplicates():
    r=five_result()
    changed=offer('ちょびリッチ','https://www.chobirich.com/ad_details/1894712','Android',40000)
    r['verified']['offers'].append(changed)
    rows,_=p.build_outputs(r)
    assert len(rows)==5
    ch=[x for x in rows if x['site']=='chobirich'][0]
    assert ch['reward']==40000

def test_write_is_idempotent(tmp_path):
    r=five_result(); rows,exc=p.build_outputs(r)
    out=tmp_path/'published.csv'; eq=tmp_path/'exceptions.json'
    p.write_outputs(rows,exc,out,eq)
    first=out.read_text()
    p.write_outputs(rows,exc,out,eq)
    assert out.read_text()==first
    with out.open() as f:
        assert len(list(csv.DictReader(f)))==5

def test_offers_csv_is_never_touched(tmp_path):
    original=(ROOT/'offers.csv').read_bytes()
    inp=tmp_path/'result.json'; inp.write_text(json.dumps(five_result()),encoding='utf-8')
    p.publish(inp,tmp_path/'published.csv',tmp_path/'exceptions.json')
    assert (ROOT/'offers.csv').read_bytes()==original
