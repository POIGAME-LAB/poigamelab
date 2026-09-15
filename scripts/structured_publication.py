"""Deterministic publication of complete, current first-party StepUp snapshots.

This is a separate policy from the older exact-baseline date-only approval.
It never renews those approvals or treats listing hints as verified offers.
Only parsers with complete step tables and complete terms are supported.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import direct_offer_refresh as direct


class Hold(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Hold(reason)


def snapshot(item, sources, checked_at, rate_confirmed=False):
    """Return a publication-ready value derived from evidence, or a hold reason."""
    sid = item.get("source")
    expected = {"warau": "warau-stepup-v1", "chobirich": "chobirich-numbered-stepup-v1"}
    require(sid in expected and sid in sources, "unsupported_source_contract")
    e = item.get("sourceEvidence") or item.get("evidence") or {}
    require(item.get("checkedAt") == checked_at, "not_current_scan")
    require(e.get("state") == "parsed" and e.get("parserVersion") == expected[sid], "incomplete_parser_contract")
    require(not e.get("downstreamTermsRequired"), "downstream_terms_required")
    url = item.get("url") or ""
    require(direct.source_host_allowed(url, sources[sid]), "unregistered_url")
    identity = direct.warau_offer_id if sid == "warau" else direct.chobirich_offer_id
    require(identity(url) == e.get("offerId"), "offer_identity_mismatch")
    require(e.get("platform") in {"iOS", "Android"}, "platform_missing")
    require(not e.get("providerCandidates"), "ambiguous_provider")
    require(not e.get("providerId") and not any(s in str(e.get("name", "")).casefold()
            for s in ("skyflag", "smaad", "mychips")), "provider_contract_not_supported")
    fields = ["offerId", "name", "platform", "rewardPoints", "rewardUnit", "steps", "termsText"]
    if sid == "chobirich":
        fields.append("observedRewardYen")
    require(all(k in e for k in fields), "missing_snapshot_fields")
    fingerprint = hashlib.sha256(json.dumps({k: e[k] for k in fields}, ensure_ascii=False,
                                             sort_keys=True).encode()).hexdigest()
    require(fingerprint == e.get("evidenceFingerprint"), "evidence_fingerprint_mismatch")
    require(e["rewardUnit"] == "pt", "unknown_reward_unit")
    points = e["rewardPoints"]
    require(type(points) is int and points > 0, "invalid_reward")
    if sid == "warau":
        require(rate_confirmed, "current_exchange_rate_unconfirmed")
    else:
        require(type(e["observedRewardYen"]) is int and e["observedRewardYen"] == points,
                "yen_point_mismatch")
    steps = e["steps"]
    require(isinstance(steps, list) and 1 <= len(steps) <= 100, "invalid_steps")
    require(all(isinstance(s, dict) and isinstance(s.get("condition"), str)
                and len(s["condition"].strip()) >= 4 and type(s.get("rewardPoints")) is int
                and s["rewardPoints"] >= 0 for s in steps), "invalid_step")
    require(len({s["condition"] for s in steps}) == len(steps), "duplicate_step")
    require(sum(s["rewardPoints"] for s in steps) == points, "step_total_mismatch")
    terms = e["termsText"]
    require(isinstance(terms, str) and 0 < len(terms) <= 20000, "missing_or_oversize_terms")
    markers = ("獲得条件", "獲得対象外", "注意事項") if sid == "warau" else (
        "成果受付期限", "成果調査受付期限", "条件達成に関する注意事項", "却下条件")
    require(all(m in terms for m in markers), "incomplete_terms")
    require(bool(re.search(r"[0-9]+\s*日以内", terms + " ".join(s["condition"] for s in steps))),
            "achievement_deadline_not_explicit")
    # Preserve the source's achievement text. Do not invent a shortened deadline
    # or omit paid steps while advertising the full reward.
    if sid == "warau":
        require(terms.index("獲得条件") < terms.index("獲得対象外"), "invalid_terms_order")
        achievement = terms.split("獲得対象外", 1)[0].split("獲得条件", 1)[1].strip()
    else:
        achievement = terms.split("成果受付期限", 1)[0].strip()
    require(bool(achievement), "missing_achievement_text")
    condition = terms + " / " + " / ".join(s["condition"] for s in steps)
    require(len(condition) <= 8000, "oversize_condition")
    return {"reward": str(points), "condition": condition,
            "deadline": "条件欄の各ステップ期限を参照", "platform": e["platform"],
            "type": "StepUp", "updatedAt": datetime.fromisoformat(checked_at).astimezone(
                timezone(timedelta(hours=9))).date().isoformat(),
            "sourceUrl": url, "verified": "true"}


def prepare(rows, evidence_items, sources, checked_at, policy, rate_confirmed=False):
    """Merge valid changed snapshots; retain each failed/ambiguous existing row."""
    output = copy.deepcopy(rows)
    enabled = policy.get("enabled") is True
    allowed = policy.get("sources") or []
    by_key = defaultdict(list)
    for item in evidence_items:
        key = (item.get("game"), item.get("source"), direct.offer_identity_key(item.get("url"), item.get("source")))
        by_key[key].append(item)
    duplicate_keys = Counter(r.get("offerKey") for r in rows)
    duplicate_identities = Counter((r.get("game"), r.get("site"), direct.offer_identity_key(r.get("url"), r.get("site"))) for r in rows)
    decisions = []
    for row in output:
        sid = row.get("site")
        key = (row.get("game"), sid, direct.offer_identity_key(row.get("url"), sid))
        if not enabled or sid not in allowed:
            continue
        decision = {"offerKey": row.get("offerKey"), "game": row.get("game"), "source": sid, "updated": False}
        try:
            require(duplicate_keys[row.get("offerKey")] == 1 and duplicate_identities[key] == 1,
                    "ambiguous_published_identity")
            require(row.get("verified") == "true" and row.get("type") == "StepUp", "unsupported_published_row")
            require(not row.get("provider"), "provider_contract_not_supported")
            items = by_key[key]
            require(bool(items), "no_current_evidence")
            candidates = []
            for item in items:
                update = snapshot(item, sources, checked_at, rate_confirmed)
                require(update["platform"] == row.get("platform"), "platform_changed")
                require(direct.target_present((item.get("sourceEvidence") or {}).get("name", ""), [row["game"]]),
                        "game_identity_changed")
                candidates.append(update)
            require(all(u == candidates[0] for u in candidates), "conflicting_current_evidence")
            update = candidates[0]
            decision["rewardChanged"] = row.get("reward") != update["reward"]
            decision["conditionChanged"] = row.get("condition") != update["condition"]
            decision["updated"] = any(row.get(k) != v for k, v in update.items())
            row.update(update)
        except (Hold, ValueError, TypeError, KeyError) as exc:
            decision["holdReason"] = str(exc) if isinstance(exc, Hold) else "invalid_snapshot"
        decisions.append(decision)
    return output, {"mode": "structured_stepup_publication_v1", "apiCalls": 0,
                    "updatedRows": sum(d["updated"] for d in decisions),
                    "rewardChanges": sum(d.get("rewardChanged", False) for d in decisions),
                    "heldRows": sum("holdReason" in d for d in decisions), "decisions": decisions}
