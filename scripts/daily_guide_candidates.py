#!/usr/bin/env python3
"""List today's new-game guide candidates from the existing daily scan outputs (read-only helper).

This does NOT replace the daily acquisition (``refresh-verified-offers.yml`` -> ``daily_scan_review.py`` ->
``write_new_game_content_queue.py``). It only reads what that run already committed and turns it into a
reviewable list for the daily guide-production routine:

* ``data/new_game_content_queue.json``  (top-five handoff, verified reward metadata)
* ``data/new_game_monitor.json``        (every candidate the same scan exposed publicly: today + continuing)

Rules it enforces (fail closed):

* both inputs must carry a ``checkedAt`` whose Japan date equals the production date; otherwise nothing is
  ranked and ``status`` is ``stale_input`` (a previous day's amount must never be reused as today's);
* listing amounts are only *hints* (``listingRewardHintYen``) taken from the scan's own title text for sources
  whose face value is 1 point = 1 yen in ``config/point_value_rates.json``; they are never a verified reward;
* games that already have a guide (published pages, guide registries, catalog, earlier research batches,
  previous daily batches, and guide pages added on any other remote branch) are excluded with the reason;
* aggregator / reward-wall apps (Freecash etc.) and scan rows classified ``likely_non_game`` are excluded.

The routine still has to open each point-site page, identify the game and decide adoption; name grouping
here is a conservative normalisation, not an identity decision.

    python scripts/daily_guide_candidates.py                    # today (JST), writes research/daily-guides/<date>/candidates.json
    python scripts/daily_guide_candidates.py --date 2026-11-05 --scan-remote --stdout
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))
QUEUE = Path("data/new_game_content_queue.json")
MONITOR = Path("data/new_game_monitor.json")
RATES = Path("config/point_value_rates.json")
DAILY_DIR = Path("research/daily-guides")
ALIAS_FILE = DAILY_DIR / "aliases.json"
LEGACY_HOLDS = DAILY_DIR / "legacy-holds.json"

# Reward walls / survey apps that list many games: never a single-game guide.
AGGREGATORS = ("freecash", "mistplay", "cashclub", "キャッシュクラブ", "justplay", "ジャストプレイ", "pocketmoney")
# Leading wrapper tags used by point sites (【SKYFLAG】, 【注意事項必読】, NEW, iOS_ ...).
LEAD_TAG = re.compile(r"^(?:【[^】]*】|\[[^\]]*\]|NEW\s+|(?:iOS|Android|iPhone)[_＿\s]+)+", re.I)
TRAIL_OS = re.compile(r"[\s_＿]*[（(]?(?:iOS|Android|iPhone|アンドロイド)[)）]?\s*$", re.I)
COND_SPLIT = re.compile(r"[（(]| 初回| 新規| アプリ| \d| (?:レベル|ステージ|第|Lv|LV|チュートリアル|ゲームクリア|累計)|[\s_＿](?:iOS|Android)\b|_")
AMOUNT = re.compile(r"(?:最大\s*)?([0-9][0-9,]{0,9})\s*(pt|P|ポイント|円)(?![a-zA-Z])")


def _load_aliases(root: Path = ROOT) -> dict[str, str]:
    """research/daily-guides/aliases.json: {"canonical name": ["variant", ...]} reviewed by an editor."""
    path = root / ALIAS_FILE
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    raw = json.loads(path.read_text(encoding="utf-8")).get("aliases", {})
    for canonical, variants in raw.items():
        base = _plain_key(canonical)
        for v in [canonical, *variants]:
            out[_plain_key(v)] = base
    return out


def _plain_key(name: str) -> str:
    s = unicodedata.normalize("NFKC", str(name or "")).casefold()
    return re.sub(r"[\s・:：\-－‐–—ー_＿!！?？'’\"“”.,、。&＆~〜/／()（）\[\]「」【】+]+", "", s)


ALIASES: dict[str, str] = {}


def jst_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(JST).date().isoformat()


def norm_key(name: str) -> str:
    s = unicodedata.normalize("NFKC", str(name or "")).casefold()
    s = re.sub(r"[\s・:：\-－‐–—ー_＿!！?？'’\"“”.,、。&＆~〜/／()（）\[\]「」【】+]+", "", s)
    return ALIASES.get(s, s)


def display_name(title_hint: str) -> str:
    s = unicodedata.normalize("NFKC", str(title_hint or "")).strip()
    s = LEAD_TAG.sub("", s).strip()
    s = COND_SPLIT.split(s, maxsplit=1)[0].strip()
    s = TRAIL_OS.sub("", s).strip()
    return s


def os_hint(title_hint: str) -> str | None:
    t = str(title_hint or "")
    ios = bool(re.search(r"iOS|iPhone", t, re.I))
    android = bool(re.search(r"Android|アンドロイド", t, re.I))
    if ios and not android:
        return "iOS"
    if android and not ios:
        return "Android"
    return None


def reward_hint(title_hint: str, source: str, rates: dict) -> int | None:
    """Largest amount in the scan's title text, only where 1 unit = 1 yen is a reviewed contract."""
    rate = (rates.get(source) or {}).get("yenPerPoint")
    best = None
    for num, unit in AMOUNT.findall(str(title_hint or "")):
        value = int(num.replace(",", ""))
        if unit == "円" or rate == 1:
            best = value if best is None else max(best, value)
    return best


def is_aggregator(name: str) -> bool:
    k = norm_key(name)
    return any(norm_key(a) in k for a in AGGREGATORS)


# ---------------------------------------------------------------- existing guides / history
def _guide_h1_names(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for page in sorted(root.glob("*-guide.html")) + sorted(root.glob("township-lv*.html")):
        m = re.search(r"<h1>(.*?)</h1>", page.read_text(encoding="utf-8", errors="replace"), re.S)
        if m:
            name = re.sub(r"<[^>]+>", "", m.group(1)).replace("ポイ活攻略", "").strip()
            out[norm_key(name)] = f"published_guide:{page.name}"
    return out


def existing_index(root: Path = ROOT, extra: list[str] | None = None, remote_pages: dict[str, str] | None = None) -> dict[str, str]:
    """norm_key(name) -> why it is already covered."""
    idx: dict[str, str] = {}
    idx.update(_guide_h1_names(root))
    catalog = root / "games.csv"
    if catalog.exists():
        with catalog.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("name"):
                    idx.setdefault(norm_key(row["name"]), "catalog:games.csv")
    for js in ("site-researched-guides.js", "site-guides.js"):
        p = root / js
        if p.exists():
            text = p.read_text(encoding="utf-8")
            for name in re.findall(r'^\s{2}"([^"]+)":\s*\{', text, re.M):
                idx.setdefault(norm_key(name), f"guide_registry:{js}")
            for title in re.findall(r'title:\s*"([^"]+?)\s*ポイ活攻略"', text):
                idx.setdefault(norm_key(title), f"guide_registry:{js}")
    for spec in sorted((root / "research").glob("new-guides/*/*.json")) + sorted((root / "research").glob("new-games/*/dossiers/*.json")):
        try:
            data = json.loads(spec.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        name = data.get("game") or data.get("name") or (data.get("identity") or {}).get("name")
        if isinstance(name, str) and name:
            idx.setdefault(norm_key(name), f"research_batch:{spec.relative_to(root)}")
    for sel in sorted((root / DAILY_DIR).glob("*/selection.json")):
        try:
            data = json.loads(sel.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for item in data.get("decisions", []):
            if item.get("decision") == "completed":
                for n in [item.get("game"), *item.get("aliases", [])]:
                    if n:
                        idx.setdefault(norm_key(n), f"daily_batch:{sel.parent.name}")
    for k, why in (remote_pages or {}).items():
        idx.setdefault(k, why)
    for n in extra or []:
        idx.setdefault(norm_key(n), "excluded_by_routine:open_pull_request")
    return idx


def previous_holds(root: Path = ROOT) -> dict[str, dict]:
    holds: dict[str, dict] = {}
    legacy = root / LEGACY_HOLDS
    if legacy.exists():
        for item in json.loads(legacy.read_text(encoding="utf-8")).get("holds", []):
            holds[norm_key(item["game"])] = {"date": item.get("date"), "reason": item.get("reason"), "recordedIn": item.get("recordedIn")}
    for sel in sorted((root / DAILY_DIR).glob("*/selection.json")):
        try:
            data = json.loads(sel.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for item in data.get("decisions", []):
            if item.get("decision") == "held" and item.get("game"):
                holds[norm_key(item["game"])] = {"date": sel.parent.name, "reason": item.get("reason")}
    return holds


def remote_branch_guides(root: Path = ROOT) -> dict[str, str]:
    """Guide pages present on any fetched remote branch but not on origin/main (unmerged drafts)."""
    out: dict[str, str] = {}
    try:
        refs = subprocess.run(["git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"],
                              cwd=root, capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return out
    for ref in refs:
        if ref in ("origin/main", "origin/HEAD", "origin"):
            continue
        try:
            names = subprocess.run(["git", "diff", "--name-only", "--diff-filter=A", f"origin/main...{ref}"],
                                   cwd=root, capture_output=True, text=True, check=True).stdout.split()
        except subprocess.CalledProcessError:
            continue
        for name in names:
            if re.fullmatch(r"[a-z0-9-]+-guide\.html", name):
                try:
                    html = subprocess.run(["git", "show", f"{ref}:{name}"], cwd=root, capture_output=True, text=True, check=True).stdout
                except subprocess.CalledProcessError:
                    continue
                m = re.search(r"<h1>(.*?)</h1>", html, re.S)
                if m:
                    game = re.sub(r"<[^>]+>", "", m.group(1)).replace("ポイ活攻略", "").strip()
                    out.setdefault(norm_key(game), f"unmerged_branch:{ref}:{name}")
    return out


# ---------------------------------------------------------------- build
def _covered(key: str, idx: dict[str, str]) -> str | None:
    if key in idx:
        return idx[key]
    for k, why in idx.items():
        # "モーマンタイム" vs "モーマンタイム【StepUp】" style suffixes; require a meaningful length.
        if len(k) >= 4 and len(key) >= 4 and (key.startswith(k) or k.startswith(key)):
            return why
    return None


def build(date: str, root: Path = ROOT, extra_exclude: list[str] | None = None, scan_remote: bool = False) -> dict:
    queue = json.loads((root / QUEUE).read_text(encoding="utf-8"))
    monitor = json.loads((root / MONITOR).read_text(encoding="utf-8"))
    rates = json.loads((root / RATES).read_text(encoding="utf-8"))["sources"]
    out = {
        "schemaVersion": 1,
        "productionDate": date,
        "inputs": {
            "contentQueue": {"path": str(QUEUE), "checkedAt": queue.get("checkedAt"), "checkedDateJst": jst_date(queue.get("checkedAt")),
                             "rankingComplete": queue.get("rankingComplete"), "count": queue.get("count")},
            "monitor": {"path": str(MONITOR), "checkedAt": monitor.get("checkedAt"), "checkedDateJst": jst_date(monitor.get("checkedAt")),
                        "items": len(monitor.get("items", [])), "counts": monitor.get("counts"), "displayLimits": monitor.get("displayLimits")},
        },
        "candidateOnly": True,
        "publicationAuthorized": False,
        "rewardNote": "listingRewardHintYen is the largest amount in the scan's own listing text (1pt=1円 sources only). "
                      "It is not a verified reward; open the point-site page before using any amount.",
    }
    stale = [k for k, v in out["inputs"].items() if v["checkedDateJst"] != date]
    if stale:
        out.update(status="stale_input", staleInputs=stale, candidates=[], excluded=[])
        return out

    ALIASES.clear()
    ALIASES.update(_load_aliases(root))
    remote = remote_branch_guides(root) if scan_remote else {}
    idx = existing_index(root, extra_exclude, remote)
    holds = previous_holds(root)
    groups: dict[str, dict] = {}

    def add(name: str, row: dict) -> None:
        key = norm_key(name)
        if not key:
            return
        g = groups.setdefault(key, {"game": name, "key": key, "rows": [], "listingRewardHintYen": None, "queueRank": None,
                                    "verifiedRewardYen": None, "sources": set(), "osHints": set(), "newToday": False,
                                    "likelyGame": False})
        g["rows"].append(row)
        g["sources"].add(row["source"])
        if row.get("os"):
            g["osHints"].add(row["os"])
        g["newToday"] = g["newToday"] or bool(row.get("isNewToday"))
        g["likelyGame"] = g["likelyGame"] or row.get("from") == "content_queue" or row.get("classification") == "likely_game"
        if row.get("rewardHintYen") is not None:
            g["listingRewardHintYen"] = max(g["listingRewardHintYen"] or 0, row["rewardHintYen"])

    for it in queue.get("items", []):
        name = it.get("game", "")
        for ev in it.get("pointSiteEvidence", []):
            add(name, {"from": "content_queue", "source": ev.get("source"), "url": ev.get("url"), "detailConfirmed": ev.get("detailConfirmed"),
                       "rewardVerified": ev.get("rewardVerified"), "rewardHintYen": ev.get("rewardYen"), "isNewToday": None, "os": None})
        g = groups.get(norm_key(name))
        if g:
            g["queueRank"] = it.get("rank")
            g["verifiedRewardYen"] = it.get("maxObservedRewardYen") if it.get("verifiedRewardSourceCount") else None

    excluded = []
    for it in monitor.get("items", []):
        hint = it.get("titleHint", "")
        name = display_name(hint)
        if it.get("classification") == "likely_non_game":
            excluded.append({"game": name, "reason": "scan_classified_likely_non_game", "titleHint": hint[:120]})
            continue
        if not name or len(norm_key(name)) < 2 or "件 新着順" in hint:
            excluded.append({"game": name, "reason": "listing_page_or_unparsable_title", "titleHint": hint[:120]})
            continue
        add(name, {"from": "monitor", "source": it.get("source"), "url": it.get("firstPartyCandidateUrl"), "titleHint": hint[:200],
                   "classification": it.get("classification"), "isNewToday": it.get("isNewToday"), "os": os_hint(hint),
                   "rewardHintYen": reward_hint(hint, it.get("source"), rates)})

    candidates = []
    for key, g in groups.items():
        g["sources"], g["osHints"] = sorted(s for s in g["sources"] if s), sorted(g["osHints"])
        if is_aggregator(g["game"]):
            excluded.append({"game": g["game"], "reason": "aggregator_or_reward_wall_not_a_single_game"})
            continue
        why = _covered(key, idx)
        if why:
            excluded.append({"game": g["game"], "reason": "already_covered", "coveredBy": why})
            continue
        if key in holds:
            g["previouslyHeld"] = holds[key]
        candidates.append(g)
    # Rows the scan itself classified as games first; "review" rows (apps, services, unclear) after them.
    candidates.sort(key=lambda g: (not g["likelyGame"], -(g["verifiedRewardYen"] or g["listingRewardHintYen"] or 0), g["queueRank"] or 99, g["game"]))
    for i, g in enumerate(candidates, 1):
        g["order"] = i
    out.update(status="ok", candidateCount=len(candidates), candidates=candidates,
               excluded=sorted(excluded, key=lambda e: (e["reason"], e["game"])), excludedCount=len(excluded))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", default=datetime.now(JST).date().isoformat(), help="production date (JST, YYYY-MM-DD)")
    ap.add_argument("--exclude", action="append", default=[], help="game name already in an open pull request (repeatable)")
    ap.add_argument("--scan-remote", action="store_true", help="also exclude guide pages added on fetched remote branches")
    ap.add_argument("--stdout", action="store_true", help="print instead of writing candidates.json")
    ap.add_argument("--top", type=int, default=40, help="rows to print in the summary")
    args = ap.parse_args(argv)
    result = build(args.date, ROOT, args.exclude, args.scan_remote)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.stdout:
        sys.stdout.write(text)
    else:
        out = ROOT / DAILY_DIR / args.date / "candidates.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)} status={result['status']}")
        for g in result.get("candidates", [])[: args.top]:
            amount = g["verifiedRewardYen"] or g["listingRewardHintYen"]
            print(f"{g['order']:>3} {'G' if g['likelyGame'] else '?'} {g['game'][:40]:<40} hint={amount} sources={','.join(g['sources'])} os={','.join(g['osHints'])}"
                  + (f" previouslyHeld={g['previouslyHeld']['date']}" if g.get("previouslyHeld") else ""))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
