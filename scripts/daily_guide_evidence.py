#!/usr/bin/env python3
"""Record today's first-party Warau offer pages for the daily guide routine (evidence only, no publication).

One GET per point_id (plus optional review pages). For each page it stores the retrieval time, HTTP status,
SHA-256 of the response, the parsed title / OS / condition / install-day deadline / every StepUp row and the
displayed total, and checks that the steps add up to the displayed total. Review entries are indexed by
(date, attribute, title) only — the review bodies are not copied into the repository.

A page that cannot be read is recorded as ``live: false`` with the reason. It is never interpreted as
"offer ended" or "0 pt" (AGENTS.md §4).

    python scripts/daily_guide_evidence.py --date 2026-11-05 --slug mystery-town 206151 206152 [--reviews 5]
    # -> research/daily-guides/2026-11-05/evidence/<slug>-offers.json
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"
WARAU = "https://www.warau.jp/contents/point/pointEntrance.php?point_id={pid}"


def fetch(url: str) -> tuple[int, bytes]:
    proc = subprocess.run(["curl", "-sSL", "--max-time", "30", "-A", UA, "-w", "\n%{http_code}", url], capture_output=True)
    body, _, code = proc.stdout.rpartition(b"\n")
    try:
        return int(code.decode() or 0), body
    except ValueError:
        return 0, proc.stdout


def page_text(raw: str) -> str:
    t = re.sub(r"<(script|style)[\s\S]*?</\1>", "", raw)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = html.unescape(t).replace("\xa0", " ").replace("\r", "")
    t = re.sub(r"[ \t　]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t)


def _int(value: str) -> int:
    return int(value.replace(",", ""))


def parse_offer(raw: str) -> dict:
    t = page_text(raw)
    title = (re.search(r"<title>(.*?)</title>", raw, re.S) or [None, ""])[1].split("｜")[0].strip()
    out: dict = {"title": html.unescape(title), "live": "獲得条件" in t and "達成条件\n獲得pt" in t}
    if "こちらのページは表示できません" in t:
        out["live"], out["unavailableReason"] = False, "page_not_viewable_publicly"
    elif "掲載終了のご案内" in t or "広告にアクセスすることができませんでした" in t:
        # Warau shows the same notice for a pause and for an end, so this records only what was shown.
        out["live"], out["unavailableReason"] = False, "listing_end_notice_shown"
        out["relatedPointIds"] = sorted(set(re.findall(r"point_id=(\d+)&(?:amp;)?pl=endEntrance(?!Similar)", raw)))
    m = re.search(r"本日インストールの場合、達成期限は\s*(\d{4}年\d+月\d+日)", t)
    out["deadlineIfInstalledToday"] = m.group(1) if m else None
    m = re.search(r"■獲得条件\s*\n(.+)", t)
    out["condition"] = m.group(1).strip() if m else None
    steps = []
    i = t.find("達成条件\n獲得pt")
    j = t.find("\n累計", i) if i >= 0 else -1
    if i >= 0 and j > i:
        seg = [s.strip() for s in t[i + len("達成条件\n獲得pt"):j].split("\n") if s.strip()]
        k = 0
        while k < len(seg):
            if k + 2 < len(seg) and seg[k + 2] == "pt" and re.fullmatch(r"[\d,]+", seg[k + 1]):
                steps.append({"condition": seg[k], "rewardPt": _int(seg[k + 1])})
                k += 3
            else:
                k += 1
    out["steps"] = steps
    m = re.search(r"\n累計\s*\n([\d,]+)\s*\npt", t)
    out["totalPt"] = _int(m.group(1)) if m else None
    out["stepSum"] = sum(s["rewardPt"] for s in steps)
    out["stepSumMatchesTotal"] = bool(steps) and out["totalPt"] == out["stepSum"]
    # Temporary increase: "10,510pt\n →\n最大\n11,040\npt\n 2026年11月07日まで"
    m = re.search(r"([\d,]+)pt\s*\n\s*→\s*\n\s*最大\s*\n\s*([\d,]+)\s*\n\s*pt\s*\n\s*(\d{4}年\d{1,2}月\d{1,2}日)まで", t)
    out["temporaryIncrease"] = {"regularPt": _int(m.group(1)), "increasedPt": _int(m.group(2)), "until": m.group(3)} if m else None
    # An end/unavailable page lists *other* offers; never read their OS or advertiser as this offer's.
    m = re.search(r"^(iOS|Android)\s*$", t, re.M) if out["live"] else None
    out["os"] = m.group(1) if m else None
    m = re.search(r"広告主：(.+)", t) if out["live"] else None
    out["advertiser"] = m.group(1).strip() if m else None
    terms = t.split("クチコミ", 1)[0]  # offer terms only; never review bodies
    out["termNotes"] = [ln.strip() for ln in terms.split("\n")
                        if re.search(r"購入|課金|対象外|あんしん保証|引継|データ移行|再インストール|判定|起動", ln) and len(ln.strip()) < 200][:20]
    out["reviewIndex"] = review_index(t)
    return out


def review_index(t: str) -> list[dict]:
    rows = []
    for mm in re.finditer(r"\n([^\n]{1,30})\nさん \((.+?)\)\n(\d{4}/\d{2}/\d{2})\n((?:.+\n){1,3}?)\(([\d.]+)\)\n", t):
        rows.append({"name": mm.group(1).strip(), "attribute": mm.group(2), "date": mm.group(3).replace("/", "-"),
                     "title": mm.group(4).strip().replace("\n", " ")})
    return rows


def record(pid: str, review_pages: int = 0) -> dict:
    url = WARAU.format(pid=pid)
    code, body = fetch(url)
    raw = body.decode("utf-8", "replace")
    entry = {"pointId": pid, "url": url, "retrievedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "httpStatus": code, "responseSha256": hashlib.sha256(body).hexdigest()}
    entry.update(parse_offer(raw) if code == 200 else {"live": False, "unavailableReason": f"http_{code}"})
    if review_pages and entry.get("live"):
        seen = {(r["date"], r["attribute"], r["title"]) for r in entry["reviewIndex"]}
        for page in range(2, review_pages + 1):
            time.sleep(0.5)
            c, b = fetch(url + f"&page={page}&sort=new")
            new = [r for r in review_index(page_text(b.decode("utf-8", "replace"))) if (r["date"], r["attribute"], r["title"]) not in seen] if c == 200 else []
            if not new:
                break
            for r in new:
                seen.add((r["date"], r["attribute"], r["title"]))
            entry["reviewIndex"] += new
    uniq = {(r["date"], r["attribute"], r["title"]): r for r in entry.get("reviewIndex", [])}
    entry["reviewIndex"] = sorted(uniq.values(), key=lambda r: (r["date"], r["attribute"], r["title"]), reverse=True)
    return entry


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("point_ids", nargs="+")
    ap.add_argument("--date", default=datetime.now(JST).date().isoformat())
    ap.add_argument("--slug", required=True)
    ap.add_argument("--reviews", type=int, default=0, help="also index up to N review pages")
    ap.add_argument("--recheck", action="store_true",
                    help="pre-publication re-check of an earlier batch: writes <slug>-offers-recheck-<today>.json instead")
    args = ap.parse_args(argv)
    checks = [record(pid, args.reviews) for pid in args.point_ids]
    out = {"schemaVersion": 1, "slug": args.slug, "site": "warau", "checkedAtJst": datetime.now(JST).isoformat(timespec="seconds"),
           "yenPerPoint": 1, "yenPerPointSource": "https://www.warau.jp/help/qa/1475/", "checks": checks}
    name = f"{args.slug}-offers-recheck-{out['checkedAtJst'][:10].replace('-', '')}.json" if args.recheck else f"{args.slug}-offers.json"
    path = ROOT / "research" / "daily-guides" / args.date / "evidence" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for c in checks:
        print(c["pointId"], c.get("os"), "live" if c.get("live") else c.get("unavailableReason"), c.get("totalPt"), "sum-ok" if c.get("stepSumMatchesTotal") else "SUM-MISMATCH",
              len(c.get("steps", [])), "steps", len(c.get("reviewIndex", [])), "reviews")
    print("wrote", path.relative_to(ROOT))
    return 0 if all(c.get("live") and c.get("stepSumMatchesTotal") for c in checks) else 2


if __name__ == "__main__":
    sys.exit(main())
