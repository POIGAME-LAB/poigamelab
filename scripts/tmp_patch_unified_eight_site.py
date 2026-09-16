from pathlib import Path
import json

EIGHT = ["moppy", "warau", "coincome", "hapitas", "amefuri", "point_town", "ec_navi", "powl"]


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, 1)


policy_path = Path('config/refresh_policy.json')
policy = json.loads(policy_path.read_text(encoding='utf-8'))
policy['unifiedDailySources'] = EIGHT
publication = policy.setdefault('structuredPublication', {})
publication['sources'] = ["warau", "chobirich", "hapitas", "coincome", "point_town", "ec_navi", "amefuri"]
publication['mode'] = 'complete-stepup-or-exact-reward-snapshot'
policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

path = Path('scripts/direct_offer_refresh.py')
text = path.read_text(encoding='utf-8')
text = replace_once(text,
'''    comparison_sources = [
        str(x).strip() for x in (policy.get("comparisonSources") or []) if str(x).strip()
    ]
    if not comparison_sources:
        print("ERROR: comparisonSources is empty", file=sys.stderr)
        return 2
    unknown = [x for x in comparison_sources if x not in sources]
    if unknown:
        print("ERROR: unregistered comparison sources: " + ", ".join(unknown), file=sys.stderr)
        return 2
''',
'''    comparison_sources = [
        str(x).strip() for x in (policy.get("comparisonSources") or []) if str(x).strip()
    ]
    if not comparison_sources:
        print("ERROR: comparisonSources is empty", file=sys.stderr)
        return 2
    unknown = [x for x in comparison_sources if x not in sources]
    if unknown:
        print("ERROR: unregistered comparison sources: " + ", ".join(unknown), file=sys.stderr)
        return 2

    unified_daily_sources = [
        str(x).strip() for x in (policy.get("unifiedDailySources") or []) if str(x).strip()
    ]
    if not unified_daily_sources:
        print("ERROR: unifiedDailySources is empty", file=sys.stderr)
        return 2
    unknown_unified = [x for x in unified_daily_sources if x not in sources]
    if unknown_unified:
        print("ERROR: unregistered unified daily sources: " + ", ".join(unknown_unified), file=sys.stderr)
        return 2
    invalid_unified = [
        x for x in unified_daily_sources
        if sources[x].get("new_game_discovery_enabled") is not True
    ]
    if invalid_unified:
        print("ERROR: unified source is not enabled for the shared discovery crawl: "
              + ", ".join(invalid_unified), file=sys.stderr)
        return 2
''', 'comparison source policy block')
text = replace_once(text,
'        requested = list(dict.fromkeys(comparison_sources + supplemental + published_sources))\n',
'        requested = list(dict.fromkeys(unified_daily_sources + comparison_sources + supplemental + published_sources))\n',
'requested source block')
text = replace_once(text,
'            is_standard = source_id in comparison_sources\n',
'            is_standard = source_id in unified_daily_sources\n',
'standard source marker')
text = replace_once(text,
'''            if source.get("scheduled_fetch_enabled", True) is not True:
                review.append({
                    "game": game,
                    "source": source_id,
                    "reason": "scheduled_source_fetch_disabled",
                    "existingRows": len(current_rows),
                    "checkedAt": checked_at,
                })
                game_result["sources"].append({
                    "source": source_id,
                    "standard": is_standard,
                    "knownOrDiscoveredUrls": 0,
                    "confirmedOffers": 0,
                    "updatedRows": 0,
                    "reviewRequired": 1,
                    "state": "review_required",
                })
                continue
''',
'''            reuse_unified_listing = (
                source_id in unified_daily_sources
                and source.get("new_game_discovery_enabled") is True
            )
            if (source.get("scheduled_fetch_enabled", True) is not True
                    and not reuse_unified_listing):
                review.append({
                    "game": game,
                    "source": source_id,
                    "reason": "scheduled_source_fetch_disabled",
                    "existingRows": len(current_rows),
                    "checkedAt": checked_at,
                })
                game_result["sources"].append({
                    "source": source_id,
                    "standard": is_standard,
                    "knownOrDiscoveredUrls": 0,
                    "confirmedOffers": 0,
                    "updatedRows": 0,
                    "reviewRequired": 1,
                    "state": "review_required",
                })
                continue
''', 'scheduled fetch gate')
text = replace_once(text,
'            detail_limit = max(0, min(6, int(source.get("direct_detail_limit", 6))))\n',
'''            detail_limit = max(0, min(6, int(source.get("direct_detail_limit", 6))))
            if reuse_unified_listing:
                detail_limit = max(
                    detail_limit,
                    max(0, min(6, int(source.get("coverage_detail_review_limit_per_game") or 0))),
                )
''', 'detail limit')
text = replace_once(text,
'''            discovery_urls = [u for u in deduped_urls
                              if offer_identity_key(u, source_id) not in published_identities]
            discovery_budget = max(0, detail_limit - len(published_urls))
            urls = published_urls + discovery_urls[:discovery_budget]
''',
'''            discovery_urls = [u for u in deduped_urls
                              if offer_identity_key(u, source_id) not in published_identities]
            if source_id in unified_daily_sources:
                for observed_url in discovery_urls:
                    review.append({
                        "game": game,
                        "source": source_id,
                        "url": observed_url,
                        "reason": "first_party_existing_game_listing_offer_observed",
                        "candidateOnly": True,
                        "publicationAuthorized": False,
                        "checkedAt": checked_at,
                    })
            discovery_budget = max(0, detail_limit - len(published_urls))
            urls = published_urls + discovery_urls[:discovery_budget]
''', 'discovery budget block')
text = replace_once(text,
'        game_result["standardTotal"] = len(comparison_sources)\n',
'        game_result["standardTotal"] = len(unified_daily_sources)\n',
'standard total')
text = replace_once(text,
'''        "comparisonSources": comparison_sources,
        "apiCalls": 0,
''',
'''        "comparisonSources": comparison_sources,
        "unifiedDailySources": unified_daily_sources,
        "apiCalls": 0,
''', 'status source block')
path.write_text(text, encoding='utf-8')

path = Path('scripts/structured_publication.py')
text = path.read_text(encoding='utf-8')
text = replace_once(text,
'''REWARD_ONLY_CONTRACTS = {
    "hapitas": {
        "parser": "hapitas-detail-review-v1",
        "identity": direct.hapitas_offer_id,
        "rewardField": "verifiedCurrentRewardYen",
        "fingerprintFields": [
            "offerId", "name", "platform", "displayedCurrentRewardPoints",
            "stepRewardPoints", "verifiedCurrentRewardPoints",
            "verifiedCurrentRewardYen", "rewardUnit", "sourcePointRate",
            "headerText", "termsText", "publicationAuthorized",
        ],
        "rewardUnit": "Hapitas-pt",
        "sourcePointRate": "1pt=1JPY",
        "termsMarkers": ("ポイント対象条件",),
    },
}
''',
'''REWARD_ONLY_CONTRACTS = {
    "hapitas": {
        "parser": "hapitas-detail-review-v1",
        "identity": direct.hapitas_offer_id,
        "rewardField": "verifiedCurrentRewardYen",
        "fingerprintFields": [
            "offerId", "name", "platform", "displayedCurrentRewardPoints",
            "stepRewardPoints", "verifiedCurrentRewardPoints",
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
        "parser": "coincome-detail-review-v1",
        "identity": direct.coincome_offer_id,
        "rewardField": "displayedRewardYen",
        "fingerprintFields": [
            "offerId", "name", "platform", "displayedRewardYen",
            "rewardUnit", "headerText", "termsText",
        ],
        "rewardUnit": "JPY-equivalent",
        "termsMarkers": ("適用端末", "キャッシュバック条件", "承認条件", "ポイント獲得条件", "否認条件"),
    },
    "point_town": {
        "parser": "pointtown-detail-review-v1",
        "identity": direct.pointtown_offer_id,
        "rewardField": "verifiedCurrentRewardYen",
        "fingerprintFields": [
            "offerId", "name", "platform", "verifiedCurrentRewardPoints",
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
        "parser": "amefuri-multistep-review-v1",
        "identity": direct.amefuri_offer_id,
        "rewardField": "verifiedCurrentRewardYen",
        "fingerprintFields": [
            "offerId", "name", "platform", "displayedRewardYenCandidates",
            "stepRewardPoints", "stepTotalPoints", "verifiedCurrentRewardYen",
            "rewardUnit", "sourcePointRate", "headerText", "termsText",
            "publicationAuthorized",
        ],
        "rewardUnit": "JPY-equivalent",
        "sourcePointRate": "10pt=1JPY",
        "pointField": "stepTotalPoints",
        "pointScale": 10,
        "termsMarkers": ("ポイント獲得条件", "成果受付期限"),
    },
}
''', 'reward-only contracts')
text = replace_once(text,
'''    require(e.get("rewardUnit") == contract["rewardUnit"], "unknown_reward_unit")
    require(
        e.get("sourcePointRate") == contract["sourcePointRate"],
        "unit_conversion_review_required",
    )
    if sid == "hapitas":
        require(
            e.get("verifiedCurrentRewardPoints") == reward
            and e.get("displayedCurrentRewardPoints") == reward,
            "yen_point_mismatch",
        )
        steps = e.get("stepRewardPoints")
        require(isinstance(steps, list), "invalid_steps")
        if steps:
            require(
                all(type(value) is int and value >= 0 for value in steps),
                "invalid_step",
            )
            require(sum(steps) == reward, "step_total_mismatch")
''',
'''    require(e.get("rewardUnit") == contract["rewardUnit"], "unknown_reward_unit")
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
        steps = e.get("stepRewardPoints")
        require(isinstance(steps, list) and len(steps) >= 2, "invalid_steps")
        require(all(type(value) is int and value >= 0 for value in steps), "invalid_step")
        require(sum(steps) == e.get("stepTotalPoints"), "step_total_mismatch")
        displayed = e.get("displayedRewardYenCandidates")
        require(isinstance(displayed, list) and reward in displayed, "displayed_reward_mismatch")
''', 'reward-only validation')
path.write_text(text, encoding='utf-8')
