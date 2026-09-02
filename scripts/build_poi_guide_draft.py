#!/usr/bin/env python3
"""PHASE 4 V53: poikatsu-oriented guide draft research, quarantine only.

V53 consumes only V51 `supported_quarantine` decisions as factual article
material. It additionally performs bounded X (Twitter) discovery for public
player-experience posts. Search snippets are discovery-only: an X result is
kept only when the status page itself can be directly fetched and contains the
target game plus poikatsu/achievement language.

X posts remain explicitly anecdotal and can never become verified factual
claims in this stage. The generated draft is a deterministic research draft,
not public copy, and no production game/site file is modified.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import collect_guide_evidence as collector
import evaluate_guide_claims as gate

DECISIONS = ROOT / 'data' / 'guide_claim_decisions.json'
CLAIMS = ROOT / 'data' / 'guide_claims_corroborated.json'
CONFIG = ROOT / 'config' / 'guide_research.json'
TARGETS = ROOT / 'config' / 'game_targets.json'
OUT = ROOT / 'data' / 'poi_guide_draft.json'
STATUS = ROOT / 'data' / 'poi_guide_draft_status.json'
LOGIC_VERSION = 'V53'

X_HOSTS = {'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com', 'mobile.twitter.com'}
X_BLOCKED_USERS = {'i', 'intent', 'share', 'home', 'search', 'explore', 'settings'}
POI_MARKERS = (
    'ポイ活', '案件', '達成', 'ポイント', 'レベル', 'lv', '無課金', '課金',
    '日目', '日で', '期限', 'クリア', '報酬',
)
SECTION_BY_CATEGORY = {
    'requirement': '案件条件に関係する裏取り済み情報',
    'timeline': '達成ペース・期限に関係する裏取り済み情報',
    'priority': '案件達成で優先したい裏取り済み情報',
    'tip': '案件達成に使える裏取り済み攻略',
    'resource': '資源・時短に関する裏取り済み情報',
    'warning': '詰まり・失敗回避に関する裏取り済み情報',
    'mechanic': '案件攻略に関係するゲーム仕様',
}


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def normalize_x_status_url(url):
    """Return a stable x.com status URL or empty string for non-status URLs."""
    try:
        p = urlparse(str(url or '').strip())
    except Exception:
        return ''
    host = (p.hostname or '').lower().rstrip('.')
    if p.scheme not in {'http', 'https'} or host not in X_HOSTS:
        return ''
    m = re.fullmatch(r'/([^/]+)/status/(\d+)(?:/.*)?', p.path or '')
    if not m:
        return ''
    user, status_id = m.group(1), m.group(2)
    if user.casefold() in X_BLOCKED_USERS:
        return ''
    return f'https://x.com/{user}/status/{status_id}'


def x_source_identity(url):
    normalized = normalize_x_status_url(url)
    if not normalized:
        return ''
    user = urlparse(normalized).path.split('/')[1].casefold()
    return f'x:{user}'


def experience_relevant(text):
    low = str(text or '').casefold()
    return any(marker.casefold() in low for marker in POI_MARKERS)


class _XMetaDescriptionParser(HTMLParser):
    # Collect only post-description metadata from a directly fetched X page.
    ALLOWED_KEYS = {'og:description', 'twitter:description'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.descriptions = []

    def handle_starttag(self, tag, attrs):
        if str(tag or '').casefold() != 'meta':
            return
        values = {
            str(key or '').casefold(): str(value or '')
            for key, value in attrs
            if key
        }
        marker = (values.get('property') or values.get('name') or '').casefold()
        if marker not in self.ALLOWED_KEYS:
            return
        content = re.sub(r'\s+', ' ', values.get('content', '')).strip()
        if content and content not in self.descriptions:
            self.descriptions.append(content)


def x_meta_descriptions(raw):
    parser = _XMetaDescriptionParser()
    try:
        parser.feed(str(raw or ''))
        parser.close()
    except Exception:
        return []
    return parser.descriptions


def x_direct_post_text(raw, aliases):
    # One directly fetched lane must independently pass both safety checks.
    visible = collector.visible_text(raw)
    if collector.target_in_text(visible, aliases) and experience_relevant(visible):
        return visible, 'visible'

    meta_rows = x_meta_descriptions(raw)
    for meta_text in meta_rows:
        if collector.target_in_text(meta_text, aliases) and experience_relevant(meta_text):
            return meta_text, 'meta'

    # Preserve existing diagnostics while failing closed.
    if collector.target_in_text(visible, aliases):
        return visible, 'none'
    for meta_text in meta_rows:
        if collector.target_in_text(meta_text, aliases):
            return meta_text, 'none'
    return visible or (meta_rows[0] if meta_rows else ''), 'none'


def bounded_excerpt(text, aliases, limit=420):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not text:
        return ''
    low = text.casefold()
    needles = [str(x).strip().casefold() for x in aliases if str(x).strip()]
    needles += [x.casefold() for x in POI_MARKERS]
    positions = [low.find(n) for n in needles if n and low.find(n) >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - 110)
    end = min(len(text), start + max(80, min(600, int(limit))))
    if end - start < limit and end == len(text):
        start = max(0, end - limit)
    excerpt = text[start:end].strip()
    if start > 0:
        excerpt = '…' + excerpt
    if end < len(text):
        excerpt += '…'
    return excerpt


def target_map(targets):
    out = {}
    for row in targets.get('games') or []:
        game = str((row or {}).get('game') or '').strip()
        if not game:
            continue
        aliases = list(dict.fromkeys([game] + [str(x).strip() for x in (row.get('aliases') or []) if str(x).strip()]))
        out[game] = aliases
    return out


def supported_facts(decision_doc, claims_doc):
    """Return only supported decisions that are present in the corroborated artifact."""
    claim_rows = claims_doc.get('claims') if isinstance(claims_doc, dict) else []
    claim_rows = claim_rows if isinstance(claim_rows, list) else []
    corroborated = {}
    for row in claim_rows:
        if not isinstance(row, dict) or row.get('status') != 'validated_quarantine':
            continue
        game = str(row.get('game') or '').strip()
        category = str(row.get('category') or '').strip()
        claim = re.sub(r'\s+', ' ', str(row.get('claim') or '')).strip()
        url = str(row.get('url') or '').strip()
        source_type = str(row.get('sourceType') or '').strip()
        if not game or category not in SECTION_BY_CATEGORY or len(claim) < 4 or not gate.source_site(url):
            continue
        key = (game, category, gate.text_key(claim))
        corroborated.setdefault(key, []).append({'url': url, 'sourceType': source_type})

    rows = decision_doc.get('decisions') if isinstance(decision_doc, dict) else []
    rows = rows if isinstance(rows, list) else []
    kept = []
    for row in rows:
        if not isinstance(row, dict) or row.get('status') != 'supported_quarantine':
            continue
        game = str(row.get('game') or '').strip()
        category = str(row.get('category') or '').strip()
        claim = re.sub(r'\s+', ' ', str(row.get('claim') or '')).strip()
        key = (game, category, gate.text_key(claim))
        evidence = corroborated.get(key) or []
        if not game or category not in SECTION_BY_CATEGORY or len(claim) < 4 or not evidence:
            continue
        sites = sorted({gate.source_site(x['url']) for x in evidence if gate.source_site(x['url'])})
        official_sites = sorted({gate.source_site(x['url']) for x in evidence if x['sourceType'] == 'official' and gate.source_site(x['url'])})
        # Re-apply the V51 support invariant rather than trusting a stale decision label.
        if not official_sites and len(sites) < 2:
            continue
        urls = sorted({x['url'] for x in evidence})
        kept.append({
            'game': game,
            'category': category,
            'claim': claim,
            'sourceUrls': urls,
            'independentSourceCount': len(sites),
            'officialSourceCount': len(official_sites),
            'status': 'supported_quarantine',
        })
    kept.sort(key=lambda x: (x['game'], x['category'], gate.text_key(x['claim'])))
    for i, row in enumerate(kept, 1):
        row['claimId'] = f'c{i}'
    return kept

def x_queries(game, aliases, cfg):
    templates = cfg.get('xQueryTemplates') or [
        'site:x.com "{game}" ゲーム ポイ活',
        'site:x.com "{alias}" ポイ活 達成 日数',
    ]
    alias = next((a for a in aliases if a.casefold() != game.casefold()), game)
    max_searches = max(1, min(4, int(cfg.get('maxPoiXSearchesPerGame', 2))))
    queries = []
    for tmpl in templates[:max_searches]:
        q = str(tmpl).replace('{game}', game).replace('{alias}', alias).strip()
        if q and q not in queries:
            queries.append(q)
    return queries


def collect_x_experiences(game, aliases, cfg, api_key, searcher=collector.tavily_search, fetcher=collector.direct_fetch):
    max_results = max(1, min(8, int(cfg.get('maxPoiXResultsPerSearch', 5))))
    max_fetches = max(1, min(8, int(cfg.get('maxPoiXDirectFetchesPerGame', 4))))
    diag = {
        'game': game, 'xSearchCalls': 0, 'xSearchErrors': 0, 'xMalformedSearchResponses': 0,
        'xResultUrls': 0, 'xEligibleStatusUrls': 0, 'xDirectFetches': 0, 'xFetchErrors': 0,
        'xTargetMissing': 0, 'xPoiContextMissing': 0, 'xDuplicateUrls': 0,
        'xDuplicateAccounts': 0, 'xExperienceCandidates': 0,
        'xMetaDescriptionFallbacks': 0,
    }
    queries = x_queries(game, aliases, cfg)
    buckets = [[] for _ in queries]
    seen_urls = set()
    # Discovery comes first for every query. Snippets/titles are intentionally discarded.
    for qi, query in enumerate(queries):
        diag['xSearchCalls'] += 1
        try:
            response = searcher(query, api_key, max_results)
        except Exception:
            diag['xSearchErrors'] += 1
            continue
        if not isinstance(response, dict) or not isinstance(response.get('results'), list):
            diag['xMalformedSearchResponses'] += 1
            continue
        results = response.get('results') or []
        diag['xResultUrls'] += len(results)
        for item in results:
            url = normalize_x_status_url((item or {}).get('url') if isinstance(item, dict) else '')
            if not url:
                continue
            if url in seen_urls:
                diag['xDuplicateUrls'] += 1
                continue
            seen_urls.add(url)
            diag['xEligibleStatusUrls'] += 1
            buckets[qi].append(url)

    # Round-robin the direct-fetch budget so the first query cannot starve later aliases.
    fetch_order = []
    depth = 0
    while any(depth < len(b) for b in buckets):
        for bucket in buckets:
            if depth < len(bucket):
                fetch_order.append(bucket[depth])
        depth += 1

    candidates = []
    seen_accounts = set()
    for url in fetch_order:
        if diag['xDirectFetches'] >= max_fetches:
            break
        identity = x_source_identity(url)
        if identity in seen_accounts:
            diag['xDuplicateAccounts'] += 1
            continue
        diag['xDirectFetches'] += 1
        try:
            raw, _meta = fetcher(url)
            text, text_source = x_direct_post_text(raw, aliases)
        except Exception:
            diag['xFetchErrors'] += 1
            continue
        if text_source == 'meta':
            diag['xMetaDescriptionFallbacks'] += 1
        if not collector.target_in_text(text, aliases):
            diag['xTargetMissing'] += 1
            continue
        if not experience_relevant(text):
            diag['xPoiContextMissing'] += 1
            continue
        excerpt = bounded_excerpt(text, aliases)
        if not excerpt:
            diag['xPoiContextMissing'] += 1
            continue
        seen_accounts.add(identity)
        candidates.append({
            'game': game,
            'url': url,
            'sourceIdentity': identity,
            'excerpt': excerpt,
            'evidenceLevel': 'single_public_post_anecdote',
            'usableAsFactualClaim': False,
            'status': 'anecdotal_quarantine',
            'retrievedAt': now_iso(),
        })
        diag['xExperienceCandidates'] += 1
    candidates.sort(key=lambda x: (x['sourceIdentity'], x['url']))
    for i, row in enumerate(candidates, 1):
        row['experienceId'] = f'x{i}'
    return candidates, diag

def coverage_for(facts):
    cats = {x['category'] for x in facts}
    coverage = {
        'requirement': 'requirement' in cats,
        'timeline': 'timeline' in cats,
        'priorityOrTip': bool(cats & {'priority', 'tip'}),
        'warningOrResource': bool(cats & {'warning', 'resource'}),
        'mechanic': 'mechanic' in cats,
    }
    gaps = []
    if not coverage['requirement']:
        gaps.append('案件条件')
    if not coverage['timeline']:
        gaps.append('達成日数・期限から逆算した進捗')
    if not coverage['priorityOrTip']:
        gaps.append('最優先行動・経験値効率')
    if not coverage['warningOrResource']:
        gaps.append('詰まりポイント・資源管理')
    return coverage, gaps


def build_game_draft(game, facts, x_rows, x_diag):
    sections = []
    by_heading = {}
    for fact in facts:
        heading = SECTION_BY_CATEGORY[fact['category']]
        by_heading.setdefault(heading, []).append({
            'claimId': fact['claimId'],
            'text': fact['claim'],
            'category': fact['category'],
            'sourceUrls': fact['sourceUrls'],
            'evidenceLevel': 'supported_quarantine',
        })
    for heading in SECTION_BY_CATEGORY.values():
        if heading in by_heading:
            sections.append({'heading': heading, 'items': by_heading[heading]})
    coverage, gaps = coverage_for(facts)
    x_status = 'direct_posts_available' if x_rows else (
        'searched_but_no_directly_verified_posts' if x_diag.get('xSearchCalls') else 'not_searched'
    )
    x_research_complete = bool(x_diag.get('xSearchCalls')) and not x_diag.get('xSearchErrors') and not x_diag.get('xMalformedSearchResponses')
    return {
        'game': game,
        'title': f'{game} ポイ活攻略｜案件達成のための裏取り済み調査メモ',
        'purpose': 'ポイ活案件の条件達成を期限内に進めるための攻略調査',
        'editorialRule': 'verified sections use only supported_quarantine claims; X posts are anecdotal and separate',
        'intro': 'ポイ活案件の条件達成を目的に、複数の独立ソースまたは公式情報で裏取りできた内容だけを確定情報として整理しています。',
        'verifiedSections': sections,
        'xTwitterResearch': {
            'status': x_status,
            'searched': bool(x_diag.get('xSearchCalls')),
            'complete': x_research_complete,
            'directVerificationDegraded': bool(x_diag.get('xFetchErrors')),
            'notes': x_rows,
            'notice': 'X（Twitter）の投稿は個人の体験談候補です。単独投稿の数値や攻略法を確定事実として本文へ昇格させません。',
        },
        'coverage': coverage,
        'researchGaps': gaps,
        'draftReady': len(facts) >= 4 and not gaps and x_research_complete,
        'publicationEligible': False,
    }


def run(decision_doc=None, claims_doc=None, cfg=None, targets=None, api_key=None,
        searcher=collector.tavily_search, fetcher=collector.direct_fetch):
    decision_doc = decision_doc or load_json(DECISIONS)
    # Read/validate the corroborated-claims artifact even though factual text is
    # taken from V51 decisions. This keeps the production stage tied to the
    # post-corroboration dataset and fail-visible if the wrong artifact is used.
    claims_doc = claims_doc or load_json(CLAIMS)
    if not isinstance(claims_doc, dict) or claims_doc.get('phase') != 'PHASE4_GUIDE_CLAIMS_CORROBORATED_V52':
        raise RuntimeError('corroborated claims phase mismatch')
    cfg = cfg or load_json(CONFIG)
    targets = targets or load_json(TARGETS)
    api_key = api_key if api_key is not None else os.getenv('TAVILY_API_KEY', '')
    if not api_key:
        raise RuntimeError('TAVILY_API_KEY unavailable')

    facts = supported_facts(decision_doc, claims_doc)
    aliases_by_game = target_map(targets)
    games_from_decisions = sorted({str((d or {}).get('game') or '').strip() for d in (decision_doc.get('decisions') or []) if str((d or {}).get('game') or '').strip()})
    max_games = max(1, min(5, int(cfg.get('maxGamesPerRun', 1))))
    games = [g for g in games_from_decisions if g in aliases_by_game][:max_games]

    drafts = []
    experiences = []
    diagnostics = []
    for game in games:
        game_facts = [x for x in facts if x['game'] == game]
        x_rows, x_diag = collect_x_experiences(game, aliases_by_game[game], cfg, api_key, searcher=searcher, fetcher=fetcher)
        experiences.extend(x_rows)
        diagnostics.append(x_diag)
        drafts.append(build_game_draft(game, game_facts, x_rows, x_diag))

    return {
        'phase': 'PHASE4_POI_GUIDE_DRAFT_V53',
        'logicVersion': LOGIC_VERSION,
        'generatedAt': now_iso(),
        'publicationWrites': 0,
        'apiCalls': sum(int(d.get('xSearchCalls') or 0) for d in diagnostics),
        'supportedClaims': facts,
        'xExperiences': experiences,
        'drafts': drafts,
        'diagnostics': diagnostics,
    }


def summarize(result):
    diagnostics = result.get('diagnostics') or []
    return {
        'phase': result.get('phase'),
        'logicVersion': LOGIC_VERSION,
        'success': True,
        'games': len(result.get('drafts') or []),
        'supportedClaims': len(result.get('supportedClaims') or []),
        'xSearchCalls': sum(int(d.get('xSearchCalls') or 0) for d in diagnostics),
        'xDirectFetches': sum(int(d.get('xDirectFetches') or 0) for d in diagnostics),
        'xExperienceCandidates': len(result.get('xExperiences') or []),
        'xMetaDescriptionFallbacks': sum(int(d.get('xMetaDescriptionFallbacks') or 0) for d in diagnostics),
        'xSearchErrors': sum(int(d.get('xSearchErrors') or 0) for d in diagnostics),
        'xFetchErrors': sum(int(d.get('xFetchErrors') or 0) for d in diagnostics),
        'draftReadyGames': sum(bool(d.get('draftReady')) for d in (result.get('drafts') or [])),
        'xResearchCompleteGames': sum(bool((d.get('xTwitterResearch') or {}).get('complete')) for d in (result.get('drafts') or [])),
        'publicationWrites': 0,
        'apiCalls': int(result.get('apiCalls') or 0),
        'lastRun': result.get('generatedAt'),
    }


def main():
    try:
        result = run()
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        status = summarize(result)
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(status, ensure_ascii=False))
    except Exception as exc:
        status = {
            'phase': 'PHASE4_POI_GUIDE_DRAFT_V53', 'logicVersion': LOGIC_VERSION,
            'success': False, 'error': collector.safe_error(exc),
            'publicationWrites': 0, 'lastRun': now_iso(),
        }
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(status, ensure_ascii=False))
        raise


if __name__ == '__main__':
    main()
