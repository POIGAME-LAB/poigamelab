#!/usr/bin/env python3
"""PHASE 4 V54: synthesize a poikatsu experience lane without promoting anecdotes.

V54 is API-free. It combines V53 directly fetched X experiences with V51
single-source community claims that survived the evidence/quote checks. It
extracts only deterministic level/day/deadline signals and keeps every such
observation explicitly anecdotal (`usableAsFactualClaim: false`). Verified
strategy facts remain exclusively in V53's supported_quarantine lane.

The output is a research package for a later article-writing stage. It can mark
that enough independent experiences exist to write an *anecdotal* pace section,
but it never marks any anecdote as a verified fact and never publishes content.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import evaluate_guide_claims as gate
import build_poi_guide_draft as v53

DECISIONS = ROOT / 'data' / 'guide_claim_decisions.json'
CLAIMS = ROOT / 'data' / 'guide_claims_corroborated.json'
V53_DRAFT = ROOT / 'data' / 'poi_guide_draft.json'
OUT = ROOT / 'data' / 'poi_guide_experience_summary.json'
STATUS = ROOT / 'data' / 'poi_guide_experience_status.json'
LOGIC_VERSION = 'V54'

EXPERIENCE_CATEGORIES = {'requirement', 'timeline', 'priority', 'tip', 'resource', 'warning'}
TACTIC_MARKERS = (
    '納屋', '倉庫', '列車', 'ヘリ', '飛行機', '市場', '商人', '工場', '島', '素材',
    'コイン', 'キャッシュ', 'ブースター', '注文', '生産', '収穫', '優先', '無視', '建築',
)
SUBJECTIVE_MARKERS = ('楽勝', '大変', '厳しい', 'きつい', '現実的', '余裕', '難しい')
HEARSAY_MARKERS = ('らしい', 'とのこと', 'そうです', 'と言われ', '目安らしい')


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def norm(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(value or ''))).strip()


def source_identity(url):
    x = v53.x_source_identity(url)
    if x:
        return x
    site = gate.source_site(url)
    return f'site:{site}' if site else ''


def numeric_signals(text):
    """Extract conservative numeric signals; no semantic completion or inference."""
    s = norm(text)
    level_matches = []
    # Explicit MAX level is an offer target, not a current progress level.
    target_levels = sorted({
        int(m.group(1)) for m in re.finditer(r'(?i)MAX\s*レベル\s*(\d{1,3})', s)
        if 0 < int(m.group(1)) <= 999
    })
    for m in re.finditer(r'(?i)(?:Lv\.?|レベル)\s*(\d{1,3})', s):
        value = int(m.group(1))
        if not (0 < value <= 999):
            continue
        prefix = s[max(0, m.start()-5):m.start()].casefold().replace(' ', '')
        is_max = prefix.endswith('max')
        level_matches.append({'level': value, 'start': m.start(), 'end': m.end(), 'isTarget': is_max})
    levels = sorted({m['level'] for m in level_matches})

    day_matches = [
        {'day': int(m.group(1)), 'start': m.start(), 'end': m.end()}
        for m in re.finditer(r'(\d{1,3})\s*日目', s)
        if 0 < int(m.group(1)) <= 999
    ]
    observed_days = sorted({m['day'] for m in day_matches})

    deadline_days = set()
    for pat in (
        r'(\d{1,3})\s*日\s*以内',
        r'期限\s*(\d{1,3})\s*日',
        r'(\d{1,3})\s*日\s*期限',
    ):
        deadline_days.update(int(x) for x in re.findall(pat, s) if 0 < int(x) <= 999)
    deadline_days = sorted(deadline_days)

    # Pair each explicit N日目 with the nearest non-MAX level mention. This avoids
    # the false cross-product "MAXレベル50 / 4日目 レベル16" -> "4日目Lv50".
    progress_pairs = []
    seen_pairs = set()
    progress_levels = [m for m in level_matches if not m['isTarget']]
    for day in day_matches:
        nearby = []
        day_center = (day['start'] + day['end']) / 2
        for lm in progress_levels:
            level_center = (lm['start'] + lm['end']) / 2
            distance = abs(level_center - day_center)
            if distance <= 120:
                nearby.append((distance, lm['start'], lm['level']))
        if not nearby:
            continue
        nearby.sort()
        pair = (day['day'], nearby[0][2])
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            progress_pairs.append({'day': pair[0], 'level': pair[1]})

    # For deadline examples, explicit MAX level wins. If there is no observed-day
    # progress and only one level is mentioned, that level may describe the target.
    deadline_target_levels = list(target_levels)
    if deadline_days and not deadline_target_levels and not observed_days:
        deadline_target_levels = levels

    return {
        'levels': levels,
        'targetLevels': target_levels,
        'observedDays': observed_days,
        'deadlineDays': deadline_days,
        'deadlineTargetLevels': deadline_target_levels,
        'progressPairs': progress_pairs,
        'containsHearsay': any(x in s for x in HEARSAY_MARKERS),
    }


def anecdotal_claims(decision_doc, claims_doc):
    """Rejoin held V51 decisions to exact V52 artifact rows, preserving provenance."""
    rows = claims_doc.get('claims') if isinstance(claims_doc, dict) else []
    rows = rows if isinstance(rows, list) else []
    by_key = {}
    for row in rows:
        if not isinstance(row, dict) or row.get('status') != 'validated_quarantine':
            continue
        game = norm(row.get('game')); category = norm(row.get('category')); claim = norm(row.get('claim'))
        url = str(row.get('url') or '').strip()
        if not game or category not in EXPERIENCE_CATEGORIES or len(claim) < 4 or not source_identity(url):
            continue
        key = (game, category, gate.text_key(claim))
        by_key.setdefault(key, []).append(row)

    decisions = decision_doc.get('decisions') if isinstance(decision_doc, dict) else []
    decisions = decisions if isinstance(decisions, list) else []
    out = []
    seen = set()
    for d in decisions:
        if not isinstance(d, dict) or d.get('status') != 'held_single_source':
            continue
        game = norm(d.get('game')); category = norm(d.get('category')); claim = norm(d.get('claim'))
        key = (game, category, gate.text_key(claim))
        for row in by_key.get(key) or []:
            url = str(row.get('url') or '').strip(); identity = source_identity(url)
            dedupe = (identity, gate.text_key(claim))
            if not identity or dedupe in seen:
                continue
            seen.add(dedupe)
            sig = numeric_signals(claim)
            has_tactic = any(m in claim for m in TACTIC_MARKERS)
            has_subjective = any(m in claim for m in SUBJECTIVE_MARKERS)
            if not (sig['levels'] or sig['observedDays'] or sig['deadlineDays'] or has_tactic or has_subjective):
                continue
            out.append({
                'game': game,
                'sourceIdentity': identity,
                'url': url,
                'text': claim,
                'category': category,
                'origin': 'held_single_source_claim',
                'signals': sig,
                'hasTacticSignal': has_tactic,
                'hasSubjectiveSignal': has_subjective,
                'evidenceLevel': 'single_source_anecdote',
                'usableAsFactualClaim': False,
                'status': 'anecdotal_quarantine',
            })
    return out


def x_observations(v53_doc):
    out = []
    seen = set()
    for row in (v53_doc.get('xExperiences') or []) if isinstance(v53_doc, dict) else []:
        if not isinstance(row, dict) or row.get('status') != 'anecdotal_quarantine':
            continue
        game = norm(row.get('game')); url = str(row.get('url') or '').strip(); text = norm(row.get('excerpt'))
        computed_identity = source_identity(url)
        claimed_identity = str(row.get('sourceIdentity') or '')
        if claimed_identity and claimed_identity != computed_identity:
            continue
        identity = computed_identity
        if not game or not identity or len(text) < 4:
            continue
        dedupe = (identity, url)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        sig = numeric_signals(text)
        out.append({
            'game': game,
            'sourceIdentity': identity,
            'url': url,
            'text': text,
            'category': 'experience',
            'origin': 'direct_x_post',
            'signals': sig,
            'hasTacticSignal': any(m in text for m in TACTIC_MARKERS),
            'hasSubjectiveSignal': any(m in text for m in SUBJECTIVE_MARKERS),
            'evidenceLevel': 'single_public_post_anecdote',
            'usableAsFactualClaim': False,
            'status': 'anecdotal_quarantine',
        })
    return out


def merge_observations(*groups):
    """Deduplicate exact source/text reuse; one source may contribute multiple distinct notes."""
    out = []
    seen = set()
    for group in groups:
        for row in group:
            key = (row['game'], row['sourceIdentity'], gate.text_key(row['text']))
            if key in seen:
                continue
            seen.add(key); out.append(row)
    out.sort(key=lambda x: (x['game'], x['sourceIdentity'], x['origin'], gate.text_key(x['text'])))
    for i, row in enumerate(out, 1):
        row['observationId'] = f'e{i}'
    return out


def timeline_summary(rows):
    usable = []
    for row in rows:
        sig = row.get('signals') or {}
        if sig.get('progressPairs') or sig.get('deadlineDays'):
            usable.append(row)
    identities = sorted({r['sourceIdentity'] for r in usable})
    progress = []
    deadlines = []
    seen_progress = set(); seen_deadlines = set()
    for row in usable:
        sig = row['signals']
        for pair in sig.get('progressPairs') or []:
            key = (row['sourceIdentity'], pair['day'], pair['level'])
            if key in seen_progress: continue
            seen_progress.add(key)
            progress.append({'sourceIdentity':row['sourceIdentity'],'url':row['url'],'day':pair['day'],'level':pair['level'],'observationId':row['observationId']})
        for days in sig.get('deadlineDays') or []:
            levels = sig.get('deadlineTargetLevels') or []
            key = (row['sourceIdentity'], days, tuple(levels))
            if key in seen_deadlines: continue
            seen_deadlines.add(key)
            deadlines.append({'sourceIdentity':row['sourceIdentity'],'url':row['url'],'deadlineDays':days,'levels':levels,'observationId':row['observationId']})
    progress.sort(key=lambda x:(x['day'],x['level'],x['sourceIdentity']))
    deadlines.sort(key=lambda x:(x['deadlineDays'],x['sourceIdentity']))
    return {
        'independentSourceCount': len(identities),
        'independentSources': identities,
        'progressExamples': progress,
        'offerDeadlineExamples': deadlines,
        'usableAsAnecdotalSection': len(identities) >= 2 and bool(progress or deadlines),
        'notice': '達成日数・進捗はプレイヤーごとの実体験例です。現在の案件条件や標準達成日数を示す確定値ではありません。',
    }


def tactic_summary(rows):
    kept = [r for r in rows if r.get('hasTacticSignal')]
    identities = sorted({r['sourceIdentity'] for r in kept})
    return {
        'independentSourceCount': len(identities),
        'independentSources': identities,
        'examples': [
            {'observationId':r['observationId'],'sourceIdentity':r['sourceIdentity'],'url':r['url'],'text':r['text']}
            for r in kept
        ],
        'usableAsAnecdotalSection': bool(kept),
        'notice': '単独ソースの工夫・失敗談は体験例としてのみ扱い、一般攻略の確定事実には昇格させません。',
    }


def factual_priority_available(v53_doc, game):
    for row in v53_doc.get('supportedClaims') or []:
        if row.get('game') == game and row.get('category') in {'priority','tip'} and row.get('status') == 'supported_quarantine':
            return True
    return False


def build_game_package(game, observations, v53_doc):
    timeline = timeline_summary(observations)
    tactics = tactic_summary(observations)
    factual_priority = factual_priority_available(v53_doc, game)
    x_complete = False
    for draft in v53_doc.get('drafts') or []:
        if draft.get('game') == game:
            x_complete = bool((draft.get('xTwitterResearch') or {}).get('complete'))
            break
    gaps = []
    if not factual_priority: gaps.append('複数ソースで裏取り済みの優先攻略')
    if not timeline['usableAsAnecdotalSection']: gaps.append('複数の独立した達成ペース体験')
    if not tactics['usableAsAnecdotalSection']: gaps.append('詰まり・資源管理の実体験')
    if not x_complete: gaps.append('X体験調査の完了')
    return {
        'game': game,
        'verifiedFactsRemainInV53': True,
        'experienceTimeline': timeline,
        'experienceTactics': tactics,
        'offerConditionPolicy': {
            'status': 'dynamic_not_inferred_from_anecdotes',
            'message': '案件条件は時期・ポイントサイトで変わるため、Xや過去ブログから現在条件を確定しません。公開時は現在の検証済み案件データを参照します。',
        },
        'researchReadyForArticleWriting': not gaps,
        'researchGaps': gaps,
        'publicationEligible': False,
    }


def run(decision_doc=None, claims_doc=None, v53_doc=None):
    decision_doc = decision_doc or json.loads(DECISIONS.read_text(encoding='utf-8'))
    claims_doc = claims_doc or json.loads(CLAIMS.read_text(encoding='utf-8'))
    v53_doc = v53_doc or json.loads(V53_DRAFT.read_text(encoding='utf-8'))
    if not isinstance(claims_doc, dict) or claims_doc.get('phase') != 'PHASE4_GUIDE_CLAIMS_CORROBORATED_V52':
        raise RuntimeError('corroborated claims phase mismatch')
    if not isinstance(v53_doc, dict) or v53_doc.get('phase') != 'PHASE4_POI_GUIDE_DRAFT_V53':
        raise RuntimeError('V53 draft phase mismatch')
    held = anecdotal_claims(decision_doc, claims_doc)
    x_rows = x_observations(v53_doc)
    observations = merge_observations(held, x_rows)
    games = sorted({r['game'] for r in observations} | {d.get('game') for d in v53_doc.get('drafts') or [] if d.get('game')})
    packages = [build_game_package(game, [r for r in observations if r['game']==game], v53_doc) for game in games]
    return {
        'phase': 'PHASE4_POI_GUIDE_EXPERIENCE_V54',
        'logicVersion': LOGIC_VERSION,
        'generatedAt': now_iso(),
        'publicationWrites': 0,
        'apiCalls': 0,
        'observations': observations,
        'games': packages,
    }


def summarize(result):
    games = result.get('games') or []
    obs = result.get('observations') or []
    return {
        'phase': result.get('phase'),
        'logicVersion': LOGIC_VERSION,
        'success': True,
        'games': len(games),
        'experienceObservations': len(obs),
        'independentExperienceSources': len({r.get('sourceIdentity') for r in obs if r.get('sourceIdentity')}),
        'timelineReadyGames': sum(bool((g.get('experienceTimeline') or {}).get('usableAsAnecdotalSection')) for g in games),
        'tacticReadyGames': sum(bool((g.get('experienceTactics') or {}).get('usableAsAnecdotalSection')) for g in games),
        'articleResearchReadyGames': sum(bool(g.get('researchReadyForArticleWriting')) for g in games),
        'apiCalls': 0,
        'publicationWrites': 0,
        'lastRun': result.get('generatedAt'),
    }


def main():
    try:
        result = run()
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        status = summarize(result)
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(status, ensure_ascii=False))
    except Exception as exc:
        status = {
            'phase':'PHASE4_POI_GUIDE_EXPERIENCE_V54','logicVersion':LOGIC_VERSION,'success':False,
            'error':f'{type(exc).__name__}: {str(exc)[:180]}','apiCalls':0,'publicationWrites':0,'lastRun':now_iso(),
        }
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(status, ensure_ascii=False)); raise


if __name__ == '__main__':
    main()
