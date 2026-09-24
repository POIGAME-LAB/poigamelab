"""Deterministic publication of complete first-party snapshots.

Full StepUp contracts may replace reward/conditions/deadline together. Reviewed
reward-only contracts may update only the reward/date/source metadata of an
already-published row after exact offer identity, platform, unit conversion,
terms and evidence fingerprint checks. Unsupported or incomplete evidence holds.
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


FULL_SNAPSHOT_CONTRACTS = {
    "warau": {
        "parser": "warau-stepup-v1",
        "identity": direct.warau_offer_id,
    },
    "chobirich": {
        "parser": "chobirich-numbered-stepup-v1",
        "identity": direct.chobirich_offer_id,
    },
}

REWARD_ONLY_CONTRACTS = {
    "hapitas": {
        "parser": "hapitas-detail-review-v2",
        "identity": direct.hapitas_offer_id,
        "rewardField": "verifiedCurrentRewardYen",
        "fingerprintFields": [
            "offerId", "name", "platform", "platformProvenance",
            "displayedCurrentRewardPoints", "stepRewardPoints", "verifiedCurrentRewardPoints",
            "verifiedCurrentRewardYen", "rewardUnit", "sourcePointRate",
            "headerText", "termsText", "publicationAuthorized",
        ],
        "rewardUnit": "Hapitas-pt",
        "sourcePointRate": "1pt=1JPY",
        "pointField": "verifiedCurrentRewardPoints",
        "pointScale": 1,
        "termsMarkers": ("ポイント対象条件",),
    },
    "coincome": {
        "parser": "coincome-detail-review-v2",
        "identity": direct.coincome_offer_id,
        "rewardField": "displayedRewardYen",
        "fingerprintFields": [
            "offerId", "name", "offerTitle", "platform", "displayedRewardYen",
            "rewardUnit", "stepRewardYen", "stepTotalYen", "headerText", "termsText",
        ],
        "rewardUnit": "JPY-equivalent",
        "termsMarkers": ("適用端末", "キャッシュバック条件", "承認条件", "否認条件"),
    },
    "point_town": {
        "parser": "pointtown-detail-review-v2",
        "identity": direct.pointtown_offer_id,
        "rewardField": "verifiedCurrentRewardYen",
        "fingerprintFields": [
            "offerId", "name", "titleMatchProvenance", "platform", "verifiedCurrentRewardPoints",
            "verifiedCurrentRewardYen", "rewardUnit", "sourcePointRate",
            "headerText", "termsText", "publicationAuthorized",
        ],
        "rewardUnit": "PointTown-point",
        "sourcePointRate": "1pt=1JPY",
        "pointField": "verifiedCurrentRewardPoints",
        "pointScale": 1,
        "termsMarkers": ("ポイント獲得条件",),
    },
    "ec_navi": {
        "parser": "ecnavi-detail-review-v1",
        "identity": direct.ecnavi_offer_id,
        "rewardField": "verifiedCurrentRewardYen",
        "fingerprintFields": [
            "offerId", "name", "platform", "displayedPointCandidates",
            "verifiedCurrentRewardPoints", "verifiedCurrentRewardYen",
            "rewardUnit", "sourcePointRate", "headerText", "termsText",
            "publicationAuthorized",
        ],
        "rewardUnit": "ECNavi-pt",
        "sourcePointRate": "10pt=1JPY",
        "pointField": "verifiedCurrentRewardPoints",
        "pointScale": 10,
        "termsMarkers": ("加算条件", "加算時期"),
    },
    "amefuri": {
        "parser": "amefuri-detail-review-v2",
        "identity": direct.amefuri_offer_id,
        "rewardField": "verifiedCurrentRewardYen",
        "fingerprintFields": [
            "offerId", "name", "platform", "rewardMode",
            "displayedRewardYenCandidates", "displayedCurrentRewardYen",
            "conditionText", "achievementDeadlineExplicit",
            "stepRewardPoints", "stepTotalPoints", "verifiedCurrentRewardPoints",
            "verifiedCurrentRewardYen", "rewardUnit", "sourcePointRate",
            "headerText", "termsText", "publicationAuthorized",
        ],
        "rewardUnit": "JPY-equivalent",
        "sourcePointRate": "10pt=1JPY",
        "pointField": "verifiedCurrentRewardPoints",
        "pointScale": 10,
        "termsMarkers": ("ポイント獲得条件",),
    },
}


def _current_jst_date(checked_at):
    return datetime.fromisoformat(checked_at).astimezone(
        timezone(timedelta(hours=9))
    ).date().isoformat()


def _fingerprint(evidence, fields):
    require(all(key in evidence for key in fields), "missing_snapshot_fields")
    payload = {key: evidence[key] for key in fields}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def full_snapshot(item, sources, checked_at, rate_confirmed=False):
    sid = item.get("source")
    contract = FULL_SNAPSHOT_CONTRACTS.get(sid)
    require(contract is not None and sid in sources, "unsupported_source_contract")
    e = item.get("sourceEvidence") or item.get("evidence") or {}
    require(item.get("checkedAt") == checked_at, "not_current_scan")
    require(
        e.get("state") == "parsed" and e.get("parserVersion") == contract["parser"],
        "incomplete_parser_contract",
    )
    require(not e.get("downstreamTermsRequired"), "downstream_terms_required")
    url = item.get("url") or ""
    require(direct.source_host_allowed(url, sources[sid]), "unregistered_url")
    require(contract["identity"](url) == e.get("offerId"), "offer_identity_mismatch")
    require(e.get("platform") in {"iOS", "Android"}, "platform_missing")
    require(not e.get("providerCandidates"), "ambiguous_provider")
    require(
        not e.get("providerId")
        and not any(
            marker in str(e.get("name", "")).casefold()
            for marker in ("skyflag", "smaad", "mychips")
        ),
        "provider_contract_not_supported",
    )
    fields = [
        "offerId", "name", "platform", "rewardPoints", "rewardUnit",
        "steps", "termsText",
    ]
    if sid == "chobirich":
        fields.append("observedRewardYen")
    require(
        _fingerprint(e, fields) == e.get("evidenceFingerprint"),
        "evidence_fingerprint_mismatch",
    )
    require(e["rewardUnit"] == "pt", "unknown_reward_unit")
    points = e["rewardPoints"]
    require(type(points) is int and points > 0, "invalid_reward")
    if sid == "warau":
        require(rate_confirmed, "current_exchange_rate_unconfirmed")
    else:
        require(
            type(e["observedRewardYen"]) is int
            and e["observedRewardYen"] == points,
            "yen_point_mismatch",
        )
    steps = e["steps"]
    require(isinstance(steps, list) and 1 <= len(steps) <= 100, "invalid_steps")
    require(
        all(
            isinstance(step, dict)
            and isinstance(step.get("condition"), str)
            and len(step["condition"].strip()) >= 4
            and type(step.get("rewardPoints")) is int
            and step["rewardPoints"] >= 0
            for step in steps
        ),
        "invalid_step",
    )
    require(
        len({step["condition"] for step in steps}) == len(steps),
        "duplicate_step",
    )
    require(
        sum(step["rewardPoints"] for step in steps) == points,
        "step_total_mismatch",
    )
    terms = e["termsText"]
    require(
        isinstance(terms, str) and 0 < len(terms) <= 20000,
        "missing_or_oversize_terms",
    )
    markers = (
        ("獲得条件", "獲得対象外", "注意事項")
        if sid == "warau"
        else ("成果受付期限", "成果調査受付期限", "条件達成に関する注意事項", "却下条件")
    )
    require(all(marker in terms for marker in markers), "incomplete_terms")
    require(
        bool(re.search(r"[0-9]+\s*日以内", terms + " ".join(step["condition"] for step in steps))),
        "achievement_deadline_not_explicit",
    )
    if sid == "warau":
        require(
            terms.index("獲得条件") < terms.index("獲得対象外"),
            "invalid_terms_order",
        )
        achievement = terms.split("獲得対象外", 1)[0].split("獲得条件", 1)[1].strip()
    else:
        achievement = terms.split("成果受付期限", 1)[0].strip()
    require(bool(achievement), "missing_achievement_text")
    condition = terms + " / " + " / ".join(step["condition"] for step in steps)
    require(len(condition) <= 8000, "oversize_condition")
    return {
        "reward": str(points),
        "condition": condition,
        "deadline": "条件欄の各ステップ期限を参照",
        "platform": e["platform"],
        "type": "StepUp",
        "updatedAt": _current_jst_date(checked_at),
        "sourceUrl": url,
        "verified": "true",
    }


def reward_only_snapshot(item, sources, checked_at):
    sid = item.get("source")
    contract = REWARD_ONLY_CONTRACTS.get(sid)
    require(contract is not None and sid in sources, "unsupported_source_contract")
    e = item.get("sourceEvidence") or item.get("evidence") or {}
    require(item.get("checkedAt") == checked_at, "not_current_scan")
    require(
        e.get("state") == "parsed" and e.get("parserVersion") == contract["parser"],
        "incomplete_parser_contract",
    )
    require(not e.get("downstreamTermsRequired"), "downstream_terms_required")
    url = item.get("url") or ""
    require(direct.source_host_allowed(url, sources[sid]), "unregistered_url")
    require(contract["identity"](url) == e.get("offerId"), "offer_identity_mismatch")
    require(e.get("platform") in {"iOS", "Android"}, "platform_missing")
    require(
        _fingerprint(e, contract["fingerprintFields"]) == e.get("evidenceFingerprint"),
        "evidence_fingerprint_mismatch",
    )
    reward = e.get(contract["rewardField"])
    require(type(reward) is int and 0 < reward < 1_000_000, "invalid_reward")
    require(e.get("rewardUnit") == contract["rewardUnit"], "unknown_reward_unit")
    if "sourcePointRate" in contract:
        require(
            e.get("sourcePointRate") == contract["sourcePointRate"],
            "unit_conversion_review_required",
        )
    point_field = contract.get("pointField")
    if point_field:
        points = e.get(point_field)
        scale = contract.get("pointScale")
        require(
            type(points) is int and type(scale) is int and scale > 0
            and points == reward * scale,
            "yen_point_mismatch",
        )
    if sid == "hapitas":
        require(
            e.get("publicationAuthorized") is True
            and e.get("platformProvenance") in {
                "reviewed_offer_registry", "source_title"
            },
            "reviewed_platform_authorization_required",
        )
        require(e.get("displayedCurrentRewardPoints") == reward, "yen_point_mismatch")
        steps = e.get("stepRewardPoints")
        require(isinstance(steps, list), "invalid_steps")
        if steps:
            require(
                all(type(value) is int and value >= 0 for value in steps),
                "invalid_step",
            )
            require(sum(steps) == reward, "step_total_mismatch")
    elif sid == "point_town":
        require(
            not re.search(r"で\s*[0-9][0-9,]*\s+[0-9][0-9,]*(?:\s|$)",
                          str(e.get("headerText") or "")),
            "ambiguous_displayed_reward",
        )
    elif sid == "amefuri":
        require(
            e.get("displayedCurrentRewardYen") == reward,
            "displayed_reward_mismatch",
        )
        displayed = e.get("displayedRewardYenCandidates")
        require(
            isinstance(displayed, list)
            and displayed
            and reward == max(displayed),
            "displayed_reward_mismatch",
        )
        steps = e.get("stepRewardPoints")
        require(isinstance(steps, list), "invalid_steps")
        require(all(type(value) is int and value > 0 for value in steps), "invalid_step")
        mode = e.get("rewardMode")
        if mode == "StepUp":
            require(len(steps) >= 2, "invalid_steps")
            require(sum(steps) == e.get("stepTotalPoints"), "step_total_mismatch")
            require(e.get("stepTotalPoints") == reward * 10, "yen_point_mismatch")
        elif mode == "Single":
            require(steps == [] and e.get("stepTotalPoints") is None, "invalid_steps")
        else:
            raise Hold("invalid_reward_mode")
    terms = e.get("termsText")
    require(
        isinstance(terms, str) and 0 < len(terms) <= 12000,
        "missing_or_oversize_terms",
    )
    require(
        all(marker in terms for marker in contract["termsMarkers"]),
        "incomplete_terms",
    )
    # Deliberately do not rewrite condition/deadline/type from a reward-only
    # contract. Existing prose survives unless a complete publication contract
    # exists for that source.
    return {
        "reward": str(reward),
        "platform": e["platform"],
        "updatedAt": _current_jst_date(checked_at),
        "sourceUrl": url,
        "verified": "true",
    }


def snapshot(item, sources, checked_at, rate_confirmed=False):
    sid = item.get("source")
    if sid in FULL_SNAPSHOT_CONTRACTS:
        return full_snapshot(item, sources, checked_at, rate_confirmed)
    if sid in REWARD_ONLY_CONTRACTS:
        return reward_only_snapshot(item, sources, checked_at)
    raise Hold("unsupported_source_contract")


def prepare(rows, evidence_items, sources, checked_at, policy, rate_confirmed=False):
    """Merge valid current snapshots; retain each failed/ambiguous existing row."""
    output = copy.deepcopy(rows)
    enabled = policy.get("enabled") is True
    allowed = policy.get("sources") or []
    by_key = defaultdict(list)
    for item in evidence_items:
        # Discovery/candidate records are deliberately non-publication inputs.
        # They may share the same offer identity as a fully parsed snapshot, so
        # admitting them here would turn an explicit safety marker into a false
        # incomplete-parser hold for an otherwise valid current snapshot.
        evidence_records = [item.get("sourceEvidence"), item.get("evidence")]
        if (item.get("candidateOnly") is True
                or item.get("publicationAuthorized") is False
                or any(isinstance(evidence, dict)
                       and (evidence.get("publicationAuthorized") is False
                            or evidence.get("candidateOnly") is True)
                       for evidence in evidence_records)):
            continue
        key = (
            item.get("game"),
            item.get("source"),
            direct.offer_identity_key(item.get("url"), item.get("source")),
        )
        by_key[key].append(item)
    duplicate_keys = Counter(row.get("offerKey") for row in rows)
    duplicate_identities = Counter(
        (
            row.get("game"),
            row.get("site"),
            direct.offer_identity_key(row.get("url"), row.get("site")),
        )
        for row in rows
    )
    decisions = []
    retired_offer_keys = set()
    for row in output:
        sid = row.get("site")
        key = (
            row.get("game"),
            sid,
            direct.offer_identity_key(row.get("url"), sid),
        )
        if not enabled or sid not in allowed:
            continue
        decision = {
            "offerKey": row.get("offerKey"),
            "game": row.get("game"),
            "source": sid,
            "updated": False,
        }
        try:
            require(
                duplicate_keys[row.get("offerKey")] == 1
                and duplicate_identities[key] == 1,
                "ambiguous_published_identity",
            )
            require(row.get("verified") == "true", "unsupported_published_row")
            require(not row.get("provider"), "provider_contract_not_supported")
            if sid in FULL_SNAPSHOT_CONTRACTS:
                require(row.get("type") == "StepUp", "unsupported_published_row")
            items = by_key[key]
            require(bool(items), "no_current_evidence")

            # Hapitas can explicitly mark an exact first-party item page as
            # ended. Retire a published row only when the current scan contains
            # exactly one fingerprinted unavailable snapshot for the same offer
            # identity and game. Fetch/parser failures continue to hold rows.
            if sid == "hapitas":
                unavailable_items = [
                    item for item in items
                    if (item.get("sourceEvidence") or item.get("evidence") or {}).get("state")
                    == "unavailable"
                ]
                if unavailable_items:
                    require(
                        len(items) == 1 and len(unavailable_items) == 1,
                        "conflicting_current_evidence",
                    )
                    item = unavailable_items[0]
                    e = item.get("sourceEvidence") or item.get("evidence") or {}
                    require(item.get("checkedAt") == checked_at, "not_current_scan")
                    require(
                        e.get("parserVersion") == "hapitas-detail-review-v2"
                        and e.get("reason") == "source_offer_unavailable"
                        and e.get("unavailableMarker") == "この広告は終了しています",
                        "unverified_unavailable_state",
                    )
                    url = item.get("url") or ""
                    require(direct.source_host_allowed(url, sources[sid]), "unregistered_url")
                    require(
                        direct.hapitas_offer_id(url) == e.get("offerId"),
                        "offer_identity_mismatch",
                    )
                    require(
                        direct.target_present(e.get("name", ""), [row["game"]]),
                        "game_identity_changed",
                    )
                    require(
                        _fingerprint(
                            e, ["offerId", "name", "unavailableMarker"]
                        ) == e.get("evidenceFingerprint"),
                        "evidence_fingerprint_mismatch",
                    )
                    decision["publicationMode"] = "explicit_unavailable_retirement"
                    decision["retired"] = True
                    decision["updated"] = True
                    retired_offer_keys.add(row.get("offerKey"))
                    decisions.append(decision)
                    continue

            candidates = []
            for item in items:
                update = snapshot(item, sources, checked_at, rate_confirmed)
                require(
                    update.get("platform") == row.get("platform"),
                    "platform_changed",
                )
                require(
                    direct.target_present(
                        (item.get("sourceEvidence") or item.get("evidence") or {}).get("name", ""),
                        [row["game"]],
                    ),
                    "game_identity_changed",
                )
                candidates.append(update)
            require(
                all(update == candidates[0] for update in candidates),
                "conflicting_current_evidence",
            )
            update = candidates[0]
            decision["publicationMode"] = (
                "complete_snapshot"
                if sid in FULL_SNAPSHOT_CONTRACTS
                else "reward_only"
            )
            decision["rewardChanged"] = row.get("reward") != update["reward"]
            decision["conditionChanged"] = (
                "condition" in update and row.get("condition") != update["condition"]
            )
            decision["updated"] = any(
                row.get(field) != value for field, value in update.items()
            )
            row.update(update)
        except (Hold, ValueError, TypeError, KeyError) as exc:
            decision["holdReason"] = (
                str(exc) if isinstance(exc, Hold) else "invalid_snapshot"
            )
        decisions.append(decision)
    output = [
        row for row in output
        if row.get("offerKey") not in retired_offer_keys
    ]
    return output, {
        "mode": "structured_first_party_publication_v2",
        "apiCalls": 0,
        "updatedRows": sum(decision["updated"] for decision in decisions),
        "rewardChanges": sum(decision.get("rewardChanged", False) for decision in decisions),
        "retiredRows": sum(decision.get("retired", False) for decision in decisions),
        "heldRows": sum("holdReason" in decision for decision in decisions),
        "decisions": decisions,
    }
