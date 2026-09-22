#!/usr/bin/env python3
"""API-free same-run new-game review and structured existing-offer refresh.

Listing titles are discovery hints, not identities or yen amounts. Reuse the
direct collector's fetch cache, bind structured evidence to first-party URLs,
and rank only amounts explicitly expressed in yen by existing parsers. The
new-game evidence stays quarantined. Existing rows use the separate explicit
structuredPublication policy; old date-only approvals are never renewed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import direct_offer_refresh as direct

ROOT = Path(__file__).resolve().parents[1]
# A 2026-09-20 live listing-only capacity probe measured 558 detail candidates
# across 136 two-site game groups before Moppy recovery. Keep a bounded margin
# above that observed surface while remaining well inside the 90-minute job cap.
MAX_DETAILS = 640
# Every rank-eligible game has offers from at least two independent source
# families, so this still bounds the maximum number of groups independently.
MAX_GROUPS = MAX_DETAILS // 2


def discovery_name(title):
    value = direct.html.unescape(str(title or "")).strip()
    value = re.sub(r"^(?:iOS|Android|And)[ _：:・-]+", "", value, flags=re.I)
    value = re.sub(r"^(?:【(?:SKYFLAG|SmaAD|MyChips|M)】)+", "", value, flags=re.I)
    value = re.sub(r"^【(?:レベル|ゲームゴール|累計)[^】]+】", "", value)
    value = re.split(r"[（(](?:(?:ユーザー|アカウント)?レベル|LEVEL|経験値バー|累計|初回課金|ギフトリンク/)", value, flags=re.I)[0]
    value = re.split(r"_(?:iOS|Android)(?:_|\b)| リピート不可| 審査中保証", value, flags=re.I)[0]
    value = re.split(r"(?:（|\()(?:StepUp|iOS|Android|多段階)(?:）|\))| 初回アプリ| 新規アプリ| 新規インストール| - レベル", value, flags=re.I)[0]
    return value.strip()


def source_families(sources):
    """Overlapping registered domains are one source, even with multiple IDs."""
    families = {sid: {sid} for sid in sources}
    domains = {sid: {str(d).lower().removeprefix("www.").rstrip(".")
                     for d in source.get("search_domains", [])} for sid, source in sources.items()}
    for left in sources:
        for right in sources:
            if any(a == b or a.endswith("." + b) or b.endswith("." + a)
                   for a in domains[left] for b in domains[right] if a and b):
                joined = families[left] | families[right]
                for sid in joined:
                    families[sid] = joined
    return {sid: min(group) for sid, group in families.items()}


def _pointtown_explicit_yen(evidence):
    """Accept PointTown yen only when its parsed reward region is unambiguous.

    The underlying review parser is intentionally conservative but older
    fixtures exposed one edge case where text such as ``で 160 200`` could be
    reduced to the first number. Until the source parser itself carries a
    stronger structural marker, the automatic top-five path independently
    rejects adjacent numeric tokens and re-checks the exact 1pt=1JPY contract.
    """
    if evidence.get("parserVersion") != "pointtown-detail-review-v1":
        return None
    header = str(evidence.get("headerText") or "")
    if re.search(r"で\s*[0-9][0-9,]*\s+[0-9][0-9,]*(?:\s|$)", header):
        return None
    points = evidence.get("verifiedCurrentRewardPoints")
    yen = evidence.get("verifiedCurrentRewardYen")
    if (
        type(points) is int
        and type(yen) is int
        and points > 0
        and points == yen
        and evidence.get("rewardUnit") == "PointTown-point"
        and evidence.get("sourcePointRate") == "1pt=1JPY"
    ):
        return yen
    return None


def explicit_yen(evidence, warau_rate_confirmed=False):
    """Do not equate raw pt/P with yen or sum OS/site alternative offers."""
    if evidence.get("state") != "parsed" or evidence.get("downstreamTermsRequired"):
        return None
    if (warau_rate_confirmed and evidence.get("parserVersion") == "warau-stepup-v1"
            and evidence.get("rewardUnit") == "pt"):
        value = evidence.get("rewardPoints")
        return value if type(value) is int and value > 0 else None
    if evidence.get("parserVersion") == "pointtown-detail-review-v1":
        return _pointtown_explicit_yen(evidence)
    contracts = {
        "chobirich-numbered-stepup-v1": "observedRewardYen",
        "coincome-detail-review-v1": "displayedRewardYen",
        "hapitas-detail-review-v1": "verifiedCurrentRewardYen",
        "ecnavi-detail-review-v1": "verifiedCurrentRewardYen",
        "amefuri-multistep-review-v1": "verifiedCurrentRewardYen",
        "gendama-detail-review-v1": "displayedRewardYen",
    }
    value = evidence.get(contracts.get(evidence.get("parserVersion"), ""))
    return value if type(value) is int and value > 0 else None


def research_queries(game):
    return {"web": f'"{game}" ポイ活 攻略 達成 撤退',
            "x": f'site:x.com "{game}" ポイ活 日目',
            "instagram": f'site:instagram.com "{game}" ポイ活',
            "youtube": f'site:youtube.com "{game}" ポイ活 攻略',
            "point_site_reviews": f'"{game}" ポイ活 口コミ 課金'}


def review_scan(*, items, sources, targets, rows, checked_at, fetcher,
                max_groups=MAX_GROUPS, max_details=MAX_DETAILS):
    families = source_families(sources)
    groups = {}
    for item in items:
        # Ambiguous titles stay eligible for strict two-site verification.
        # Only an explicit non-game classification is dropped at this stage.
        if item.get("classification") == "likely_non_game":
            continue
        name = discovery_name(item.get("titleHint"))
        if not name or direct.context_matches_known_game(name, targets):
            continue
        sid, url = item.get("source"), item.get("firstPartyCandidateUrl")
        if (sid not in sources or not direct.source_host_allowed(url, sources[sid])
                or not direct.detail_like(url, sources[sid])):
            continue
        if not direct.source_participates_in_new_game_ranking(sources[sid]):
            continue
        identity = direct.offer_identity_key(url, sid)
        if not identity:
            continue
        key = direct.normalized_text(name)
        bucket = groups.setdefault(key, {"game": name, "offers": {}})
        bucket["offers"].setdefault((families[sid], identity), (sid, url))

    owners = {}
    for key, group in groups.items():
        for identity in group["offers"]:
            owners.setdefault(identity, set()).add(key)
    for group in groups.values():
        group["offers"] = {identity: offer for identity, offer in group["offers"].items()
                           if len(owners[identity]) == 1}
    eligible = [g for g in groups.values()
                if len({family for family, _ in g["offers"]}) >= 2]
    eligible.sort(key=lambda g: (-len({f for f, _ in g["offers"]}), g["game"]))
    warau_rate_confirmed = False
    rate_url = "https://www.warau.jp/help/qa/128/"
    if (any(row.get("site") == "warau" for row in rows)
            or any(sid == "warau" for g in eligible[:max_groups] for sid, _ in g["offers"].values())) and "warau" in sources:
        try:
            raw, final_url = fetcher(rate_url, sources["warau"])
            warau_rate_confirmed = bool(final_url == rate_url and re.search(
                r"原則として\s*1ポイント\s*[=＝]\s*1円", direct.visible_text(raw)))
        except Exception:
            pass
    detail_calls, results = 0, []
    for group in eligible[:max_groups]:
        details = []
        for sid, url in group["offers"].values():
            if detail_calls >= max_details:
                break
            detail_calls += 1
            item = {"source": sid, "url": url, "sourceFamily": families[sid]}
            try:
                parsed = direct.inspect_detail(url, sources[sid], [group["game"]], fetcher=fetcher)
                evidence = parsed.get("sourceEvidence") or {}
                item["evidence"] = evidence
                item["finalUrl"] = parsed.get("url")
                item["detailConfirmed"] = bool(
                    direct.source_host_allowed(item["finalUrl"], sources[sid])
                    and evidence.get("state") == "parsed"
                    and evidence.get("evidenceFingerprint")
                    and evidence.get("termsText")
                    and evidence.get("platform") in {"iOS", "Android"}
                    and not evidence.get("downstreamTermsRequired"))
                item["rewardYen"] = explicit_yen(evidence, warau_rate_confirmed) if item["detailConfirmed"] else None
            except Exception as exc:
                item.update(detailConfirmed=False, error=direct.summarize_fetch_error(exc))
            details.append(item)
        confirmed = {d["sourceFamily"] for d in details if d.get("detailConfirmed")}
        amounts = [d["rewardYen"] for d in details if d.get("rewardYen") is not None]
        listing_sources = {family for family, _ in group["offers"]}
        verified_reward_sources = {
            d["sourceFamily"] for d in details if d.get("rewardYen") is not None
        }
        reasons = ["game_identity_review_required", "full_terms_publication_review_required",
                   "cross_channel_research_required", "inline_progress_evidence_required",
                   "image_and_rights_required", "guide_and_mobile_artifact_validation_required"]
        if len(confirmed) < 2:
            reasons.insert(0, "fewer_than_two_confirmed_sites")
        if not amounts:
            reasons.insert(0, "yen_conversion_incomplete")
        elif any(d.get("detailConfirmed") and d.get("rewardYen") is None for d in details):
            # A second source may confirm the game/offer but expose a reward
            # unit that is not yet safely convertible to JPY. Keep the game as
            # a research candidate when at least one first-party reward is
            # strictly verified; publication remains separately gated.
            reasons.insert(0, "partial_yen_conversion")
        if len(details) < len(group["offers"]):
            reasons.insert(0, "detail_budget_reached")
        # Fail closed: a single parser/source must never determine a new game's
        # published/ranked reward. This specifically prevents a malformed detail
        # page (for example a referral/promotional pt amount in the header) from
        # becoming the candidate's "highest reward".
        ranking_eligible = len(listing_sources) >= 2 and len(verified_reward_sources) >= 2 and bool(amounts)
        if len(verified_reward_sources) < 2:
            reasons.insert(0, "fewer_than_two_verified_reward_sources")
        results.append({"game": group["game"], "confirmedSourceCount": len(confirmed),
                        "listingSourceCount": len(listing_sources),
                        "verifiedRewardSourceCount": len(verified_reward_sources),
                        "candidateEligible": ranking_eligible,
                        "maxObservedRewardYen": max(amounts) if amounts else None,
                        "publicationAuthorized": False, "holdReasons": reasons,
                        "researchStatus": "not_started", "researchQueries": research_queries(group["game"]),
                        "details": details})
    ranked = [g for g in results if g["candidateEligible"] and g["maxObservedRewardYen"] is not None
              and "detail_budget_reached" not in g["holdReasons"]]
    ranked.sort(key=lambda g: (-g["maxObservedRewardYen"], g["game"]))
    group_limit = len(eligible) > max_groups
    detail_limit = any("detail_budget_reached" in r["holdReasons"] for r in results)
    return {"phase": "DAILY_SAME_SCAN_REVIEW_V1", "checkedAt": checked_at,
            "apiCalls": 0, "publicationWrites": 0, "publishedGames": 0,
            "warauBaseRate": {"confirmed": warau_rate_confirmed, "sourceUrl": rate_url},
            "listingGroups": len(groups), "twoSiteListingGroups": len(eligible),
            "reviewedGroups": len(results), "detailInspectionCalls": detail_calls,
            "groupLimitReached": group_limit,
            "detailLimitReached": detail_limit,
            "sourceScanIncomplete": False,
            "incompleteDiscoverySources": [],
            "rankingComplete": not group_limit and not detail_limit,
            "rankingScope": "supported_scanned_first_party_surfaces",
            "topFiveReviewCandidates": [g["game"] for g in ranked[:5]], "results": results}


def apply_discovery_completeness(report, discovery_summary):
    """Hold top-five handoff when a configured first-party scan failed mid-run.

    `catalogComplete` is intentionally not required: some sources expose only a
    reviewed partial surface by design. `scanComplete` instead captures transient
    failures, content guards, pagination that did not finish, or candidate caps in
    the exact run whose candidates are being ranked.
    """
    if not isinstance(report, dict):
        raise ValueError("daily_review_invalid")
    source_results = (
        discovery_summary.get("sourceResults")
        if isinstance(discovery_summary, dict) else None
    )
    if not isinstance(source_results, list):
        raise ValueError("discovery_summary_missing")
    incomplete = []
    non_ranking_incomplete = []
    for row in source_results:
        if not isinstance(row, dict):
            raise ValueError("discovery_source_result_invalid")
        if row.get("scanComplete") is not True:
            source = str(row.get("source") or row.get("sourceLabel") or "unknown")
            # Missing rankingRequired stays fail-closed for old/unknown data.
            if row.get("rankingRequired") is False:
                non_ranking_incomplete.append(source)
            else:
                incomplete.append(source)
    report["sourceScanIncomplete"] = bool(incomplete)
    report["incompleteDiscoverySources"] = sorted(set(incomplete))
    report["nonRankingIncompleteDiscoverySources"] = sorted(set(non_ranking_incomplete))
    report["discoverySourceCount"] = len(source_results)
    report["rankingComplete"] = bool(report.get("rankingComplete")) and not incomplete
    report["rankingScope"] = "supported_scanned_first_party_surfaces"
    holds = []
    if report.get("groupLimitReached") is True:
        holds.append("ranking_group_budget_reached")
    if report.get("detailLimitReached") is True:
        holds.append("ranking_detail_budget_reached")
    if incomplete:
        holds.append("first_party_discovery_scan_incomplete")
    report["rankingHoldReasons"] = holds
    return report


def _write_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main():
    review_path = ROOT / "data/daily_scan_review.json"

    def consume(**kwargs):
        from structured_publication import prepare
        evidence_items = kwargs.pop("review_items")
        publication_policy = kwargs.pop("publication_policy")
        report = review_scan(**kwargs)
        updated_rows, publication = prepare(kwargs["rows"], evidence_items, kwargs["sources"],
            kwargs["checked_at"], publication_policy, report["warauBaseRate"]["confirmed"])
        report["existingPublication"] = publication
        kwargs["rows"][:] = updated_rows
        _write_report(review_path, report)
        return {"confirmedOfferKeys": [d["offerKey"] for d in publication["decisions"]
                                      if "holdReason" not in d]}

    result = direct.main(after_scan=consume)
    if result != 0:
        return result
    try:
        report = json.loads(review_path.read_text(encoding="utf-8"))
        refresh = json.loads((ROOT / "data/comparison_refresh_status.json").read_text(encoding="utf-8"))
        discovery = refresh.get("newGameDiscovery")
        apply_discovery_completeness(report, discovery)
        _write_report(review_path, report)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: failed to bind discovery completeness to daily ranking: {type(exc).__name__}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
