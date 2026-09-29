"""Offer URLs that passed the strict existing-game gate, kept for rechecking.

config/game_targets.json holds hand-reviewed URLs only. This file is the
machine-maintained counterpart: every offer the strict gate found
publication-eligible is remembered here so the next nightly refresh opens it
again even when it has dropped off the first listing pages. Registering a URL
never publishes anything; each fetch still has to pass the same gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import direct_offer_refresh as direct

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data" / "verified_offer_urls.json"


def load(path=PATH):
    """Return the entry list. A missing file is empty; a corrupt one raises."""
    path = Path(path)
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        raise ValueError("verified_offer_urls_invalid")
    return entries


def register(entries, decisions, checked_at):
    """Add or refresh every publication-eligible decision. Returns (entries, changed)."""
    out = [dict(e) for e in entries]
    index = {(e.get("game"), e.get("source"), e.get("identity")): e for e in out}
    changed = False
    for d in decisions or []:
        if d.get("publicationEligible") is not True or "holdReason" in d:
            continue
        game, source, url = d.get("game"), d.get("source"), d.get("url")
        identity = direct.offer_identity_key(url, source) if url and source else None
        if not (game and identity and identity == d.get("identity")):
            continue
        entry = index.get((game, source, identity))
        if entry is None:
            entry = {"game": game, "source": source, "identity": identity, "url": url,
                     "firstVerifiedAt": checked_at, "lastVerifiedAt": checked_at}
            out.append(entry)
            index[(game, source, identity)] = entry
            changed = True
        elif entry.get("lastVerifiedAt") != checked_at or entry.get("url") != url:
            entry.update(url=url, lastVerifiedAt=checked_at)
            changed = True
    out.sort(key=lambda e: (e["game"], e["source"], e["identity"]))
    return out, changed


def save(entries, path=PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    doc = {"schemaVersion": 1, "entries": entries}
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def merge_into_targets(targets, entries):
    """Add remembered URLs to each target's known URLs (in memory only)."""
    by_game = {t.get("game"): t for t in targets}
    for e in entries:
        target = by_game.get(e.get("game"))
        source, url = e.get("source"), e.get("url")
        if target is None or not source or not url:
            continue
        known = target.setdefault("known_urls_by_source", {}).setdefault(source, [])
        have = {direct.offer_identity_key(u, source) for u in known}
        if direct.offer_identity_key(url, source) not in have:
            known.append(url)
    return targets
