#!/usr/bin/env python3
"""Bounded research for the five games selected by the 01:17 scan.

This stage is quarantine-only. Tavily is discovery, never factual evidence by
itself. URLs are kept as factual research sources only when their public page is
directly fetched and independently contains the target game. X/YouTube/Instagram
may legitimately produce zero kept sources while still recording a completed
search. Point-site evidence comes from the already verified same-run queue.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "new_game_content_queue.json"
OUT_DIR = ROOT / "data" / "new_game_channel_research"
STATUS = ROOT / "data" / "new_game_channel_research_status.json"
CHANNELS = ("web", "x", "youtube", "instagram", "pointSites")
DOMAIN_FILTERS = {
    "x": {"x.com", "www.x.com", "twitter.com", "www.twitter.com"},
    "youtube": {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"},
    "instagram": {"instagram.com", "www.instagram.com"},
}
POI_MARKERS = ("ポイ活", "案件", "達成", "レベル", "lv", "無課金", "課金", "日目", "クリア", "報酬", "ポイント")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def safe_slug(value):
    raw = str(value or "").strip().casefold()
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    if ascii_slug:
        return ascii_slug[:80]
    return "game-" + hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]


def safe_https(url):
    try:
        p = urlparse(str(url or "").strip())
    except Exception:
        return False
    return p.scheme == "https" and bool(p.hostname) and p.username is None and p.password is None


def host_ok(url, channel):
    if channel not in DOMAIN_FILTERS:
        return True
    host = (urlparse(url).hostname or "").lower()
    return host in DOMAIN_FILTERS[channel]


def normalized(value):
    return re.sub(r"\s+", "", str(value or "")).casefold()


def target_present(text, game):
    target = normalized(game)
    return bool(target and target in normalized(text))


def poi_context(text):
    low = str(text or "").casefold()
    return any(marker.casefold() in low for marker in POI_MARKERS)


def bounded_excerpt(text, game, limit=520):
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return ""
    low = value.casefold()
    positions = [low.find(str(game).casefold())]
    positions += [low.find(x.casefold()) for x in POI_MARKERS]
    positions = [x for x in positions if x >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - 140)
    end = min(len(value), start + limit)
    excerpt = value[start:end].strip()
    if start:
        excerpt = "…" + excerpt
    if end < len(value):
        excerpt += "…"
    return excerpt


def _search(query, api_key, max_results):
    from collect_guide_evidence import tavily_search
    return tavily_search(query, api_key, max_results=max_results)


def _fetch(url):
    from collect_guide_evidence import direct_fetch, visible_text
    raw, meta = direct_fetch(url)
    return visible_text(raw), meta


def research_channel(game, channel, query, api_key, *, searcher=_search, fetcher=_fetch, max_results=5, max_fetches=4):
    lane = {
        "searched": True,
        "complete": False,
        "query": str(query or ""),
        "searchCalls": 1,
        "searchErrors": 0,
        "resultUrls": 0,
        "directFetches": 0,
        "fetchErrors": 0,
        "sources": [],
    }
    try:
        response = searcher(str(query or ""), api_key, max_results)
    except Exception:
        lane["searchErrors"] = 1
        return lane
    rows = response.get("results") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        lane["searchErrors"] = 1
        return lane
    lane["resultUrls"] = len(rows)
    seen = set()
    for item in rows:
        if lane["directFetches"] >= max_fetches:
            break
        url = str((item or {}).get("url") or "").strip() if isinstance(item, dict) else ""
        if not safe_https(url) or not host_ok(url, channel) or url in seen:
            continue
        seen.add(url)
        lane["directFetches"] += 1
        try:
            text, meta = fetcher(url)
        except Exception:
            lane["fetchErrors"] += 1
            continue
        if not target_present(text, game):
            continue
        excerpt = bounded_excerpt(text, game)
        if not excerpt:
            continue
        source = {
            "id": f"{channel}:{len(lane['sources']) + 1}",
            "url": url,
            "channel": channel,
            "targetConfirmed": True,
            "poiContext": poi_context(text),
            "excerpt": excerpt,
            "claim": excerpt if poi_context(text) else "",
            "httpStatus": int((meta or {}).get("httpStatus", 200)),
            "evidenceLevel": "direct_public_page",
        }
        lane["sources"].append(source)
    lane["complete"] = lane["searchErrors"] == 0
    return lane


def point_site_lane(item):
    sources = []
    for row in item.get("pointSiteEvidence") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("source") or "").strip()
        url = str(row.get("url") or "").strip()
        if not sid or not safe_https(url):
            continue
        sources.append({
            "id": f"pointSites:{sid}",
            "url": url,
            "channel": "pointSites",
            "targetConfirmed": True,
            "poiContext": True,
            "claim": f"{sid} の同一巡回で案件詳細を確認済み",
            "evidenceLevel": "same_scan_first_party_detail",
        })
    if len({x["id"] for x in sources}) < 1:
        raise ValueError("point_site_evidence_missing")
    return {"searched": True, "complete": True, "searchCalls": 0, "sources": sources}


def research_item(item, api_key, *, searcher=_search, fetcher=_fetch):
    game = str(item.get("game") or "").strip()
    if not game:
        raise ValueError("game_missing")
    queries = item.get("researchQueries")
    if not isinstance(queries, dict):
        raise ValueError("research_queries_missing")
    result = {
        "schemaVersion": 1,
        "phase": "NEW_GAME_MULTI_CHANNEL_RESEARCH_V1",
        "game": game,
        "rank": int(item.get("rank") or 0),
        "maxObservedRewardYen": int(item.get("maxObservedRewardYen") or 0),
        "publicationAuthorized": False,
        "research": {},
    }
    for channel in ("web", "x", "youtube", "instagram"):
        result["research"][channel] = research_channel(
            game, channel, queries.get(channel, ""), api_key,
            searcher=searcher, fetcher=fetcher,
        )
    result["research"]["pointSites"] = point_site_lane(item)
    result["complete"] = all(result["research"][c].get("complete") is True for c in CHANNELS)
    result["apiCalls"] = sum(int(result["research"][c].get("searchCalls") or 0) for c in CHANNELS)
    return result


def run(queue=None, api_key=None, *, searcher=_search, fetcher=_fetch, out_dir=OUT_DIR):
    queue = queue or load(INPUT)
    if not isinstance(queue, dict) or queue.get("phase") != "NEW_GAME_CONTENT_QUEUE_V1":
        raise ValueError("content_queue_phase_mismatch")
    api_key = api_key if api_key is not None else os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY unavailable")
    items = (queue.get("items") or [])[:5]
    outputs = []
    for item in items:
        result = research_item(item, api_key, searcher=searcher, fetcher=fetcher)
        path = Path(out_dir) / f"{safe_slug(result['game'])}.json"
        atomic_json(path, result)
        outputs.append(result)
    status = {
        "phase": "NEW_GAME_MULTI_CHANNEL_RESEARCH_V1",
        "success": all(x.get("complete") for x in outputs),
        "games": len(outputs),
        "completeGames": sum(bool(x.get("complete")) for x in outputs),
        "apiCalls": sum(int(x.get("apiCalls") or 0) for x in outputs),
        "publicationWrites": 0,
    }
    atomic_json(STATUS, status)
    return status


def main():
    status = run()
    print(json.dumps(status, ensure_ascii=False))
    return 0 if status["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
