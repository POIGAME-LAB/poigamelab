import csv, json, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
import adopt_verified_games as a
REQ=['registered_domain','first_party_registered_source','url_present','evidence_present','evidence_domains_registered','evidence_same_offer_identity','exact_identity_candidate_present','reward_valid','reward_consistent','condition_present']
def offer(site,url,platform='iOS'):
 return {'site':site,'url':url,'evidence_urls':[url],'platform':platform,'reward_yen':1000,'condition':'達成','deadline':'30日','registered_source':site,'auto_publish_ready':True,'deterministic_checks':{k:True for k in REQ}}
def make_fixture(td):
 td=Path(td); (td/'results').mkdir();
 (td/'games.csv').write_text('name,image,condition,days,difficulty,overview,tips,featured,addedDate\nTownship,,指定条件クリア,調査中,調査中,,,true,2026-08-29\n')
 (td/'targets.json').write_text(json.dumps({'games':[{'game':'Township','aliases':['Township']}]}))
 (td/'refresh.json').write_text(json.dumps({'games':{'Township':{'enabled':True}}}))
 (td/'published.csv').write_text(','.join(a.FIELDS)+'\n')
 (td/'cfg.json').write_text(json.dumps({'minimumVerifiedOffersForAdoption':2,'minimumVerifiedSourcesForAdoption':2}))
 return td
def payload(game='新作ゲーム'):
 offs=[offer('warau','https://www.warau.jp/contents/point/pointEntrance.php?point_id=1'),offer('coincome','https://cimcome.jp/campaigns/details/2','Android')]
 return {'game':game,'researchedAt':'2026-08-31','sourceQueue':{'aliases':[game,'New Game']},'quarantine':True,'autoPublish':False,'collectorResult':{'runAt':'2026-08-31T00:00:00+00:00','health':{'collectionComplete':True,'degradedReasons':[]},'verified':{'game':game,'offers':offs}}}
class T(unittest.TestCase):
 def runx(self,td):
  return a.run(td/'adopt.json',td/'results',td/'games.csv',td/'targets.json',td/'refresh.json',td/'published.csv',td/'status.json',td/'cfg.json')
 def test_adopts_strict_game_and_offers(self):
  with tempfile.TemporaryDirectory() as x:
   td=make_fixture(x); (td/'adopt.json').write_text(json.dumps({'items':[{'game':'新作ゲーム','eligible':True,'status':'adoption_ready'}]})); (td/'results/x.json').write_text(json.dumps(payload()))
   out=self.runx(td); self.assertEqual(out['adopted'],1)
   self.assertIn('新作ゲーム',(td/'games.csv').read_text()); self.assertIn('新作ゲーム',(td/'targets.json').read_text())
   rows=list(csv.DictReader((td/'published.csv').open())); self.assertEqual(len(rows),2)
   self.assertFalse(json.loads((td/'refresh.json').read_text())['games']['新作ゲーム']['enabled'])
   self.assertEqual(json.loads((td/'adopt.json').read_text())['items'][0]['status'],'adopted')
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
 def test_config_keeps_new_refresh_disabled(self):
  c=json.loads((ROOT/'config/trend_discovery.json').read_text())['productionAdoption']; self.assertTrue(c['revalidateBeforeWrite']); self.assertFalse(c['initialRefreshEnabled']); self.assertEqual(c['apiCalls'],0)
if __name__=='__main__': unittest.main()
