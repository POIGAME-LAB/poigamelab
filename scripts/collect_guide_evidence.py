#!/usr/bin/env python3
"""PHASE 4 V49 guide-evidence discovery foundation.

Tavily is discovery only. Search titles/snippets are never persisted as factual
strategy evidence. Every kept URL is fetched directly and must independently
contain the target game. V49 produces a quarantined evidence manifest only; it
never writes game tips/overview or public site data.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "guide_research.json"
TARGETS = ROOT / "config" / "game_targets.json"
OUT = ROOT / "data" / "guide_evidence.json"
STATUS = ROOT / "data" / "guide_research_status.json"


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def post_json(url, payload, timeout=45):
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "POIGAME-LAB/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def tavily_search(query, api_key, max_results=6):
    return post_json("https://api.tavily.com/search", {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
    })


def direct_fetch(url, timeout=25):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.5",
    })
    with urlopen(req, timeout=timeout) as r:
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "text/html" not in ctype and "text/plain" not in ctype:
            raise ValueError("unsupported content type")
        return r.read(1_500_000).decode("utf-8", errors="replace"), {"httpStatus": getattr(r, "status", 200)}


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}: self.skip += 1
    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip: self.skip -= 1
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)


def visible_text(raw):
    p=_VisibleText(); p.feed(raw or "")
    return re.sub(r"\s+", " ", unescape(" ".join(p.parts))).strip()


def canonical_url(url):
    """Stable public page identity; drop tracking/session selectors."""
    u=urlparse(url)
    if u.scheme not in {"http", "https"} or not u.hostname:
        return ""
    tracking_keys={"fbclid", "gclid", "yclid", "ref", "referrer", "affiliate", "aff_id"}
    kept=[]
    for k,v in parse_qsl(u.query, keep_blank_values=True):
        low=k.lower()
        if not low.startswith("utm_") and low not in tracking_keys: kept.append((k,v))
    return urlunparse((u.scheme.lower(), u.netloc.lower(), u.path or "/", "", urlencode(sorted(kept)), ""))


def host_matches(host, domain):
    host=(host or "").lower().strip("."); domain=(domain or "").lower().strip(".")
    return bool(host and domain and (host == domain or host.endswith("." + domain)))


def public_http_url(url):
    """Reject localhost/private literal IPs before direct retrieval."""
    u=urlparse(url); host=(u.hostname or "").lower()
    if u.scheme not in {"http","https"} or not host or host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        ip=ipaddress.ip_address(host)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)
    except ValueError:
        return True


def blocked_url(url, blocked_domains):
    host=(urlparse(url).hostname or "").lower()
    return (not public_http_url(url)) or any(host_matches(host, d) for d in blocked_domains)


def source_type(url, game, cfg):
    host=(urlparse(url).hostname or "").lower()
    official=(cfg.get("officialDomainsByGame") or {}).get(game) or []
    if any(host_matches(host, d) for d in official): return "official"
    return "community_guide"


def target_in_text(text, aliases):
    low=(text or "").casefold()
    return any(str(a).strip().casefold() in low for a in aliases if str(a).strip())


def safe_error(exc):
    msg=re.sub(r"(?i)(api[_-]?key|authorization|token)\s*[:=]\s*[^\s,]+", r"\1=[REDACTED]", str(exc))
    return msg[:180]


def collect_game(game_cfg, cfg, api_key, searcher=tavily_search, fetcher=direct_fetch):
    game=game_cfg["game"]; aliases=list(dict.fromkeys([game] + (game_cfg.get("aliases") or [])))
    diag={"game":game,"searchAttempts":0,"searchErrors":[],"resultUrls":0,"eligibleUrls":0,"directFetches":0,"fetchErrors":0,"confirmed":0}
    found=[]; seen=set()
    max_searches=max(1,min(5,int(cfg.get("maxSearchesPerGame",3))))
    max_results=max(1,min(10,int(cfg.get("maxResultsPerSearch",6))))
    max_fetches=max(1,min(12,int(cfg.get("maxDirectFetchesPerGame",8))))
    for tmpl in (cfg.get("queryTemplates") or [])[:max_searches]:
        query=str(tmpl).replace("{game}", game)
        diag["searchAttempts"] += 1
        try:
            response=searcher(query, api_key, max_results)
        except Exception as e:
            diag["searchErrors"].append(safe_error(e)); continue
        results=response.get("results") or []
        diag["resultUrls"] += len(results)
        for item in results:
            url=canonical_url(str((item or {}).get("url") or "").strip())
            if not url or blocked_url(url, cfg.get("blockedDomains") or []) or url in seen: continue
            seen.add(url); diag["eligibleUrls"] += 1
            if diag["directFetches"] >= max_fetches: break
            diag["directFetches"] += 1
            try:
                raw, meta=fetcher(url)
                text=visible_text(raw)
            except Exception as e:
                diag["fetchErrors"] += 1; continue
            if not target_in_text(text, aliases): continue
            diag["confirmed"] += 1
            found.append({
                "game":game,
                "url":url,
                "domain":urlparse(url).hostname or "",
                "sourceType":source_type(url, game, cfg),
                "targetConfirmed":True,
                "retrievedAt":now_iso(),
                "contentHash":"sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "httpStatus":int(meta.get("httpStatus",200)),
                "status":"quarantined"
            })
        if diag["directFetches"] >= max_fetches: break
    return found, diag


def run(cfg=None, targets=None, api_key=None, searcher=tavily_search, fetcher=direct_fetch):
    cfg=cfg or load_json(CONFIG); targets=targets or load_json(TARGETS)
    api_key=api_key if api_key is not None else os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY unavailable")
    games=(targets.get("games") or [])[:max(1,min(5,int(cfg.get("maxGamesPerRun",1))))]
    evidence=[]; diagnostics=[]
    for g in games:
        rows, diag=collect_game(g,cfg,api_key,searcher=searcher,fetcher=fetcher)
        evidence.extend(rows); diagnostics.append(diag)
    # deterministic dedupe by game + canonical URL
    unique={(x["game"],x["url"]):x for x in evidence}
    evidence=[unique[k] for k in sorted(unique)]
    return {
        "phase":"PHASE4_GUIDE_EVIDENCE_V49",
        "generatedAt":now_iso(),
        "publicationWrites":0,
        "evidence":evidence,
        "diagnostics":diagnostics,
    }


def main():
    try:
        result=run()
        OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        status={"phase":result["phase"],"success":True,"evidenceCount":len(result["evidence"]),"publicationWrites":0,"lastRun":result["generatedAt"]}
        STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(status,ensure_ascii=False))
    except Exception as e:
        status={"phase":"PHASE4_GUIDE_EVIDENCE_V49","success":False,"error":safe_error(e),"publicationWrites":0,"lastRun":now_iso()}
        STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(status,ensure_ascii=False))
        raise

if __name__ == "__main__": main()
