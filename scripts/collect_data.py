#!/usr/bin/env python3
"""POIGAME LAB data collector.

No paid API key is required. It uses public web search via DDGS and public pages.
IMPORTANT: collected values are candidates only. They are NOT auto-published to offers.csv.
"""
from __future__ import annotations
import csv, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
NOW = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")

REWARD_RE = re.compile(r"(?<!\\d)([1-9][0-9,]{2,7})\\s*(?:円|P|ポイント|pt|CIM)", re.I)


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader(); w.writerows(rows)


def ddgs_search(query, max_results=6, timelimit=None):
    try:
        from ddgs import DDGS
    except ImportError:
        print("ddgs is missing. Run: pip install ddgs requests beautifulsoup4", file=sys.stderr)
        return []
    try:
        with DDGS() as d:
            return list(d.text(query, max_results=max_results, timelimit=timelimit))
    except Exception as e:
        print(f"search failed: {query}: {e}", file=sys.stderr)
        return []


def extract_reward(text):
    vals=[]
    for raw in REWARD_RE.findall(text or ""):
        try:
            n=int(raw.replace(",",""))
            if 100 <= n <= 500000:
                vals.append(n)
        except ValueError:
            pass
    return max(vals) if vals else None


def collect_offer_candidates(games, sources):
    out=[]
    for g in games:
        game=g["name"].strip()
        if not game: continue
        for src in sources:
            if src.get("enabled","true").lower() != "true": continue
            site=src["site"].strip(); domain=src["domain"].strip()
            # Search official domain first. We intentionally do not guess a direct offer URL.
            q=f'site:{domain} "{game}" (ポイント OR 円 OR CIM)'
            results=ddgs_search(q, max_results=5)
            for rank,r in enumerate(results, start=1):
                title=r.get("title",""); body=r.get("body",""); href=r.get("href","")
                reward=extract_reward(title+" "+body)
                if not href or reward is None: continue
                host=urlparse(href).netloc.lower()
                if domain not in host: continue
                confidence=max(35, 88-rank*8)
                out.append({
                    "game":game,"site":site,"reward":reward,"url":href,
                    "title":title,"checkedAt":NOW,"confidence":confidence,"status":"要確認"
                })
            time.sleep(0.4)
    # dedupe by game/site/url/reward
    uniq={}
    for x in out:
        uniq[(x['game'],x['site'],x['url'],x['reward'])]=x
    return list(uniq.values())


def collect_guides(games):
    out=[]
    blocked=("moppy.jp","cimcome.jp","mercari.com")
    for g in games:
        game=g["name"].strip()
        results=ddgs_search(f'"{game}" ポイ活 攻略', max_results=8)
        kept=0
        for r in results:
            href=r.get("href",""); title=r.get("title","")
            if not href or any(d in href for d in blocked): continue
            out.append({"game":game,"title":title,"url":href,"source":urlparse(href).netloc,
                        "checkedAt":NOW,"status":"要確認"})
            kept+=1
            if kept>=5: break
        time.sleep(0.4)
    return out


def collect_trends(games, trend_sources):
    out=[]
    # Track known games against the selected social sources. Raw unknown-game search results
    # can still be reviewed from the result titles and later added to games.csv.
    known=[g["name"].strip() for g in games if g.get("name")]
    for src in trend_sources:
        if src.get("enabled","true").lower() != "true": continue
        base=src.get("query","").strip()
        results=ddgs_search(base, max_results=12, timelimit="w")
        for r in results:
            title=(r.get("title","") or "")+" "+(r.get("body","") or "")
            href=r.get("href","") or ""
            matched=[g for g in known if g.lower() in title.lower()]
            # Unknown titles are stored as __DISCOVERY__ so a human can spot new games.
            if not matched: matched=["__DISCOVERY__"]
            for game in matched:
                out.append({"game":game,"source":src.get("name",src.get("source","")),
                            "title":r.get("title","") or "","url":href,"publishedAt":"",
                            "checkedAt":NOW,"score":1,"status":"要確認"})
        time.sleep(0.4)
    return out


def main():
    games=read_csv(ROOT/'games.csv')
    sources=read_csv(ROOT/'sources.csv')
    trends=read_csv(ROOT/'trend_sources.csv')
    offer_rows=collect_offer_candidates(games,sources)
    guide_rows=collect_guides(games)
    trend_rows=collect_trends(games,trends)
    write_csv(DATA/'offer_candidates.csv',["game","site","reward","url","title","checkedAt","confidence","status"],offer_rows)
    write_csv(DATA/'guide_candidates.csv',["game","title","url","source","checkedAt","status"],guide_rows)
    write_csv(DATA/'trend_mentions.csv',["game","source","title","url","publishedAt","checkedAt","score","status"],trend_rows)
    status={"lastRun":NOW,"offerCandidates":len(offer_rows),"guideCandidates":len(guide_rows),"trendMentions":len(trend_rows),
            "note":"自動収集結果は候補です。確認後に公開データへ反映してください。"}
    (DATA/'collection_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(status,ensure_ascii=False))

if __name__ == '__main__': main()
