#!/usr/bin/env python3
"""Read-only source collector for the editorial pipeline; no AI or paid API.

Consumes reviewed URL jobs. Search discovery stays with the connected research
agent: queries and unresolved research lanes are emitted by plan_jobs().
Only first-party offer URLs registered in point_sources are fetched as offers.
A successful fetch is not publication authorization or semantic verification.
"""

import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
import direct_offer_refresh as direct
import new_game_pipeline as pipe

PARSERS = {
    k: getattr(direct, "inspect_" + k + "_offer")
    for k in (
        "warau",
        "coincome",
        "moppy",
        "mikoshi",
        "hapitas",
        "chobirich",
        "amefuri",
    )
}


def plan_jobs(root, selection):
    jobs = []
    for g in selection["candidates"]:
        queries = {
            ch: [g["name"] + " " + suffix]
            for ch, suffix in {
                "official": "公式 ゲーム",
                "web": "ポイ活 達成 日数 課金 撤退",
                "x": "site:x.com ポイ活 達成 日目",
                "youtube": "site:youtube.com ポイ活 攻略",
                "instagram": "site:instagram.com ポイ活",
                "pointSites": "ポイ活 案件 条件 期限",
            }.items()
        }
        jobs.append(
            {
                "slug": g["slug"],
                "gameId": g["gameId"],
                "game": g["name"],
                "aliases": g["aliases"],
                "queries": queries,
                "offerJobs": [
                    {"source": r["source"], "url": r["firstPartyCandidateUrl"]}
                    for r in g["offers"]
                ],
                "requirements": [
                    "Record actual URL, source date, access status and relevant heading.",
                    "At least two independent player identities with target, days, spend, play time.",
                    "Never treat a search snippet as body evidence.",
                    "Use schemaVersion 2 dossiers. Missing fields stay null; do not guess.",
                ],
            }
        )
    return jobs


def collect(jobs, sources, fetcher=direct.fetch_first_party, limit=30):
    cache = {}
    out = []
    calls = 0
    for game in jobs:
        rows = []
        for job in game["offerJobs"]:
            sid, url = job["source"], job["url"]
            key = (sid, pipe.url_key(url))
            source = sources.get(sid)
            if key in cache:
                row = cache[key]
            elif not source or sid not in PARSERS:
                row = {"state": "review_required", "reason": "unsupported_source"}
            elif calls >= limit:
                row = {"state": "review_required", "reason": "fetch_budget_exhausted"}
            else:
                calls += 1
                try:
                    raw, final = fetcher(url, source, timeout=15)
                    row = {
                        "raw": raw,
                        "final": final,
                        "sha256": hashlib.sha256(raw.encode()).hexdigest(),
                        "retrievedAt": datetime.now(timezone.utc).isoformat(),
                    }
                except Exception as exc:
                    row = {"state": "fetch_error", "reason": str(exc)[:160]}
                cache[key] = row
            if "raw" in row:
                result = PARSERS[sid](
                    row["raw"], url, row["final"], [game["game"], *game["aliases"]]
                )
                # Keep facts and hashes, not a full copyrighted copy of the terms.
                terms = result.pop("termsText", "")
                result["termsSha256"] = (
                    hashlib.sha256(terms.encode()).hexdigest() if terms else None
                )
                result["termsNeedSemanticReview"] = True
                result.update(
                    evidenceSha256=row["sha256"], retrievedAt=row["retrievedAt"]
                )
            else:
                result = row
            rows.append({"source": sid, "url": url, **result})
        out.append(
            {"slug": game["slug"], "offers": rows, "publicationAuthorized": False}
        )
    return {
        "fetchCalls": calls,
        "uniqueFetches": len(cache),
        "publicationWrites": 0,
        "results": out,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--limit", type=int, default=30)
    a = ap.parse_args()
    folder = (pipe.ROOT / a.run).resolve()
    if (pipe.ROOT / "research/new-games").resolve() not in folder.parents:
        raise ValueError("outside_quarantine")
    selected = pipe.select(pipe.ROOT, pipe.read(folder / "registry.json"))
    jobs = plan_jobs(pipe.ROOT, selected)
    pipe.atomic(folder / "research-jobs.json", jobs)
    if a.fetch:
        sources = {
            s["id"]: s
            for s in pipe.read(pipe.ROOT / "config/point_sources.json")["sources"]
        }
        pipe.atomic(
            folder / "collected-offers.json", collect(jobs, sources, limit=a.limit)
        )
    print(
        json.dumps(
            {"jobs": len(jobs), "fetchRequested": a.fetch, "publicationWrites": 0}
        )
    )


if __name__ == "__main__":
    main()
