#!/usr/bin/env python3
"""Research high-reward new-game candidates sequentially and adopt only strict V29 passes.

This bridge connects the public new-game monitor to the existing quarantine research,
V29 deterministic adoption gate, and V30 production adopter. It is deliberately
fail-closed per candidate but fail-open for the batch: a HOLD or research failure does
not stop later candidates. Candidates are deduplicated by game, existing games are
excluded, at most 15 are researched, and the run stops after five successful adoptions.
"""
from __future__ import annotations

import csv
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import adopt_verified_games as v30
import evaluate_research_adoption as v29
import research_offer_bridge as research

ROOT = Path(__file__).resolve().parents[1]
MONITOR = ROOT / 'data/new_game_monitor.json'
GAMES = ROOT / 'games.csv'
CONFIG = ROOT / 'config/trend_discovery.json'
ADOPTION_CANDIDATES = ROOT / 'data/adoption_candidates.json'
ADOPTION_STATUS = ROOT / 'data/adoption_status.json'
BRIDGE_STATUS = ROOT / 'data/high_reward_adoption_status.json'

MAX_CANDIDATES = 15
TARGET_ADOPTIONS = 5

NON_GAME_WORDS = (
    'カード', '口座', '銀行', '証券', '通販', 'ストア', '予約', '講座', 'ウォーカー',
    'サンワダイレクト', 'trip.com', 'booking.com', '古着', 'ゴールド（nl）',
)
GAME_HINTS = (
    'ゲーム', 'game', 'puzzle', 'match', 'jigsaw', 'level', 'レベル', 'ステージ',
    'stepup', 'ミッション', 'インストール', 'アプリ', 'ポイントを獲得',
)


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def norm(text):
    return re.sub(r'[^0-9a-zぁ-んァ-ヶ一-龠]+', '', str(text or '').casefold())


def existing_games(path=GAMES):
    if not Path(path).exists():
        return set()
    with Path(path).open(encoding='utf-8', newline='') as f:
        return {norm(row.get('name')) for row in csv.DictReader(f) if row.get('name')}


def parse_reward_pt(text):
    text = str(text or '').replace('，', ',')
    values = []
    for m in re.finditer(r'(\d[\d,\s]*)\s*pt\b', text, flags=re.I):
        digits = re.sub(r'\D', '', m.group(1))
        if digits:
            values.append(int(digits))
    return max(values) if values else 0


def clean_game_name(title):
    s = str(title or '').strip()
    # Remove platform / campaign labels without erasing a legitimate title.
    s = re.sub(r'（\s*(?:iOS|Android|多段階|StepUp)\s*）', '', s, flags=re.I)
    s = re.sub(r'\(\s*(?:iOS|Android|multi[- ]?stage|stepup)\s*\)', '', s, flags=re.I)
    # Common separators between title and condition copy.
    markers = [
        ' - レベル', ' - LEVEL', ' 新規アプリ', ' 新規インストール', ' 初回アプリ',
        ' アプリDL', ' アプリダウンロード', ' マルチミッション', '（レベル', '（LEVEL',
        '（最高点数', '（30日以内', '（累計', '（StepUp',
    ]
    lower = s.casefold()
    cuts = []
    for marker in markers:
        i = lower.find(marker.casefold())
        if i > 0:
            cuts.append(i)
    if cuts:
        s = s[:min(cuts)]
    # Strip remaining terminal platform/campaign parentheses and punctuation.
    s = re.sub(r'[\s\-–—:：]+$', '', s).strip()
    return s


def looks_like_game(item):
    if item.get('classification') == 'likely_non_game':
        return False
    title = str(item.get('titleHint') or '')
    low = title.casefold()
    if any(word.casefold() in low for word in NON_GAME_WORDS):
        return False
    if item.get('classification') == 'likely_game':
        return True
    return any(h.casefold() in low for h in GAME_HINTS)


def build_candidates(monitor, games_path=GAMES, limit=MAX_CANDIDATES):
    known = existing_games(games_path)
    grouped = {}
    for item in monitor.get('items', []):
        if not looks_like_game(item):
            continue
        reward = parse_reward_pt(item.get('titleHint'))
        if reward <= 0:
            continue
        game = clean_game_name(item.get('titleHint'))
        key = norm(game)
        if not game or not key or key in known:
            continue
        row = grouped.setdefault(key, {
            'game': game,
            'aliases': [game],
            'maxRewardPt': 0,
            'sources': [],
            'sourceCandidates': [],
            'collectorReady': True,
            'status': 'collector_ready',
            'origin': 'high_reward_monitor',
        })
        row['maxRewardPt'] = max(row['maxRewardPt'], reward)
        source = item.get('source')
        if source and source not in row['sources']:
            row['sources'].append(source)
        row['sourceCandidates'].append({
            'source': source,
            'url': item.get('firstPartyCandidateUrl'),
            'titleHint': item.get('titleHint'),
            'rewardPt': reward,
        })
    rows = sorted(grouped.values(), key=lambda x: (-x['maxRewardPt'], x['game'].casefold()))
    return rows[:max(0, int(limit))]


def _adopt_one(decision, results_dir, cfg_path, status_path):
    payload = {
        'schemaVersion': 1,
        'phase': 'PHASE3_ADOPTION_GATE_V29',
        'generatedAt': now_iso(),
        'autoPublish': False,
        'autoAddGame': False,
        'summary': {'researchedGames': 1, 'adoptionReady': 1, 'held': 0},
        'items': [decision],
    }
    with tempfile.TemporaryDirectory() as d:
        adoption_path = Path(d) / 'adoption.json'
        adoption_path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        out = v30.run(
            adoptions_path=adoption_path,
            results_dir=results_dir,
            status_path=status_path,
            config_path=cfg_path,
        )
    match = next((x for x in out.get('results', []) if norm(x.get('game')) == norm(decision.get('game'))), None)
    return match or {'game': decision.get('game'), 'adopted': False, 'reasons': ['v30_result_missing']}


def run(monitor_path=MONITOR, games_path=GAMES, config_path=CONFIG,
        max_candidates=MAX_CANDIDATES, target_adoptions=TARGET_ADOPTIONS,
        research_one=research.run_one, evaluate=v29.evaluate, adopt_one=_adopt_one):
    monitor = load_json(monitor_path) if Path(monitor_path).exists() else {'items': []}
    cfg = load_json(config_path)
    candidates = build_candidates(monitor, games_path=games_path, limit=max_candidates)
    results = []
    decisions = []
    adopted = 0

    for candidate in candidates:
        if adopted >= int(target_adoptions):
            break
        game = candidate['game']
        item = dict(candidate)
        item['researchLogicVersion'] = 'high-reward-v1'
        try:
            research_result = research_one(item, env=os.environ)
        except Exception as exc:
            research_result = {'game': game, 'returncode': 99, 'resultSaved': False, 'error': type(exc).__name__}
        row = {'game': game, 'maxRewardPt': candidate['maxRewardPt'], 'research': research_result}
        slug = research.stable_slug(game)
        result_path = research.RESULTS / f'{slug}.json'
        if research_result.get('returncode') != 0 or not research_result.get('resultSaved') or not result_path.exists():
            row.update({'status': 'hold', 'reasons': ['research_failed_or_missing']})
            decisions.append({'game': game, 'eligible': False, 'status': 'hold', 'reasons': row['reasons']})
            results.append(row)
            continue

        try:
            decision = evaluate(load_json(result_path), cfg)
        except Exception as exc:
            decision = {'game': game, 'eligible': False, 'status': 'hold', 'reasons': ['v29_evaluation_error'], 'error': type(exc).__name__}
        decisions.append(decision)
        row['v29'] = decision
        if not decision.get('eligible'):
            row.update({'status': 'hold', 'reasons': decision.get('reasons') or ['v29_hold']})
            results.append(row)
            continue

        v30_status_tmp = Path(tempfile.gettempdir()) / f'poigamelab-v30-{slug}.json'
        try:
            adoption = adopt_one(decision, research.RESULTS, Path(config_path), v30_status_tmp)
        except Exception as exc:
            adoption = {'game': game, 'adopted': False, 'reasons': ['v30_adoption_error'], 'error': type(exc).__name__}
        finally:
            v30_status_tmp.unlink(missing_ok=True)
        row['v30'] = adoption
        if adoption.get('adopted'):
            adopted += 1
            row['status'] = 'adopted'
        else:
            row.update({'status': 'hold', 'reasons': adoption.get('reasons') or ['v30_hold']})
        results.append(row)

    canonical = {
        'schemaVersion': 1,
        'phase': 'PHASE3_HIGH_REWARD_V29_GATE',
        'generatedAt': now_iso(),
        'autoPublish': False,
        'autoAddGame': False,
        'summary': {
            'researchedGames': len(results),
            'adoptionReady': sum(1 for x in decisions if x.get('eligible')),
            'held': sum(1 for x in decisions if not x.get('eligible')),
        },
        'items': decisions,
    }
    atomic_json(ADOPTION_CANDIDATES, canonical)
    status = {
        'phase': 'PHASE3_HIGH_REWARD_ADOPTION_BRIDGE_V1',
        'runAt': now_iso(),
        'candidateLimit': int(max_candidates),
        'targetAdoptions': int(target_adoptions),
        'candidatesPrepared': len(candidates),
        'researched': len(results),
        'adopted': adopted,
        'held': sum(1 for x in results if x.get('status') != 'adopted'),
        'stoppedAfterTarget': adopted >= int(target_adoptions),
        'results': results,
    }
    atomic_json(ADOPTION_STATUS, status)
    atomic_json(BRIDGE_STATUS, status)
    return status


def main():
    missing = [k for k in ('GEMINI_API_KEY',) if not os.getenv(k, '').strip()]
    if missing:
        status = {
            'phase': 'PHASE3_HIGH_REWARD_ADOPTION_BRIDGE_V1',
            'runAt': now_iso(),
            'success': False,
            'error': 'missing_required_secrets',
            'missingSecretNames': missing,
        }
        atomic_json(BRIDGE_STATUS, status)
        print(json.dumps(status, ensure_ascii=False))
        return 2
    out = run(
        max_candidates=int(os.getenv('HIGH_REWARD_MAX_CANDIDATES', str(MAX_CANDIDATES))),
        target_adoptions=int(os.getenv('HIGH_REWARD_TARGET_ADOPTIONS', str(TARGET_ADOPTIONS))),
    )
    print(json.dumps({k: out[k] for k in ('candidatesPrepared', 'researched', 'adopted', 'held')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
