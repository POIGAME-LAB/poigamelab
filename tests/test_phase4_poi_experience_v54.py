import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('v54',ROOT/'scripts'/'build_poi_experience_summary.py')
v54=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(v54)


def claim(game,category,text,url,status='validated_quarantine'):
    return {'game':game,'category':category,'claim':text,'evidenceQuote':text,'url':url,'sourceType':'community_guide','status':status}

def decision(game,category,text,status='held_single_source'):
    return {'game':game,'category':category,'claim':text,'status':status}

def docs(rows,decisions,x=None,supported=None):
    claims={'phase':'PHASE4_GUIDE_CLAIMS_CORROBORATED_V52','claims':rows}
    dec={'phase':'PHASE4_GUIDE_CLAIM_GATE_V51','decisions':decisions}
    v53={'phase':'PHASE4_POI_GUIDE_DRAFT_V53','supportedClaims':supported or [],'xExperiences':x or [],'drafts':[{'game':'Township','xTwitterResearch':{'complete':True}}]}
    return dec,claims,v53

def xrow(user,text,status='anecdotal_quarantine'):
    return {'game':'Township','url':f'https://x.com/{user}/status/1','sourceIdentity':f'x:{user}','excerpt':text,'status':status,'usableAsFactualClaim':False}


def test_version_phase_and_zero_publication_api():
    dec,claims,v53=docs([],[],[])
    out=v54.run(dec,claims,v53); s=v54.summarize(out)
    assert v54.LOGIC_VERSION=='V54'
    assert out['phase']=='PHASE4_POI_GUIDE_EXPERIENCE_V54'
    assert out['publicationWrites']==0 and out['apiCalls']==0
    assert s['publicationWrites']==0 and s['apiCalls']==0


def test_extracts_observed_day_level_pair():
    s=v54.numeric_signals('レベル35は無課金で23日目に到達できた')
    assert s['levels']==[35] and s['observedDays']==[23]
    assert s['progressPairs']==[{'day':23,'level':35}]


def test_extracts_deadlines_without_turning_hearsay_into_progress():
    s=v54.numeric_signals('レベル60に到達、55日以内。クリアまで50日前後かかるらしい')
    assert s['levels']==[60] and s['deadlineDays']==[55]
    assert s['observedDays']==[] and s['progressPairs']==[]
    assert s['containsHearsay'] is True


def test_held_single_source_claim_becomes_anecdote_not_fact():
    text='76日目でレベル50に到達した'
    dec,claims,v53=docs([claim('Township','timeline',text,'https://x.com/u/status/9')],[decision('Township','timeline',text)])
    out=v54.run(dec,claims,v53)
    row=out['observations'][0]
    assert row['origin']=='held_single_source_claim'
    assert row['usableAsFactualClaim'] is False
    assert row['signals']['progressPairs']==[{'day':76,'level':50}]


def test_supported_claim_is_not_duplicated_into_anecdote_lane():
    text='市場は最優先で建築する'
    dec,claims,v53=docs([claim('Township','priority',text,'https://a.example/x')],[decision('Township','priority',text,'supported_quarantine')])
    assert v54.run(dec,claims,v53)['observations']==[]


def test_x_direct_post_stays_anecdotal_and_structured():
    dec,claims,v53=docs([],[],[xrow('a','Township ポイ活 4日目 レベル16 到達')])
    row=v54.run(dec,claims,v53)['observations'][0]
    assert row['origin']=='direct_x_post' and row['usableAsFactualClaim'] is False
    assert row['signals']['progressPairs']==[{'day':4,'level':16}]


def test_two_independent_sources_make_timeline_anecdotal_section_usable():
    t='レベル35は無課金で23日目に到達できた'
    rows=[claim('Township','timeline',t,'https://blog.example/a')]
    ds=[decision('Township','timeline',t)]
    dec,claims,v53=docs(rows,ds,[xrow('b','Township ポイ活 4日目 レベル16 到達')])
    game=v54.run(dec,claims,v53)['games'][0]
    assert game['experienceTimeline']['independentSourceCount']==2
    assert game['experienceTimeline']['usableAsAnecdotalSection'] is True


def test_same_source_does_not_inflate_independent_timeline_count():
    a='23日目でレベル35に到達した'; b='30日目でレベル40に到達した'
    rows=[claim('Township','timeline',a,'https://same.example/a'),claim('Township','timeline',b,'https://same.example/b')]
    ds=[decision('Township','timeline',a),decision('Township','timeline',b)]
    dec,claims,v53=docs(rows,ds,[])
    game=v54.run(dec,claims,v53)['games'][0]
    assert game['experienceTimeline']['independentSourceCount']==1
    assert game['experienceTimeline']['usableAsAnecdotalSection'] is False


def test_tactic_examples_are_kept_as_experience_only():
    t='飛行機イベントは要求アイテムが重いため途中で無視した'
    dec,claims,v53=docs([claim('Township','tip',t,'https://a.example/guide')],[decision('Township','tip',t)])
    game=v54.run(dec,claims,v53)['games'][0]
    assert game['experienceTactics']['usableAsAnecdotalSection'] is True
    assert game['experienceTactics']['examples'][0]['text']==t


def test_offer_condition_is_never_inferred_from_x_deadline():
    dec,claims,v53=docs([],[],[xrow('a','Township ポイ活 MAXレベル50 期限90日')])
    game=v54.run(dec,claims,v53)['games'][0]
    assert game['offerConditionPolicy']['status']=='dynamic_not_inferred_from_anecdotes'
    assert game['publicationEligible'] is False


def test_article_research_ready_uses_verified_priority_plus_experience_lanes():
    timeline='23日目でレベル35に到達した'
    tactic='飛行機イベントは要求が重いため途中で無視した'
    rows=[claim('Township','timeline',timeline,'https://blog.example/a'),claim('Township','tip',tactic,'https://blog2.example/a')]
    ds=[decision('Township','timeline',timeline),decision('Township','tip',tactic)]
    supported=[{'game':'Township','category':'priority','claim':'市場は最優先で建築する','status':'supported_quarantine'}]
    dec,claims,v53=docs(rows,ds,[xrow('b','Township ポイ活 4日目 レベル16 到達')],supported)
    game=v54.run(dec,claims,v53)['games'][0]
    assert game['researchGaps']==[]
    assert game['researchReadyForArticleWriting'] is True
    assert game['publicationEligible'] is False


def test_missing_verified_priority_keeps_research_not_ready():
    t='23日目でレベル35に到達した'
    dec,claims,v53=docs([claim('Township','timeline',t,'https://a.example/x')],[decision('Township','timeline',t)],[xrow('b','4日目 レベル16 Township ポイ活')])
    game=v54.run(dec,claims,v53)['games'][0]
    assert '複数ソースで裏取り済みの優先攻略' in game['researchGaps']
    assert game['researchReadyForArticleWriting'] is False


def test_x_incomplete_keeps_research_not_ready():
    t='23日目でレベル35に到達した'; tactic='列車を優先して素材を集めた'
    rows=[claim('Township','timeline',t,'https://a.example/x'),claim('Township','tip',tactic,'https://b.example/x')]
    ds=[decision('Township','timeline',t),decision('Township','tip',tactic)]
    supported=[{'game':'Township','category':'priority','claim':'市場優先','status':'supported_quarantine'}]
    dec,claims,v53=docs(rows,ds,[xrow('c','4日目 レベル16 Township ポイ活')],supported)
    v53['drafts'][0]['xTwitterResearch']['complete']=False
    game=v54.run(dec,claims,v53)['games'][0]
    assert 'X体験調査の完了' in game['researchGaps']
    assert game['researchReadyForArticleWriting'] is False


def test_wrong_claim_phase_fails_closed():
    dec,claims,v53=docs([],[],[]); claims['phase']='WRONG'
    try: v54.run(dec,claims,v53); assert False
    except RuntimeError as e: assert 'claims phase mismatch' in str(e)


def test_wrong_v53_phase_fails_closed():
    dec,claims,v53=docs([],[],[]); v53['phase']='WRONG'
    try: v54.run(dec,claims,v53); assert False
    except RuntimeError as e: assert 'V53 draft phase mismatch' in str(e)


def test_status_counts_sources_and_ready_games():
    t='23日目でレベル35に到達した'; tactic='列車を優先して素材を集めた'
    rows=[claim('Township','timeline',t,'https://a.example/x'),claim('Township','tip',tactic,'https://b.example/x')]
    ds=[decision('Township','timeline',t),decision('Township','tip',tactic)]
    supported=[{'game':'Township','category':'priority','claim':'市場優先','status':'supported_quarantine'}]
    dec,claims,v53=docs(rows,ds,[xrow('c','4日目 レベル16 Township ポイ活')],supported)
    s=v54.summarize(v54.run(dec,claims,v53))
    assert s['logicVersion']=='V54'
    assert s['independentExperienceSources']==3
    assert s['timelineReadyGames']==1 and s['tacticReadyGames']==1 and s['articleResearchReadyGames']==1
    assert s['apiCalls']==0 and s['publicationWrites']==0

def test_max_target_level_does_not_cross_pair_with_current_day_progress():
    s=v54.numeric_signals('期限90日 MAXレベル50 4日目 レベル16 到達')
    assert s['targetLevels']==[50]
    assert s['progressPairs']==[{'day':4,'level':16}]
    assert s['deadlineTargetLevels']==[50]
    assert {'day':4,'level':50} not in s['progressPairs']


def test_deadline_without_max_can_use_single_target_level_when_no_progress_day():
    s=v54.numeric_signals('レベル60に到達 StepUp 55日以内')
    assert s['deadlineDays']==[55]
    assert s['observedDays']==[]
    assert s['deadlineTargetLevels']==[60]

def test_tampered_x_source_identity_is_rejected():
    row=xrow('real','Township ポイ活 4日目 レベル16 到達')
    row['sourceIdentity']='x:fake'
    dec,claims,v53=docs([],[],[row])
    out=v54.run(dec,claims,v53)
    assert out['observations']==[]
