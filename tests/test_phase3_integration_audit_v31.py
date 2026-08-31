import csv,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
import audit_phase3_pipeline as a
FIELDS=['offerKey','game','site','provider','reward_yen','condition','platform','type','deadline','updatedAt','url','sourceUrl','verified']
def fixture(x):
 p=Path(x); (p/'games.csv').write_text('name,image,condition,days,difficulty,overview,tips,featured,addedDate\nTownship,,x,x,x,,,true,2026-01-01\n',encoding='utf-8')
 (p/'targets.json').write_text(json.dumps({'games':[{'game':'Township'}]},ensure_ascii=False)); (p/'refresh.json').write_text(json.dumps({'games':{'Township':{'enabled':True}}},ensure_ascii=False)); (p/'adopt.json').write_text(json.dumps({'items':[]}))
 with (p/'published.csv').open('w',newline='',encoding='utf-8') as f: csv.DictWriter(f,fieldnames=FIELDS).writeheader()
 return p
def run(p): return a.audit(p/'games.csv',p/'targets.json',p/'refresh.json',p/'published.csv',p/'adopt.json')
def add_offer(p,key='k1',game='新作',url='https://example.com/a'):
 rows=[]
 with (p/'published.csv').open(encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f))
 rows.append({'offerKey':key,'game':game,'url':url})
 with (p/'published.csv').open('w',encoding='utf-8',newline='') as f: w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
class T(unittest.TestCase):
 def test_clean_baseline(self):
  with tempfile.TemporaryDirectory() as x: self.assertTrue(run(fixture(x))['success'])
 def test_duplicate_game_fails(self):
  with tempfile.TemporaryDirectory() as x:
   p=fixture(x); p.joinpath('games.csv').write_text(p.joinpath('games.csv').read_text()+'Township,,x,x,x,,,false,2026-01-02\n'); self.assertFalse(run(p)['success'])
 def test_duplicate_offer_key_fails(self):
  with tempfile.TemporaryDirectory() as x:
   p=fixture(x); add_offer(p); add_offer(p); self.assertTrue(any('duplicate_offer_key' in e for e in run(p)['errors']))
 def test_published_unknown_game_fails(self):
  with tempfile.TemporaryDirectory() as x:
   p=fixture(x); add_offer(p); self.assertTrue(any('published_game_missing' in e for e in run(p)['errors']))
 def test_invalid_url_fails(self):
  with tempfile.TemporaryDirectory() as x:
   p=fixture(x); add_offer(p,game='Township',url='javascript:bad'); self.assertTrue(any('invalid_published_url' in e for e in run(p)['errors']))
 def test_adopted_requires_registry_refresh_and_offers(self):
  with tempfile.TemporaryDirectory() as x:
   p=fixture(x); p.joinpath('adopt.json').write_text(json.dumps({'items':[{'game':'新作','status':'adopted','publishedOfferCount':2}]},ensure_ascii=False)); self.assertFalse(run(p)['success'])
 def test_valid_adoption_passes(self):
  with tempfile.TemporaryDirectory() as x:
   p=fixture(x); p.joinpath('games.csv').write_text(p.joinpath('games.csv').read_text()+'新作,,x,x,x,,,false,2026-01-02\n'); p.joinpath('targets.json').write_text(json.dumps({'games':[{'game':'Township'},{'game':'新作'}]},ensure_ascii=False)); p.joinpath('refresh.json').write_text(json.dumps({'games':{'Township':{'enabled':True},'新作':{'enabled':False}}},ensure_ascii=False)); p.joinpath('adopt.json').write_text(json.dumps({'items':[{'game':'新作','status':'adopted','publishedOfferCount':2}]},ensure_ascii=False)); add_offer(p,'k1'); add_offer(p,'k2'); self.assertTrue(run(p)['success'])
 def test_workflow_audits_before_commit_and_conditional_results_add(self):
  s=(ROOT/'.github/workflows/discover-trending-games.yml').read_text(); self.assertLess(s.index('audit_phase3_pipeline.py'),s.index('git config user.name')); self.assertIn('if [ -d data/research_results ]',s); self.assertIn('data/phase3_pipeline_audit.json',s)
if __name__=='__main__': unittest.main()
