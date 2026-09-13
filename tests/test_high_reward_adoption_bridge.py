import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('high_reward_bridge',ROOT/'scripts/high_reward_adoption_bridge.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class HighRewardBridgeTests(unittest.TestCase):
    def test_reward_parser_uses_highest_pt_value(self):
        self.assertEqual(mod.parse_reward_pt('1,650pt → 最大 1,740 pt'),1740)
        self.assertEqual(mod.parse_reward_pt('LEVEL4000 70,000pt'),70000)

    def test_os_duplicates_are_grouped_and_sorted_by_reward(self):
        monitor={'items':[
            {'titleHint':'Swipe It: Board Wooden Puzzle（多段階）（Android） - レベル4000到達 70,000pt','source':'powl','classification':'likely_game'},
            {'titleHint':'Swipe It: Board Wooden Puzzle（多段階）（iOS） - レベル4000到達 70,000pt','source':'powl','classification':'likely_game'},
            {'titleHint':'Falling Match -3D Tidy Master（LEVEL240クリア）（iOS） 新規インストール後 2,500pt','source':'powl','classification':'likely_game'},
        ]}
        with tempfile.TemporaryDirectory() as d:
            games=Path(d)/'games.csv'; games.write_text('name,image,condition,days,difficulty,overview,tips,featured,addedDate\n',encoding='utf-8')
            rows=mod.build_candidates(monitor,games_path=games,limit=15)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['game'],'Swipe It: Board Wooden Puzzle')
        self.assertEqual(rows[0]['maxRewardPt'],70000)

    def test_existing_game_is_excluded(self):
        monitor={'items':[{'titleHint':'Known Game（iOS） 新規インストール後 9,000pt','source':'powl','classification':'likely_game'}]}
        with tempfile.TemporaryDirectory() as d:
            games=Path(d)/'games.csv'; games.write_text('name,image,condition,days,difficulty,overview,tips,featured,addedDate\nKnown Game,,,,,,,,\n',encoding='utf-8')
            self.assertEqual(mod.build_candidates(monitor,games_path=games,limit=15),[])

    def test_hold_does_not_stop_next_candidate(self):
        monitor={'items':[
            {'titleHint':'Game A（iOS） 新規インストール後 10,000pt','source':'powl','classification':'likely_game'},
            {'titleHint':'Game B（iOS） 新規インストール後 9,000pt','source':'powl','classification':'likely_game'},
        ]}
        calls=[]
        original_results=mod.research.RESULTS
        original_candidates=mod.ADOPTION_CANDIDATES
        original_status=mod.ADOPTION_STATUS
        original_bridge_status=mod.BRIDGE_STATUS
        with tempfile.TemporaryDirectory() as d:
            d=Path(d); games=d/'games.csv'; games.write_text('name,image,condition,days,difficulty,overview,tips,featured,addedDate\n',encoding='utf-8')
            monitor_path=d/'monitor.json'; monitor_path.write_text(json.dumps(monitor),encoding='utf-8')
            cfg=d/'cfg.json'; cfg.write_text(json.dumps({'minimumVerifiedOffersForAdoption':2,'minimumVerifiedSourcesForAdoption':2}),encoding='utf-8')
            results=d/'results'; results.mkdir(); mod.research.RESULTS=results
            mod.ADOPTION_CANDIDATES=d/'adoption_candidates.json'; mod.ADOPTION_STATUS=d/'adoption_status.json'; mod.BRIDGE_STATUS=d/'bridge_status.json'
            def research_one(item,env=None):
                calls.append(item['game'])
                slug=mod.research.stable_slug(item['game'])
                (results/f'{slug}.json').write_text(json.dumps({'game':item['game']}),encoding='utf-8')
                return {'game':item['game'],'returncode':0,'resultSaved':True}
            def evaluate(payload,cfg):
                ok=payload['game']=='Game B'
                return {'game':payload['game'],'eligible':ok,'status':'adoption_ready' if ok else 'hold','reasons':[] if ok else ['insufficient_verified_sources']}
            def adopt_one(decision,*args):
                return {'game':decision['game'],'adopted':True}
            out=mod.run(monitor_path=monitor_path,games_path=games,config_path=cfg,max_candidates=15,target_adoptions=1,research_one=research_one,evaluate=evaluate,adopt_one=adopt_one)
        mod.research.RESULTS=original_results; mod.ADOPTION_CANDIDATES=original_candidates; mod.ADOPTION_STATUS=original_status; mod.BRIDGE_STATUS=original_bridge_status
        self.assertEqual(calls,['Game A','Game B'])
        self.assertEqual(out['adopted'],1)
        self.assertEqual(out['held'],1)

if __name__=='__main__': unittest.main()
