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
* games that already have a **guide** (a published guide page, a registry entry whose page exists, a guide spec whose
  page exists, a completed earlier daily batch, a guide page added on any other remote branch, or a game that is
  in an open pull request) are excluded with the reason. Material that is *not* a guide - a games.csv catalog row,
  a research dossier, a guide spec without a page - never excludes a game: it is attached to the candidate as
  ``relatedMaterial`` so the editor can reuse it ("a comparison/research record exists" is not "a guide exists");
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
from datetime import date as Date, datetime, timedelta, timezone
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
STEP_TAG = re.compile(r"[『「｛{]\s*(?:StepUp|ステップアップ|多段階)\s*[』」｝}]", re.I)
LEAD_TAG = re.compile(r"^(?:【[^】]*】|\[[^\]]*\]|NEW\s+|(?:iOS|Android|iPhone)[_＿\s]+)+", re.I)
TRAIL_OS = re.compile(r"[\s_＿]*[（(]?(?:iOS|Android|iPhone|アンドロイド)[)）]?\s*$", re.I)
COND_SPLIT = re.compile(r"[（(]| 初回| 新規| アプリ| 条件達成| 任意の| \d| (?:レベル|ステージ|第|Lv|LV|チュートリアル|ゲームクリア|累計)|[\s_＿](?:iOS|Android)\b|_")
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
    s = STEP_TAG.sub("", s).strip()
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


STEPUP_WORDS = re.compile(r"StepUp|ステップアップ|多段階|各ミッション|各成果地点|STEP\s*\d", re.I)
SINGLE_WORDS = re.compile(r"(?:レベル|Lv\.?|ステージ|チャプター|ワールド|フロア|ランク|勝利|プレイヤーレベル|ユーザーレベル)\s*[0-9０-９,]+\s*(?:以上)?\s*(?:を)?(?:クリア|到達|達成|完成|オープン|解放)"
                         r"|ポイント獲得条件】記載の条件を達成|(?:クリア|到達|達成|アンロック|オープン|読了|解放)\s*[0-9,]+\s*[PpＰ円]|(?:クリア|到達|達成|アンロック|読了)\s*$")
SERVICE_WORDS = re.compile(r"初回購入|初回投票|契約完了|口座|クレジットカード|予約|査定|入金|チャージ完了|ご利用|定期購読|無料会員|資料請求|申込|申し込み|LINE友だち|ログインし、利用規約")


def kind_hint(title_hint: str) -> str:
    """Rough offer-shape hint from a listing title: stepup / single / service / unknown (never a verification)."""
    t = unicodedata.normalize("NFKC", str(title_hint or ""))
    if STEPUP_WORDS.search(t):
        return "stepup"
    if SERVICE_WORDS.search(t) and not SINGLE_WORDS.search(t):
        return "service"
    if SINGLE_WORDS.search(t):
        return "single"
    return "unknown"


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


def _registry_guides(root: Path) -> dict[str, str]:
    """Registry entries (site-guides.js / site-researched-guides.js) whose guide page exists in the repository."""
    out: dict[str, str] = {}
    for js in ("site-researched-guides.js", "site-guides.js"):
        p = root / js
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for m in re.finditer(r'^\s{2}"([^"]+)":\s*\{(.*?)^\s{2}\}', text, re.M | re.S):
            hrefs = re.findall(r'href:\s*"([^"#?]+)"', m.group(2))
            if any(re.fullmatch(r"[a-z0-9-]+-guide\.html|township-lv\d+\.html", h) and (root / h).is_file() for h in hrefs):
                out.setdefault(norm_key(m.group(1)), f"guide_registry:{js}")
        for title in re.findall(r'title:\s*"([^"]+?)\s*ポイ活攻略"', text):
            out.setdefault(norm_key(title), f"guide_registry:{js}")
    return out


def existing_index(root: Path = ROOT, extra: list[str] | None = None, remote_pages: dict[str, str] | None = None) -> dict[str, str]:
    """norm_key(name) -> why a *guide* already exists (or is already in flight).

    Only guides count: published guide pages, registry entries pointing at an existing page, guide specs whose page
    exists, completed daily batches, guide pages on other remote branches, games in an open pull request.
    games.csv rows and research dossiers are NOT guides - see :func:`related_material_index`.
    """
    idx: dict[str, str] = {}
    idx.update(_guide_h1_names(root))
    for k, why in _registry_guides(root).items():
        idx.setdefault(k, why)
    for spec in sorted((root / "research").glob("new-guides/*/*.json")):
        try:
            data = json.loads(spec.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        name = data.get("game") or data.get("name")
        page = data.get("file")
        if isinstance(name, str) and name and isinstance(page, str) and (root / page).is_file():
            idx.setdefault(norm_key(name), f"guide_spec:{spec.relative_to(root)}")
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


def related_material_index(root: Path = ROOT) -> dict[str, list[dict]]:
    """norm_key(name) -> non-guide material that already exists (never an exclusion reason).

    * ``catalog``          a games.csv comparison-catalog row (the game has a detail/comparison page, not a guide);
    * ``research_dossier`` research/new-games/*/dossiers/*.json (collected research, no published article);
    * ``guide_spec_only``  research/new-guides/*/*.json whose guide page was never published.
    """
    out: dict[str, list[dict]] = {}

    def add(name: object, kind: str, ref: str) -> None:
        if isinstance(name, str) and name.strip():
            out.setdefault(norm_key(name), []).append({"kind": kind, "ref": ref})

    catalog = root / "games.csv"
    if catalog.exists():
        with catalog.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                add(row.get("name"), "catalog", "games.csv")
    for path in sorted((root / "research").glob("new-games/*/dossiers/*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        ref = str(path.relative_to(root))
        for name in [data.get("game"), data.get("name"), (data.get("identity") or {}).get("name"), *(data.get("aliases") or [])]:
            add(name, "research_dossier", ref)
    for path in sorted((root / "research").glob("new-guides/*/*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        page = data.get("file")
        if isinstance(page, str) and not (root / page).is_file():
            add(data.get("game") or data.get("name"), "guide_spec_only", str(path.relative_to(root)))
    return out


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
            return why + " (name-prefix match: confirm the store identity)"
    return None


def _related(key: str, rel: dict[str, list[dict]]) -> list[dict]:
    if key in rel:
        return rel[key]
    for k, items in rel.items():
        if len(k) >= 4 and len(key) >= 4 and (key.startswith(k) or k.startswith(key)):
            return [{**i, "match": "name-prefix"} for i in items]
    return []


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
    related = related_material_index(root)
    holds = previous_holds(root)
    groups: dict[str, dict] = {}

    def add(name: str, row: dict) -> None:
        key = norm_key(name)
        if not key:
            return
        g = groups.setdefault(key, {"game": name, "key": key, "rows": [], "listingRewardHintYen": None, "queueRank": None,
                                    "verifiedRewardYen": None, "sources": set(), "osHints": set(), "newToday": False,
                                    "likelyGame": False, "kindHints": set(), "offerUrls": {}, "firstSeenJst": None})
        g["rows"].append(row)
        g["sources"].add(row["source"])
        if row.get("kind"):
            g["kindHints"].add(row["kind"])
        if row.get("url") and row.get("source"):
            g["offerUrls"].setdefault(row["source"], [])
            if row["url"] not in g["offerUrls"][row["source"]]:
                g["offerUrls"][row["source"]].append(row["url"])
        if row.get("os"):
            g["osHints"].add(row["os"])
        g["newToday"] = g["newToday"] or bool(row.get("isNewToday"))
        first_seen = jst_date(row.get("firstSeen"))
        if first_seen and (not g.get("firstSeenJst") or first_seen < g["firstSeenJst"]):
            g["firstSeenJst"] = first_seen
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
                   "firstSeen": it.get("firstSeen"),
                   "classification": it.get("classification"), "isNewToday": it.get("isNewToday"), "os": os_hint(hint),
                   "kind": kind_hint(hint), "rewardHintYen": reward_hint(hint, it.get("source"), rates)})

    candidates = []
    for key, g in groups.items():
        g["sources"], g["osHints"] = sorted(s for s in g["sources"] if s), sorted(g["osHints"])
        g["kindHints"] = sorted(g["kindHints"])
        # Days the scan has known this offer. The monitor's first scan (a baseline day on which ~145 offers were
        # first seen at once) is not a listing date: such offers are "listed at least since the baseline".
        if g["firstSeenJst"]:
            g["listedDays"] = (Date.fromisoformat(date) - Date.fromisoformat(g["firstSeenJst"])).days
        if is_aggregator(g["game"]):
            excluded.append({"game": g["game"], "reason": "aggregator_or_reward_wall_not_a_single_game"})
            continue
        why = _covered(key, idx)
        if why:
            excluded.append({"game": g["game"], "reason": "already_covered", "coveredBy": why})
            continue
        if key in holds:
            g["previouslyHeld"] = holds[key]
        rel = _related(key, related)
        if rel:
            g["relatedMaterial"] = rel  # information only: never a reason to skip the game
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
