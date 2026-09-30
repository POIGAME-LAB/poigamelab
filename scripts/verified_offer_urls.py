"""Offer URLs that passed the strict existing-game gate, kept for rechecking.

config/game_targets.json holds hand-reviewed URLs only. This file is the
machine-maintained counterpart: every offer the strict gate found
publication-eligible is remembered here so the next nightly refresh opens it
again even when it has dropped off the first listing pages. Registering a URL
never publishes anything; each fetch still has to pass the same gate.

A remembered URL is dropped only after the source page itself said the offer
ended on UNAVAILABLE_RUNS_BEFORE_REMOVAL separate nightly runs in a row. Fetch
errors, parser doubts or a run that did not open the page never count, and any
live reading of the page starts the count again.
"""
from __future__ import annotations

import json
from pathlib import Path

import direct_offer_refresh as direct

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data" / "verified_offer_urls.json"
UNAVAILABLE_RUNS_BEFORE_REMOVAL = 3


def load(path=PATH):
    """Return the entry list. A missing file is empty; a corrupt one raises."""
    return direct.load_verified_offer_urls(path)


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
            entry.pop("unavailableStreak", None)
            entry.pop("lastUnavailableAt", None)
            changed = True
    out.sort(key=lambda e: (e["game"], e["source"], e["identity"]))
    return out, changed


def _current_evidence(snapshots, checked_at):
    """This run's page readings keyed by (game, source, identity)."""
    found = {}
    for item in snapshots or []:
        if not isinstance(item, dict) or item.get("checkedAt") != checked_at:
            continue
        source = item.get("source")
        url = item.get("requestedUrl") or item.get("url")
        identity = direct.offer_identity_key(url, source) if url and source else None
        if not (item.get("game") and identity):
            continue
        found.setdefault((item["game"], source, identity), []).append(
            item.get("sourceEvidence") or {})
    return found


def retire(entries, snapshots, checked_at, runs=UNAVAILABLE_RUNS_BEFORE_REMOVAL):
    """Count explicit "offer ended" readings; drop an entry after ``runs`` in a row.

    Returns (entries, changed, removed). Only a page that the source parser read
    as ``unavailable`` counts. A run with no reading of the page (not fetched,
    fetch error) leaves the count as it is; a live reading resets it.
    """
    evidence = _current_evidence(snapshots, checked_at)
    out, removed, changed = [], [], False
    for original in entries:
        entry = dict(original)
        readings = evidence.get((entry.get("game"), entry.get("source"), entry.get("identity")))
        if readings and all(
                e.get("state") == "unavailable" and e.get("reason") == "source_offer_unavailable"
                for e in readings):
            if entry.get("lastUnavailableAt") != checked_at:
                entry["unavailableStreak"] = int(entry.get("unavailableStreak") or 0) + 1
                entry["lastUnavailableAt"] = checked_at
                changed = True
            if entry["unavailableStreak"] >= runs:
                removed.append(entry)
                changed = True
                continue
        elif readings and any(e.get("state") == "parsed" for e in readings):
            if "unavailableStreak" in entry or "lastUnavailableAt" in entry:
                entry.pop("unavailableStreak", None)
                entry.pop("lastUnavailableAt", None)
                changed = True
        out.append(entry)
    return out, changed, removed


def save(entries, path=PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    doc = {"schemaVersion": 1, "entries": entries}
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def merge_into_targets(targets, entries):
    """Add remembered URLs to each target's known URLs (in memory only)."""
    return direct.merge_verified_offer_urls(targets, entries)
