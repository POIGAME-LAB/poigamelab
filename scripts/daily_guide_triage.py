#!/usr/bin/env python3
"""First-pass triage of every daily guide candidate, then a *bounded* look at the first-party offer pages.

``daily_guide_candidates.py`` lists what the scan saw; this script decides **where to spend the limited research
budget**. The previous routine took the candidates in reward order, opened Warau pages only and stopped after about
15 games - nine of those slots went to Warau SKYFLAG/SmaAD pages that are not viewable publicly, while Amefuri,
COINCOME and Moppy pages of the same games (and ~70 single-condition games) were never looked at.

Stage A (offline, free, **all** candidates)
    Classifies each candidate (game vs service), works out which first-party sites could verify its conditions
    (site x offer shape: Amefuri/COINCOME read StepUp and single offers, Moppy reads single offers only - its StepUp
    Steps are not on the page - Warau is uncertain) and ranks by transparent components. The score only orders the
    research queue. It never says that an article is possible.

Stage B (network, ``--probe``; bounded)
    Walks the ranking and records the candidate's own offer pages with ``guide_offer_sources`` (one GET per page,
    politely spaced). When a game has no readable page, ONE Amefuri name search may add Amefuri pages whose cleaned
    name is identical (a similar name is only listed as ``possibleMatch`` and never probed - identity is decided by the
    store listing later). It stops when ``--target-verified`` readable offers were found, when ``--probe-limit`` games
    were examined (default 30, never more than 40) or when the request cap is hit.

Verdicts (per candidate) - none of them is "an article can be written":

``offer_verified``    at least one first-party page was read with every condition, reward unit and deadline;
``offer_unreadable``  every probed page was unreadable (the states are listed - never read as "ended" or "0 pt");
``offer_not_probed``  budget/stage A only;
``non_game_or_service`` / ``excluded``  a service word was found in the title (not a single-game guide topic).

Candidates with no game words and no service words are ``unclassified``: they are probed only after the likely games and
their ``gameStatus`` stays ``unconfirmed`` - an editor must confirm from the store listing that it is a game.

Whether independent player records exist (2+ independent players, 3+ panel entries, <= 5 years and older than 1 year only with the same condition) and the game's
identity (store developer / app id) are still checked by the routine for ``offer_verified`` games.

    python scripts/daily_guide_triage.py --date 2026-11-19               # stage A only -> triage.json
    python scripts/daily_guide_triage.py --date 2026-11-19 --probe       # + bounded first-party probing
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import daily_guide_candidates as cand  # noqa: E402
from scripts import guide_offer_sources as sources  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))
DAILY_DIR = Path("research/daily-guides")

DEFAULT_PROBE_LIMIT = 30
MAX_PROBE_LIMIT = 40          # "30-40 candidates" - never more, whatever the flags say
DEFAULT_TARGET_VERIFIED = 12  # player research drops many offers; stop probing once this many are readable
MAX_REQUESTS = 140            # hard cap of GETs in one run (page probes + Amefuri searches)
MAX_PAGES_PER_GAME = 3
MAX_LOOKUPS = 20

# (site, offer shape) -> can the public page alone back an article table?  None = depends on the page.
EXPECTED_READABLE: dict[tuple[str, str], bool | None] = {
    ("amefuri", "stepup"): True, ("amefuri", "single"): True,
    ("coincome", "stepup"): True, ("coincome", "single"): True,
    ("moppy", "single"): True, ("moppy", "stepup"): False,   # Moppy StepUp Steps sit behind "POINT GET"
    ("warau", "single"): None, ("warau", "stepup"): None,    # SKYFLAG / SmaAD pages are often "表示できません"
}
SKYFLAG_TAGS = ("【SKYFLAG】", "【SmaAD】")
# Sources the scan reads but this module has no page adapter for: they show the game exists elsewhere, nothing more.
UNSUPPORTED_SOURCES = ("gendama", "kurashiru_reward", "mikoshi", "trima", "hapitas", "ec_navi", "point_town", "powl")


def _paths(c: dict) -> list[dict]:
    """Offer pages of the candidate that an adapter can read, with the expectation for their site x shape."""
    out, seen = [], set()
    for row in c.get("rows", []):
        found = sources.site_and_offer_id(row.get("url") or "")
        if not found or found in seen:
            continue
        seen.add(found)
        site, offer_id = found
        kind = cand.kind_hint(row.get("titleHint", "")) if row.get("titleHint") else "unknown"
        shape = kind if kind in ("stepup", "single") else None
        expected = EXPECTED_READABLE.get((site, shape)) if shape else None
        flagged = site == "warau" and any(tag in str(row.get("titleHint", "")) for tag in SKYFLAG_TAGS)
        out.append({"site": site, "offerId": offer_id, "url": row["url"], "kindHint": kind, "expectedReadable": expected,
                    "skyflagTagged": flagged})
    return out


def _listed_component(days: int | None) -> int:
    if days is None:
        return 0
    return -1 if days < 3 else 0 if days < 14 else 1 if days < 30 else 2


def triage_offline(c: dict) -> dict:
    """Stage A for one candidate: bucket, readable-path expectation and a transparent ranking score."""
    kinds = set(c.get("kindHints", []))
    sites = set(c.get("sources", []))
    paths = _paths(c)
    likely = bool(c.get("likelyGame"))
    # "service" needs a positive signal (a service word in the title). A name that merely lacks game words is NOT proof of
    # a non-game: "Triple Tile" or "Worms Incoming" are listed without any kind words, so they stay in the queue as
    # "unclassified" (probed only after the likely games, and never counted as ready until an editor confirms the game).
    if kinds == {"service"} or ("service" in kinds and kinds <= {"service", "unknown"} and not likely):
        bucket = "non_game_or_service"
    elif not likely and kinds <= {"unknown"}:
        bucket = "unclassified"
    else:
        bucket = "game_candidate"
    readable = [p for p in paths if p["expectedReadable"] is True]
    uncertain = [p for p in paths if p["expectedReadable"] is None and not p["skyflagTagged"]]
    flagged = [p for p in paths if p["skyflagTagged"]]
    hint = c.get("verifiedRewardYen") or c.get("listingRewardHintYen") or 0
    parts = {
        "readablePaths": 3 * min(len(readable), 2),
        "uncertainPath": 1 if uncertain else 0,
        # Listed on more point sites = more people playing it = likelier to have player records (operator decision 2026-11-26).
        "multiSite": 0 if len(sites) < 2 else min(len(sites), 5),
        "rewardMagnitude": round(min(4.0, math.log10(hint)), 2) if hint > 0 else 0,
        # Player records (needed: 2+ independent, <=5 years; >1 year only with an unchanged condition) cannot exist for an offer listed a day ago; the 2026-11-19
        # article that passed had an offer listed ~2 weeks. Long-listed offers are likelier to have records.
        "listedFor": _listed_component(c.get("listedDays")),
        "reusableMaterial": 1 if c.get("relatedMaterial") else 0,
        "noReadablePath": -3 if (paths and not readable and not uncertain) else 0,
        "skyflagOnly": -1 if flagged and not readable and not uncertain else 0,
        "previouslyHeld": -2 if c.get("previouslyHeld") else 0,
        "reviewClassification": -1 if not c.get("likelyGame") else 0,
        "serviceOrNonGame": -5 if bucket == "non_game_or_service" else 0,
    }
    return {
        "game": c["game"], "order": c.get("order"), "bucket": bucket, "kindHints": sorted(kinds), "sources": sorted(sites),
        "osHints": c.get("osHints", []), "listingRewardHintYen": c.get("listingRewardHintYen"), "listedDays": c.get("listedDays"),
        "paths": paths, "otherSites": sorted(sites & set(UNSUPPORTED_SOURCES)),
        "scoreParts": parts, "score": round(sum(parts.values()), 2),
        "relatedMaterial": c.get("relatedMaterial", []), "previouslyHeld": c.get("previouslyHeld"),
        "verdict": "non_game_or_service" if bucket == "non_game_or_service" else "offer_not_probed",
        "gameStatus": "unconfirmed" if bucket == "unclassified" else "likely_game" if bucket == "game_candidate" else "not_a_game",
        "identityCheckRequired": True,
    }


def _same_name(a: str, b: str) -> bool:
    ka, kb = cand.norm_key(a), cand.norm_key(b)
    return bool(ka) and ka == kb


def _summarise(ev: dict) -> dict:
    keep = ("offerKey", "site", "url", "state", "unavailableReason", "title", "gameName", "os", "osSource", "kind", "pointUnit",
            "yenPerPoint", "totalPt", "totalYen", "deadlineDays", "deadlineBasis", "httpStatus", "retrievedAt", "responseSha256")
    out = {k: ev.get(k) for k in keep}
    out["stepCount"] = len(ev.get("steps", []))
    out["temporaryIncrease"] = bool(ev.get("temporaryIncrease"))
    # first-party review counts (Warau: reviews listed on the first page; Moppy: the page's クチコミ count) - a signal
    # that player records may exist, never a count of independent players
    if ev.get("site") == "warau":
        out["reviewCount"] = len(ev.get("reviewIndex", []))
    elif ev.get("reviewCount") is not None:
        out["reviewCount"] = ev["reviewCount"]
    return out


def probe(item: dict, budget: dict, fetcher=None, delay: float = 0.8, lookup: bool = True) -> None:
    """Stage B for one candidate (mutates ``item``). Counts every GET in ``budget``.

    ``budget["maxRequests"]`` / ``["maxLookups"]`` override the daily caps for a deliberate one-off retrospective
    analysis; the daily routine always uses the module defaults."""
    max_requests, max_lookups = budget.get("maxRequests", MAX_REQUESTS), budget.get("maxLookups", MAX_LOOKUPS)
    results, pages = [], sorted(item["paths"], key=lambda p: (p["expectedReadable"] is not True, p["skyflagTagged"]))
    for path in pages[:MAX_PAGES_PER_GAME]:
        if budget["requests"] >= max_requests:
            budget["capHit"] = True
            break
        if budget["requests"]:
            time.sleep(delay)
        budget["requests"] += 1
        results.append(_summarise(sources.record(path["url"], fetcher)))
        if results[-1]["state"] == "readable":
            break  # one readable first-party page is enough to rank the game; the routine re-records the pages it uses
    cross = {"searched": False, "matches": [], "possibleMatch": []}
    if (lookup and not any(r["state"] == "readable" for r in results) and budget["lookups"] < max_lookups
            and budget["requests"] < max_requests and not any(p["site"] == "amefuri" for p in item["paths"])):
        if budget["requests"]:
            time.sleep(delay)
        budget["requests"] += 1
        budget["lookups"] += 1
        cross["searched"] = True
        for hit in sources.lookup_amefuri(item["game"], fetcher):
            (cross["matches"] if _same_name(hit["gameName"], item["game"]) else cross["possibleMatch"]).append(hit)
        for hit in cross["matches"][:2]:
            if budget["requests"] >= max_requests:
                budget["capHit"] = True
                break
            time.sleep(delay)
            budget["requests"] += 1
            results.append(_summarise(sources.record(hit["url"], fetcher)))
            if results[-1]["state"] == "readable":
                break
    item["probes"], item["crossSite"] = results, cross
    readable = [r for r in results if r["state"] == "readable"]
    item["playerSignal"] = {"firstPartyReviewCount": max([r["reviewCount"] for r in results if r.get("reviewCount") is not None] or [None], default=None)}
    if readable:
        item["verdict"] = "offer_verified"
        item["readableOffers"] = [{"offerKey": r["offerKey"], "kind": r["kind"], "os": r["os"], "totalPt": r["totalPt"], "totalYen": r["totalYen"]} for r in readable]
    else:
        item["verdict"] = "offer_unreadable"
        item["unreadableReasons"] = sorted({f"{r['site']}:{r['state']}:{r.get('unavailableReason')}" for r in results})


def _is_promising(item: dict) -> bool:
    """A readable offer that is worth counting toward the stop target (see module docstring)."""
    if item["verdict"] != "offer_verified" or item.get("previouslyHeld"):
        return False
    return (item.get("playerSignal") or {}).get("firstPartyReviewCount") != 0


def build(date: str, root: Path = ROOT, do_probe: bool = False, probe_limit: int = DEFAULT_PROBE_LIMIT,
          target_verified: int = DEFAULT_TARGET_VERIFIED, fetcher=None, delay: float = 0.8, lookup: bool = True) -> dict:
    cpath = root / DAILY_DIR / date / "candidates.json"
    data = json.loads(cpath.read_text(encoding="utf-8"))
    if data.get("status") != "ok":
        return {"schemaVersion": 1, "productionDate": date, "status": data.get("status", "unknown"), "items": []}
    cand.ALIASES.clear()
    cand.ALIASES.update(cand._load_aliases(root))
    limit = max(1, min(int(probe_limit), MAX_PROBE_LIMIT))
    items = [triage_offline(c) for c in data["candidates"]]
    # games held on an earlier day go to the back of the queue: they are probed only with what the new games leave over
    def queue_key(i):
        return (bool(i.get("previouslyHeld")), -i["score"], i["order"] or 0, i["game"])

    games = sorted((i for i in items if i["bucket"] == "game_candidate"), key=queue_key)
    unclassified = sorted((i for i in items if i["bucket"] == "unclassified"), key=queue_key)
    budget = {"requests": 0, "lookups": 0, "capHit": False, "probed": 0, "verified": 0, "promising": 0}
    if do_probe:
        for item in games + unclassified:      # unclassified names only get what the likely games leave over
            if budget["probed"] >= limit or budget["promising"] >= target_verified or budget["capHit"]:
                break
            if not item["paths"] and budget["lookups"] >= MAX_LOOKUPS:
                continue
            probe(item, budget, fetcher, delay, lookup)
            budget["probed"] += 1
            budget["verified"] += item["verdict"] == "offer_verified"
            budget["promising"] += _is_promising(item)
    # After probing, games whose first-party page already shows user reviews come first among the verified ones.
    def reviews(i):
        return (i.get("playerSignal") or {}).get("firstPartyReviewCount") or 0

    bucket_order = {"game_candidate": 0, "unclassified": 1, "non_game_or_service": 2}
    ranked = sorted(items, key=lambda i: (bucket_order.get(i["bucket"], 3), i["verdict"] != "offer_verified" if do_probe else False,
                                          -min(reviews(i), 5), -i["score"], i["order"] or 0, i["game"]))
    for n, item in enumerate(ranked, 1):
        item["rank"] = n
    counts: dict[str, int] = {}
    for item in items:
        counts[item["verdict"]] = counts.get(item["verdict"], 0) + 1
    return {
        "schemaVersion": 1, "productionDate": date, "status": "ok", "candidatesFile": f"research/daily-guides/{date}/candidates.json",
        "inputCheckedAt": data["inputs"]["monitor"]["checkedAt"],
        "stages": {"A": "offline, all candidates", "B": "bounded first-party probing" if do_probe else "not run"},
        "budget": {"probeLimit": limit, "maxProbeLimit": MAX_PROBE_LIMIT, "targetVerified": target_verified,
                   "maxRequests": MAX_REQUESTS, "maxPagesPerGame": MAX_PAGES_PER_GAME, "maxAmefuriLookups": MAX_LOOKUPS, **budget},
        "candidateCount": len(items), "gameCandidateCount": len(games), "unclassifiedCount": len(unclassified), "verdictCounts": counts,
        "note": "score orders the research queue only. offer_verified means the first-party conditions were read; it does not mean an "
                "article is possible (player records, store identity and gameplay sources are still required).",
        "items": ranked,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", default=datetime.now(JST).date().isoformat())
    ap.add_argument("--probe", action="store_true", help="stage B: read first-party offer pages (network, bounded)")
    ap.add_argument("--probe-limit", type=int, default=DEFAULT_PROBE_LIMIT, help=f"games to examine in stage B (<= {MAX_PROBE_LIMIT})")
    ap.add_argument("--target-verified", type=int, default=DEFAULT_TARGET_VERIFIED)
    ap.add_argument("--no-lookup", action="store_true", help="skip the Amefuri name search")
    ap.add_argument("--delay", type=float, default=0.8, help="seconds between requests")
    ap.add_argument("--out", help="output path (default research/daily-guides/<date>/triage.json)")
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args(argv)
    result = build(args.date, ROOT, args.probe, args.probe_limit, args.target_verified, None, args.delay, not args.no_lookup)
    if result.get("status") != "ok":
        print(f"candidates status={result.get('status')}: nothing to triage")
        return 2
    out = Path(args.out) if args.out else ROOT / DAILY_DIR / args.date / "triage.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    b = result["budget"]
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}  candidates={result['candidateCount']} games={result['gameCandidateCount']} "
          f"verdicts={result['verdictCounts']} requests={b['requests']}/{b['maxRequests']} probed={b['probed']}/{b['probeLimit']} "
          f"verified={b['verified']} promising={b['promising']}")
    for item in result["items"][: args.top]:
        print(f"{item['rank']:>3} {item['score']:>5} {item['verdict']:<20} {item['game'][:34]:<34} kinds={','.join(item['kindHints'])} "
              f"sites={','.join(item['sources'])} paths={','.join(p['site'] for p in item['paths'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
