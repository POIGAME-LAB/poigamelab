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
MAX_GROUPS = 1200
MAX_DETAILS = 2400
MIN_CANDIDATE_SOURCES = 1


def _source_id(source):
    return str((source or {}).get("id") or "")


def _parsed_url(url):
    try:
        return direct.urlparse(str(url or ""))
    except (TypeError, ValueError):
        return None


def _is_moppy_ajax_listing(url, source):
    parsed = _parsed_url(url)
    return bool(
        _source_id(source) == "moppy"
        and parsed is not None
        and parsed.path == "/ajax/category/get_list.php"
    )


def _is_coincome_app_listing(url, source):
    parsed = _parsed_url(url)
    if _source_id(source) != "coincome" or parsed is None or parsed.path.rstrip("/") != "/campaigns":
        return False
    try:
        query = direct.parse_qs(parsed.query or "")
    except (TypeError, ValueError):
        return False
    return query.get("_category_id") == ["21"]


def _is_amefuri_app_listing(url, source):
    parsed = _parsed_url(url)
    if _source_id(source) != "amefuri" or parsed is None or parsed.path != "/item_list":
        return False
    try:
        query = direct.parse_qs(parsed.query or "")
    except (TypeError, ValueError):
        return False
    return query.get("slug") == ["app_game"]


def _is_retryable_transport_error(error):
    if isinstance(error, direct.HTTPError):
        return error.code in {408, 425, 429, 500, 502, 503, 504}
    if isinstance(error, TimeoutError):
        return True
    if isinstance(error, direct.URLError):
        return True
    return isinstance(error, ConnectionError)


def _fetch_moppy_ajax(url, source, timeout=15, max_bytes=1200000, opener_factory=None):
    """Fetch Moppy's first-party AJAX listing using its required XRW header.

    Live GitHub-runner diagnostics on 2026-09-17 showed that the endpoint
    returns an empty 200 response without ``X-Requested-With: XMLHttpRequest``
    and the normal listing payload with that header. Browser UA, Referer and
    cookies were independently tested and were not required.
    """
    if not direct.source_host_allowed(url, source):
        raise ValueError("URL is outside registered first-party domains")
    mobile = bool(source.get("mobile", True))
    ua = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
        "Mobile/15E148 Safari/604.1"
        if mobile else
        "Mozilla/5.0 (compatible; POIGAMELAB/1.0; +https://poigamelab.com/)"
    )
    req = direct.Request(url, headers={
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.5",
        "X-Requested-With": "XMLHttpRequest",
    })
    factory = opener_factory or direct.build_opener
    opener = factory(direct.FirstPartyRedirectHandler(source))
    with opener.open(req, timeout=timeout) as response:
        final_url = response.geturl() if hasattr(response, "geturl") else url
        if not direct.source_host_allowed(final_url, source):
            raise ValueError("redirect left registered first-party domains")
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("response exceeds byte limit; incomplete evidence rejected")
        charset = None
        try:
            charset = response.headers.get_content_charset()
        except Exception:
            pass
    return data.decode(charset or "utf-8", errors="replace"), final_url


def resilient_fetch_first_party(url, source, timeout=15, max_bytes=1200000, base_fetch=None):
    """Use one normal read, with one bounded retry only for known transient gaps.

    Normal successful listing requests are still fetched once and reused by the
    direct collector cache. The second read is permitted only when a supported
    listing has a transient transport failure, or when COINCOME returns a
    successful page that contains none of its reviewed first-party detail
    identities. This prevents a temporary empty edge response from being
    mistaken for a genuine zero-offer catalog.
    """
    base = base_fetch or direct.fetch_first_party
    moppy_ajax = _is_moppy_ajax_listing(url, source)
    coincome_listing = _is_coincome_app_listing(url, source)
    amefuri_listing = _is_amefuri_app_listing(url, source)
    retryable_listing = moppy_ajax or coincome_listing or amefuri_listing

    def one_read():
        if moppy_ajax:
            return _fetch_moppy_ajax(url, source, timeout=timeout, max_bytes=max_bytes)
        if timeout == 15 and max_bytes == 1200000:
            return base(url, source)
        return base(url, source, timeout=timeout, max_bytes=max_bytes)

    try:
        raw, final_url = one_read()
    except Exception as exc:
        if not retryable_listing or not _is_retryable_transport_error(exc):
            raise
        raw, final_url = one_read()

    if moppy_ajax and not str(raw or "").strip():
        raw, final_url = one_read()
        if not str(raw or "").strip():
            raise ValueError("moppy ajax listing empty after retry")

    if coincome_listing and "/campaigns/details/" not in str(raw or ""):
        raw, final_url = one_read()
        if "/campaigns/details/" not in str(raw or ""):
            raise ValueError("coincome app listing missing detail identities after retry")

    return raw, final_url


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
        # Ambiguous titles stay eligible for strict first-party detail verification.
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

    owners = {}
    for key, group in groups.items():
        for identity in group["offers"]:
            owners.setdefault(identity, set()).add(key)
    for group in groups.values():
        group["offers"] = {identity: offer for identity, offer in group["offers"].items()
                           if len(owners[identity]) == 1}
    eligible = [g for g in groups.values()
                if len({family for family, _ in g["offers"]}) >= MIN_CANDIDATE_SOURCES]
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
        reasons = ["game_identity_review_required", "full_terms_publication_review_required",
                   "cross_channel_research_required", "inline_progress_evidence_required",
                   "image_and_rights_required", "guide_and_mobile_artifact_validation_required"]
        if len(confirmed) < MIN_CANDIDATE_SOURCES:
            reasons.insert(0, "no_confirmed_site")
        if any(d.get("detailConfirmed") and d.get("rewardYen") is None for d in details) or not amounts:
            reasons.insert(0, "yen_conversion_incomplete")
        if len(details) < len(group["offers"]):
            reasons.insert(0, "detail_budget_reached")
        results.append({"game": group["game"], "confirmedSourceCount": len(confirmed),
                        "candidateEligible": len(confirmed) >= MIN_CANDIDATE_SOURCES,
                        "maxObservedRewardYen": max(amounts) if amounts else None,
                        "publicationAuthorized": False, "holdReasons": reasons,
                        "researchStatus": "not_started", "researchQueries": research_queries(group["game"]),
                        "details": details})
    # One confirmed point-site amount is sufficient for candidate ranking.
    # Other sources may remain unreadable and are kept as diagnostics, but they
    # must not veto a valid first-party yen amount from another source.
    ranked = [g for g in results if g["candidateEligible"] and g["maxObservedRewardYen"] is not None
              and "detail_budget_reached" not in g["holdReasons"]]
    ranked.sort(key=lambda g: (-g["maxObservedRewardYen"], g["game"]))
    group_limit = len(eligible) > max_groups
    detail_limit = any("detail_budget_reached" in r["holdReasons"] for r in results)
    return {"phase": "DAILY_SAME_SCAN_REVIEW_V1", "checkedAt": checked_at,
            "apiCalls": 0, "publicationWrites": 0, "publishedGames": 0,
            "warauBaseRate": {"confirmed": warau_rate_confirmed, "sourceUrl": rate_url},
            "listingGroups": len(groups),
            "candidateListingGroups": len(eligible),
            "twoSiteListingGroups": sum(
                len({family for family, _ in g["offers"]}) >= 2 for g in groups.values()
            ),
            "reviewedGroups": len(results), "detailInspectionCalls": detail_calls,
            "groupLimitReached": group_limit,
            "detailLimitReached": detail_limit,
            "sourceScanIncomplete": False,
            "incompleteDiscoverySources": [],
            "rankingComplete": not group_limit and not detail_limit,
            "rankingScope": "supported_scanned_first_party_surfaces",
            "topFiveReviewCandidates": [g["game"] for g in ranked[:5]], "results": results}


def apply_discovery_completeness(report, discovery_summary):
    """Hold top-five handoff only for discovery gaps that can bias ranking.

    A source may deliberately expose a bounded partial surface. Such a source is
    non-blocking only when the source contract explicitly marks ranking
    completeness as optional *and* the run stopped solely at its configured
    candidate cap. Transport/content failures still block ranking. Missing
    metadata fails closed.
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
    expected_partial = []
    for row in source_results:
        if not isinstance(row, dict):
            raise ValueError("discovery_source_result_invalid")
        if row.get("scanComplete") is True:
            continue
        source_id = str(row.get("source") or row.get("sourceLabel") or "unknown")
        bounded_partial = (
            row.get("rankingCompletenessRequired") is False
            and row.get("candidateLimitReached") is True
            and int(row.get("fetchErrors") or 0) == 0
            and row.get("contentGuardFailed") is not True
        )
        if bounded_partial:
            expected_partial.append(source_id)
        else:
            incomplete.append(source_id)
    report["sourceScanIncomplete"] = bool(incomplete)
    report["incompleteDiscoverySources"] = sorted(set(incomplete))
    report["expectedPartialDiscoverySources"] = sorted(set(expected_partial))
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

    prior_fetch = direct.fetch_first_party

    def guarded_fetch(url, source, timeout=15, max_bytes=1200000):
        return resilient_fetch_first_party(
            url, source, timeout=timeout, max_bytes=max_bytes, base_fetch=prior_fetch
        )

    direct.fetch_first_party = guarded_fetch
    try:
        result = direct.main(after_scan=consume)
    finally:
        direct.fetch_first_party = prior_fetch
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
