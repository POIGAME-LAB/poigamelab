#!/usr/bin/env python3
"""PHASE 4 V51: deterministic support/conflict gate for quarantined guide claims.

This stage is API-free. It never turns V50 claims into public copy. It groups only
conservatively equivalent claims, counts independent source sites, detects exact
numeric variants as conflicts, and keeps every decision in quarantine.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / 'data' / 'guide_claims.json'
OUT = ROOT / 'data' / 'guide_claim_decisions.json'
STATUS = ROOT / 'data' / 'guide_claim_decision_status.json'
ALLOWED_SOURCE_TYPES = {'official', 'community_guide'}
ALLOWED_CATEGORIES = {'requirement', 'timeline', 'priority', 'resource', 'warning', 'mechanic', 'tip'}
MULTI_LABEL_SUFFIXES = {'co.jp', 'ne.jp', 'or.jp', 'ac.jp', 'go.jp', 'co.uk', 'org.uk', 'com.au', 'net.au'}


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def text_key(value):
    s = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return ''.join(ch for ch in s if ch.isalnum())


def conflict_key(value):
    s = unicodedata.normalize('NFKC', str(value or '')).casefold()
    s = re.sub(r'\d+(?:[.,]\d+)?', '<num>', s)
    return ''.join(ch for ch in s if ch.isalnum() or ch in '<>')


def numeric_signature(value):
    s = unicodedata.normalize('NFKC', str(value or ''))
    return tuple(x.replace(',', '') for x in re.findall(r'\d+(?:[.,]\d+)?', s))


def source_site(url):
    try:
        p = urlsplit(str(url or ''))
        if p.scheme != 'https' or not p.hostname:
            return ''
        host = p.hostname.rstrip('.').lower()
    except Exception:
        return ''
    if host == 'localhost' or ':' in host or re.fullmatch(r'\d+(?:\.\d+){3}', host):
        return ''
    labels = host.split('.')
    if len(labels) < 2:
        return ''
    tail2 = '.'.join(labels[-2:])
    if tail2 in MULTI_LABEL_SUFFIXES and len(labels) >= 3:
        return '.'.join(labels[-3:])
    return tail2


def valid_claim(row):
    if not isinstance(row, dict):
        return False
    if row.get('status') != 'validated_quarantine':
        return False
    if row.get('category') not in ALLOWED_CATEGORIES or row.get('sourceType') not in ALLOWED_SOURCE_TYPES:
        return False
    if not str(row.get('game') or '').strip() or len(str(row.get('claim') or '').strip()) < 4:
        return False
    if not str(row.get('evidenceQuote') or '').strip() or not source_site(row.get('url')):
        return False
    return True


def evaluate(doc):
    rows = doc.get('claims') if isinstance(doc, dict) else []
    rows = rows if isinstance(rows, list) else []
    accepted = [r for r in rows if valid_claim(r)]
    rejected_input = len(rows) - len(accepted)

    groups = {}
    for row in accepted:
        key = (str(row['game']).strip(), row['category'], text_key(row['claim']))
        groups.setdefault(key, []).append(row)

    conflict_members = set()
    variants = {}
    for key, members in groups.items():
        exemplar = members[0]
        sig = numeric_signature(exemplar['claim'])
        if not sig:
            continue
        ckey = (key[0], key[1], conflict_key(exemplar['claim']))
        variants.setdefault(ckey, []).append((key, sig))
    conflicts = []
    for ckey, vals in variants.items():
        distinct = {sig for _, sig in vals}
        if len(distinct) <= 1:
            continue
        member_keys = [key for key, _ in vals]
        conflict_members.update(member_keys)
        conflicts.append({
            'game': ckey[0], 'category': ckey[1], 'conflictKey': ckey[2],
            'numericVariants': [list(x) for x in sorted(distinct)],
            'claimVariants': sorted({groups[k][0]['claim'] for k in member_keys}),
            'status': 'held_conflict',
        })

    decisions = []
    for key in sorted(groups):
        members = groups[key]
        sites = sorted({source_site(r['url']) for r in members})
        official_sites = sorted({source_site(r['url']) for r in members if r['sourceType'] == 'official'})
        urls = sorted({r['url'] for r in members})
        if key in conflict_members:
            status, reason = 'held_conflict', 'numeric_conflict'
        elif official_sites:
            status, reason = 'supported_quarantine', 'official_source'
        elif len(sites) >= 2:
            status, reason = 'supported_quarantine', 'independent_corroboration'
        else:
            status, reason = 'held_single_source', 'insufficient_independent_sources'
        decisions.append({
            'game': key[0], 'category': key[1], 'claim': members[0]['claim'],
            'status': status, 'reason': reason,
            'independentSourceCount': len(sites), 'independentSources': sites,
            'officialSourceCount': len(official_sites), 'sourceUrls': urls,
            'evidenceCount': len(members), 'publicationEligible': False,
        })

    counts = {
        'inputClaims': len(rows), 'validInputClaims': len(accepted), 'rejectedInputClaims': rejected_input,
        'decisionGroups': len(decisions),
        'supportedQuarantine': sum(d['status'] == 'supported_quarantine' for d in decisions),
        'heldSingleSource': sum(d['status'] == 'held_single_source' for d in decisions),
        'heldConflict': sum(d['status'] == 'held_conflict' for d in decisions),
        'conflictGroups': len(conflicts),
    }
    return {
        'phase': 'PHASE4_GUIDE_CLAIM_GATE_V51', 'generatedAt': now_iso(), 'apiCalls': 0,
        'publicationWrites': 0, 'publicationEligibleClaims': 0,
        'counts': counts, 'decisions': decisions, 'conflicts': conflicts,
    }


def main():
    try:
        result = evaluate(json.loads(IN.read_text(encoding='utf-8')))
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        status = {
            'phase': result['phase'], 'success': True, **result['counts'], 'apiCalls': 0,
            'publicationWrites': 0, 'publicationEligibleClaims': 0, 'lastRun': result['generatedAt'],
        }
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(status, ensure_ascii=False))
    except Exception as exc:
        status = {
            'phase': 'PHASE4_GUIDE_CLAIM_GATE_V51', 'success': False,
            'error': f'{type(exc).__name__}: {str(exc)[:180]}', 'apiCalls': 0,
            'publicationWrites': 0, 'publicationEligibleClaims': 0, 'lastRun': now_iso(),
        }
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(status, ensure_ascii=False))
        raise


if __name__ == '__main__':
    main()
