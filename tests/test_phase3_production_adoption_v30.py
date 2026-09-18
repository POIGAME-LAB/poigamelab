import csv, json, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
import adopt_verified_games as a
REQ=['registered_domain','first_party_registered_source','url_present','evidence_present','evidence_domains_registered','evidence_same_offer_identity','exact_identity_candidate_present','reward_valid','reward_consistent','condition_present']
def offer(site,url,platform='iOS'):
 return {'site':site,'url':url,'evidence_urls':[url],'platform':platform,'reward_yen':1000,'condition':'達成','deadline':'30日','registered_source':site,'auto_publish_ready':True,'deterministic_checks':{k:True for k in REQ}}
def make_fixture(td):
 td=Path(td); (td/'results').mkdir();
 (td/'games.csv').write_text('name,image,condition,days,difficulty,overview,tips,featured,addedDate,provisionalReward,provisionalSource\nTownship,,指定条件クリア,調査中,調査中,,,true,2026-08-29,12345,seed\n')
 (td/'targets.json').write_text(json.dumps({'games':[{'game':'Township','aliases':['Township']}]}))
 (td/'refresh.json').write_text(json.dumps({'games':{'Township':{'enabled':True}}}))
 (td/'published.csv').write_text(','.join(a.FIELDS)+'\n')
 (td/'cfg.json').write_text(json.dumps({'minimumVerifiedOffersForAdoption':2,'minimumVerifiedSourcesForAdoption':2}))
 return td
def payload(game='新作ゲーム'):
 offs=[offer('warau','https://www.warau.jp/contents/point/pointEntrance.php?point_id=1'),offer('coincome','https://cimcome.jp/campaigns/details/2','Android')]
 return {'game':game,'researchedAt':'2026-08-31','sourceQueue':{'aliases':[game,'New Game']},'quarantine':True,'autoPublish':False,'collectorResult':{'runAt':'2026-08-31T00:00:00+00:00','health':{'collectionComplete':True,'degradedReasons':[]},'verified':{'game':game,'offers':offs}}}
def content_package(game='新作ゲーム'):
 return {'schemaVersion':1,'game':game,'publicationReady':True,
  'research':{
   'web':{'searched':True,'complete':True,'sources':[{'id':'web1','url':'https://example.com/g','claim':'攻略情報を確認'}]},
   'x':{'searched':True,'complete':True,'sources':[{'id':'x1','url':'https://x.com/u/status/1','claim':'進捗情報を確認'}]},
   'youtube':{'searched':True,'complete':True,'sources':[]},
   'instagram':{'searched':True,'complete':True,'sources':[]},
   'pointSites':{'searched':True,'complete':True,'sources':[{'id':'p1','url':'https://www.warau.jp/example','claim':'案件条件を確認'}]}},
  'guide':{'title':'新作ゲーム ポイ活攻略まとめ','intro':'案件達成のために確認済み情報を整理した攻略です。','overview':'育成とステージ進行を組み合わせて目標到達を目指すゲームです。','tips':'毎日の日課と資源管理を優先して効率よく進めます。','sections':[
   {'heading':'序盤','text':'序盤は日課を開放しつつ目標レベルまで育成を進めます。','sourceRefs':['web1','p1']},
   {'heading':'中盤','text':'中盤は資源を温存しながら詰まりやすい条件を先回りします。','sourceRefs':['web1']},
   {'heading':'進捗','text':'公開された進捗例は個人差のある参考値として分離して扱います。','sourceRefs':['x1']}]},
  'progress':[{'identityKey':'x:u','sourceRef':'x1','summary':'10日目付近の公開進捗記録'}],
  'image':{'path':'assets/game-art/new-game.png','provenance':'generated','rightsConfirmed':True},
  'guidePath':'new-game-guide.html','days':'10〜14日目安','difficulty':'普通'}
def install_content(td):
 td=Path(td); (td/'assets/game-art').mkdir(parents=True,exist_ok=True); (td/'assets/game-art/new-game.png').write_bytes(b'x'); (td/'new-game-guide.html').write_text('<html>guide</html>'); d=td/'content'; d.mkdir(); (d/'p.json').write_text(json.dumps(content_package(),ensure_ascii=False)); return d
class T(unittest.TestCase):
 def runx(self,td,content_dir=None,content_root=None):
  kwargs={}
  if content_dir is not None: kwargs['content_dir']=content_dir
  if content_root is not None: kwargs['content_root']=content_root
  return a.run(td/'adopt.json',td/'results',td/'games.csv',td/'targets.json',td/'refresh.json',td/'published.csv',td/'status.json',td/'cfg.json',**kwargs)
 def test_adopts_strict_game_and_offers(self):
  with tempfile.TemporaryDirectory() as x:
   td=make_fixture(x); (td/'adopt.json').write_text(json.dumps({'items':[{'game':'新作ゲーム','eligible':True,'status':'adoption_ready'}]})); (td/'results/x.json').write_text(json.dumps(payload()))
   out=self.runx(td); self.assertEqual(out['adopted'],1)
   self.assertIn('新作ゲーム',(td/'games.csv').read_text()); self.assertIn('新作ゲーム',(td/'targets.json').read_text())
   rows=list(csv.DictReader((td/'published.csv').open())); self.assertEqual(len(rows),2)
   self.assertFalse(json.loads((td/'refresh.json').read_text())['games']['新作ゲーム']['enabled'])
   self.assertEqual(json.loads((td/'adopt.json').read_text())['items'][0]['status'],'adopted')
 def test_preserves_extended_games_schema_and_values(self):
  with tempfile.TemporaryDirectory() as x:
   td=make_fixture(x); (td/'adopt.json').write_text(json.dumps({'items':[{'game':'新作ゲーム','eligible':True,'status':'adoption_ready'}]})); (td/'results/x.json').write_text(json.dumps(payload()))
   self.runx(td)
   rows=list(csv.DictReader((td/'games.csv').open()))
   self.assertEqual(list(rows[0].keys()),['name','image','condition','days','difficulty','overview','tips','featured','addedDate','provisionalReward','provisionalSource'])
   self.assertEqual(rows[0]['provisionalReward'],'12345'); self.assertEqual(rows[0]['provisionalSource'],'seed')
   new=next(r for r in rows if r['name']=='新作ゲーム'); self.assertEqual(new['provisionalReward'],''); self.assertEqual(new['provisionalSource'],'')
 def test_registered_source_id_wins_over_display_label(self):
  with tempfile.TemporaryDirectory() as x:
   td=make_fixture(x); p=payload(); p['collectorResult']['verified']['offers'][1]=offer('アメフリ','https://www.amefri.net/detail/id/2','Android'); p['collectorResult']['verified']['offers'][1]['registered_source']='amefuri'
   (td/'adopt.json').write_text(json.dumps({'items':[{'game':'新作ゲーム','eligible':True,'status':'adoption_ready'}]})); (td/'results/x.json').write_text(json.dumps(p))
   out=self.runx(td); self.assertEqual(out['adopted'],1)
   rows=list(csv.DictReader((td/'published.csv').open())); self.assertIn('amefuri',{r['site'] for r in rows}); self.assertNotIn('unknown',{r['site'] for r in rows})
 def test_required_content_package_blocks_blank_adoption(self):
  with tempfile.TemporaryDirectory() as x:
   td=make_fixture(x); cfg=json.loads((td/'cfg.json').read_text()); cfg['productionAdoption']={'requiresContentPackage':True}; (td/'cfg.json').write_text(json.dumps(cfg)); (td/'adopt.json').write_text(json.dumps({'items':[{'game':'新作ゲーム','eligible':True,'status':'adoption_ready'}]})); (td/'results/x.json').write_text(json.dumps(payload())); empty=td/'content'; empty.mkdir()
   out=self.runx(td,empty,td); self.assertEqual(out['adopted'],0); self.assertIn('content_gate:content_package_missing',out['results'][0]['reasons']); self.assertNotIn('新作ゲーム',(td/'games.csv').read_text())
 def test_complete_content_package_populates_catalog(self):
  with tempfile.TemporaryDirectory() as x:
   td=make_fixture(x); cfg=json.loads((td/'cfg.json').read_text()); cfg['productionAdoption']={'requiresContentPackage':True}; (td/'cfg.json').write_text(json.dumps(cfg)); (td/'adopt.json').write_text(json.dumps({'items':[{'game':'新作ゲーム','eligible':True,'status':'adoption_ready'}]})); (td/'results/x.json').write_text(json.dumps(payload())); content=install_content(td)
   out=self.runx(td,content,td); self.assertEqual(out['adopted'],1); self.assertTrue(out['results'][0]['contentPackageValidated']); rows=list(csv.DictReader((td/'games.csv').open())); new=next(r for r in rows if r['name']=='新作ゲーム'); self.assertEqual(new['image'],'assets/game-art/new-game.png'); self.assertEqual(new['difficulty'],'普通'); self.assertNotEqual(new['overview'],'')
 def test_alias_collision_with_existing_game_blocks_second_catalog_row(self):
  with tempfile.TemporaryDirectory() as x:
   td=make_fixture(x)
   targets=json.loads((td/'targets.json').read_text())
   targets['games'][0]['aliases']=['Township','タウンシップ']
   (td/'targets.json').write_text(json.dumps(targets,ensure_ascii=False))
   p=payload('タウンシップ')
   p['sourceQueue']['aliases']=['タウンシップ','Township']
   (td/'adopt.json').write_text(json.dumps({'items':[{'game':'タウンシップ','eligible':True,'status':'adoption_ready'}]},ensure_ascii=False))
   (td/'results/x.json').write_text(json.dumps(p,ensure_ascii=False))
   out=self.runx(td)
   self.assertEqual(out['adopted'],0)
   self.assertIn('existing_game_identity_collision',out['results'][0]['reasons'])
   rows=list(csv.DictReader((td/'games.csv').open()))
   self.assertEqual([r['name'] for r in rows],['Township'])
 def test_idempotent_no_duplicate_game_or_offer(self):
  with tempfile.TemporaryDirectory() as x:
   td=make_fixture(x); (td/'adopt.json').write_text(json.dumps({'items':[{'game':'新作ゲーム','eligible':True,'status':'adoption_ready'}]})); (td/'results/x.json').write_text(json.dumps(payload()))
   self.runx(td); self.runx(td)
   self.assertEqual((td/'games.csv').read_text().count('新作ゲーム'),1); self.assertEqual(len(list(csv.DictReader((td/'published.csv').open()))),2)
 def test_revalidation_blocks_tampered_result(self):
  with tempfile.TemporaryDirectory() as x:
   td=make_fixture(x); p=payload(); p['collectorResult']['verified']['offers'][0]['deterministic_checks']['reward_consistent']=False
   (td/'adopt.json').write_text(json.dumps({'items':[{'game':'新作ゲーム','eligible':True,'status':'adoption_ready'}]})); (td/'results/x.json').write_text(json.dumps(p))
   out=self.runx(td); self.assertEqual(out['adopted'],0); self.assertNotIn('新作ゲーム',(td/'games.csv').read_text())
 def test_non_ready_never_adopts(self):
  with tempfile.TemporaryDirectory() as x:
   td=make_fixture(x); (td/'adopt.json').write_text(json.dumps({'items':[{'game':'新作ゲーム','eligible':False,'status':'hold'}]})); (td/'results/x.json').write_text(json.dumps(payload()))
   self.assertEqual(self.runx(td)['adopted'],0)
 def test_workflow_orders_gate_before_adoption_and_commits_production(self):
  s=(ROOT/'.github/workflows/discover-trending-games.yml').read_text(); self.assertLess(s.index('evaluate_research_adoption.py'),s.index('adopt_verified_games.py'))
  self.assertIn('data/published_offers.csv',s); self.assertIn('config/game_targets.json',s)
 def test_config_keeps_new_refresh_disabled_and_requires_content(self):
  c=json.loads((ROOT/'config/trend_discovery.json').read_text())['productionAdoption']; self.assertTrue(c['revalidateBeforeWrite']); self.assertTrue(c['requiresContentPackage']); self.assertFalse(c['initialRefreshEnabled']); self.assertEqual(c['apiCalls'],0)
if __name__=='__main__': unittest.main()
