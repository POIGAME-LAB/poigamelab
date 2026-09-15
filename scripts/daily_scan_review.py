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
MAX_GROUPS = 15
MAX_DETAILS = 60


def discovery_name(title):
    value = direct.html.unescape(str(title or "")).strip()
    # Never merge different sequels, subtitles, or broadly matching names.
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


def explicit_yen(evidence, warau_rate_confirmed=False):
    """Do not equate raw pt/P with yen or sum OS/site alternative offers."""
    if evidence.get("state") != "parsed" or evidence.get("downstreamTermsRequired"):
        return None
    if (warau_rate_confirmed and evidence.get("parserVersion") == "warau-stepup-v1"
            and evidence.get("rewardUnit") == "pt"):
        value = evidence.get("rewardPoints")
        return value if type(value) is int and value > 0 else None
    contracts = {
        "chobirich-numbered-stepup-v1": "observedRewardYen",
        "coincome-detail-review-v1": "displayedRewardYen",
        "hapitas-detail-review-v1": "verifiedCurrentRewardYen",
        "pointtown-detail-review-v1": "verifiedCurrentRewardYen",
        "ecnavi-detail-review-v1": "verifiedCurrentRewardYen",
        "amefuri-multistep-review-v1": "verifiedCurrentRewardYen",
        "gendama-detail-review-v1": "displayedRewardYen",
    }
    value = evidence.get(contracts.get(evidence.get("parserVersion"), ""))
    return value if type(value) is int and value > 0 else None


def research_queries(game):
    # A plan is explicitly not a completed search or verified progress record.
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
        if item.get("classification") != "likely_game":
            continue
        name = discovery_name(item.get("titleHint"))
        if not name or direct.context_matches_known_game(name, targets):
            continue
        sid, url = item.get("source"), item.get("firstPartyCandidateUrl")
        if (sid not in sources or not direct.source_host_allowed(url, sources[sid])
                or not direct.detail_like(url, sources[sid])):
            continue
        if (sources[sid].get("scheduled_fetch_enabled", True) is not True
                and not (sources[sid].get("coverage_detail_review_enabled") is True
                         and sources[sid].get("coverage_detail_review_mode") == "candidate_only")):
            continue
        identity = direct.offer_identity_key(url, sid)
        if not identity:
            continue
        key = direct.normalized_text(name)
        bucket = groups.setdefault(key, {"game": name, "offers": {}})
        bucket["offers"].setdefault((families[sid], identity), (sid, url))

    # An offer URL appearing under conflicting names is not two new games.
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
            pass  # Unknown conversion keeps the candidate out of the ranking.
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
                # The parser binds canonical offer identity. Retain the host
                # check even when a fixture/custom fetcher is supplied.
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
        reasons = ["game_identity_review_required", "full_terms_publication_review_required",
                   "cross_channel_research_required", "inline_progress_evidence_required",
                   "image_and_rights_required", "guide_and_mobile_artifact_validation_required"]
        if len(confirmed) < 2:
            reasons.insert(0, "fewer_than_two_confirmed_sites")
        if any(d.get("detailConfirmed") and d.get("rewardYen") is None for d in details) or not amounts:
            reasons.insert(0, "yen_conversion_incomplete")
        if len(details) < len(group["offers"]):
            reasons.insert(0, "detail_budget_reached")
        results.append({"game": group["game"], "confirmedSourceCount": len(confirmed),
                        "candidateEligible": len(confirmed) >= 2,
                        "maxObservedRewardYen": max(amounts) if amounts else None,
                        "publicationAuthorized": False, "holdReasons": reasons,
                        "researchStatus": "not_started", "researchQueries": research_queries(group["game"]),
                        "details": details})
    ranked = [g for g in results if g["candidateEligible"] and g["maxObservedRewardYen"] is not None
              and "yen_conversion_incomplete" not in g["holdReasons"]
              and "detail_budget_reached" not in g["holdReasons"]]
    ranked.sort(key=lambda g: (-g["maxObservedRewardYen"], g["game"]))
    return {"phase": "DAILY_SAME_SCAN_REVIEW_V1", "checkedAt": checked_at,
            "apiCalls": 0, "publicationWrites": 0, "publishedGames": 0,
            "warauBaseRate": {"confirmed": warau_rate_confirmed, "sourceUrl": rate_url},
            "listingGroups": len(groups), "twoSiteListingGroups": len(eligible),
            "reviewedGroups": len(results), "detailInspectionCalls": detail_calls,
            "groupLimitReached": len(eligible) > max_groups,
            "detailLimitReached": any("detail_budget_reached" in r["holdReasons"] for r in results),
            "rankingScope": "reviewed_confirmed_candidates_only",
            "topFiveReviewCandidates": [g["game"] for g in ranked[:5]], "results": results}


def main():
    def consume(**kwargs):
        from structured_publication import prepare
        evidence_items = kwargs.pop("review_items")
        publication_policy = kwargs.pop("publication_policy")
        report = review_scan(**kwargs)
        updated_rows, publication = prepare(kwargs["rows"], evidence_items, kwargs["sources"],
            kwargs["checked_at"], publication_policy, report["warauBaseRate"]["confirmed"])
        report["existingPublication"] = publication
        # Mutate only after all candidates have been evaluated; the direct
        # collector owns the final concurrent-write check and atomic CSV write.
        kwargs["rows"][:] = updated_rows
        path = ROOT / "data/daily_scan_review.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return {"confirmedOfferKeys": [d["offerKey"] for d in publication["decisions"]
                                       if "holdReason" not in d]}
    return direct.main(after_scan=consume)


if __name__ == "__main__":
    raise SystemExit(main())
