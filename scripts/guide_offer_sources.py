#!/usr/bin/env python3
"""First-party offer-page adapters for the daily guide routine (read-only evidence, no publication).

``scripts/daily_guide_evidence.py`` only understood Warau StepUp tables. The daily candidate list, however,
is dominated by other point sites and by *single-condition* offers ("レベル300クリア 700P"). This module turns one
public offer page of Warau / Amefuri / COINCOME / Moppy into one normalized evidence record, so the routine can
verify an offer on whichever site actually exposes its conditions.

Rules (AGENTS.md §4 / docs/daily-guide-routine.md):

* one GET per page, no login, no access-control workaround, only the four registered first-party hosts;
* every state is explicit and never collapsed: ``readable`` / ``steps_not_public`` / ``not_viewable`` /
  ``ended`` / ``not_found`` / ``http_error`` / ``parse_failed`` / ``identity_mismatch``. A failed or unreadable
  page is **never** read as "offer ended" or "0 pt";
* reward units are never mixed. Each record carries ``pointUnit`` and ``yenPerPoint`` (Warau pt = 1 yen,
  Moppy P = 1 yen, Amefuri pt = 0.1 yen - "10pt=1円" must be printed on the page, COINCOME shows yen directly).
  Different sites pay different amounts for the same game; a record always describes exactly one site;
* ``kind`` is ``stepup`` (every Step readable), ``single`` (one achievement condition, one reward) or
  ``unknown``. A StepUp page that does not publish its Steps (Moppy: "各成果地点は POINT GET をタップ後に遷移する
  ページでご確認ください") is ``steps_not_public`` and can never back an article table;
* a boosted amount ("Ptアップ" / sale) is recorded in ``temporaryIncrease`` - the end date is only filled in when
  the page states one.
"""
from __future__ import annotations

import hashlib
import html
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlsplit

if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import daily_guide_evidence as warau_evidence  # noqa: E402

SITES = {
    "warau": {"label": "ワラウ", "hosts": {"www.warau.jp"}},
    "amefuri": {"label": "アメフリ", "hosts": {"www.amefri.net", "amefri.net"}},
    "coincome": {"label": "COINCOME", "hosts": {"cimcome.jp"}},
    "moppy": {"label": "モッピー", "hosts": {"pc.moppy.jp"}},
}
STATES = ("readable", "steps_not_public", "not_viewable", "ended", "not_found", "http_error", "parse_failed", "identity_mismatch")
# Only a readable page with every condition may back an article's offer table.
ARTICLE_READY_STATES = ("readable",)

Fetcher = Callable[[str], "tuple[int, bytes]"]


# ---------------------------------------------------------------- helpers
def _unesc(value: str) -> str:
    # Some Amefuri titles arrive double escaped ("Puzzle &amp;amp; Art").
    return html.unescape(html.unescape(value or "")).strip()


def _num(value: str) -> int:
    return int(str(value).replace(",", ""))


def _text(raw: str) -> str:
    return warau_evidence.page_text(raw)


def _nfkc(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "")


def site_and_offer_id(url: str) -> tuple[str, str] | None:
    """(site, offerId) for a registered first-party offer-detail URL, else None."""
    try:
        parts = urlsplit(str(url or ""))
    except ValueError:
        return None
    if parts.scheme != "https" or parts.username or parts.password:
        return None
    host, path, query = (parts.hostname or "").lower(), parts.path, parts.query
    if host in SITES["warau"]["hosts"] and path.endswith("pointEntrance.php"):
        m = re.search(r"(?:^|&)point_id=(\d+)", query)
        return ("warau", m.group(1)) if m else None
    if host in SITES["amefuri"]["hosts"]:
        m = re.fullmatch(r"/detail/id/(\d+)", path)
        return ("amefuri", m.group(1)) if m else None
    if host in SITES["coincome"]["hosts"]:
        m = re.fullmatch(r"/campaigns/details/(\d+)", path)
        return ("coincome", m.group(1)) if m else None
    if host in SITES["moppy"]["hosts"] and path.endswith("/ad/detail.php"):
        m = re.search(r"(?:^|&)(?:s_id|site_id)=(\d+)", query)
        return ("moppy", m.group(1)) if m else None
    return None


def canonical_offer_url(site: str, offer_id: str) -> str:
    return {
        "warau": f"https://www.warau.jp/contents/point/pointEntrance.php?point_id={offer_id}",
        "amefuri": f"https://www.amefri.net/detail/id/{offer_id}",
        "coincome": f"https://cimcome.jp/campaigns/details/{offer_id}",
        "moppy": f"https://pc.moppy.jp/ad/detail.php?site_id={offer_id}",
    }[site]


_OS_TAIL = re.compile(r"[\s_＿]*[（(【\[]?\s*(iOS|Android|iPhone)\s*[)）】\]]?\s*(?:用)?\s*$", re.I)
_OS_HEAD = re.compile(r"^\s*(iOS|Android|iPhone)[_＿\s]+", re.I)
_TAGS = re.compile(r"[（(【『「｛{\[]\s*(?:StepUp|ステップアップ|多段階)\s*[)）】』」｝}\]]", re.I)
_COND_PAREN = re.compile(r"[（(][^（()）]*(?:到達|クリア|達成|解放|アンロック|オープン|読了|チャージ|課金|完成|勝利)[^（()）]*[)）]\s*$")


def os_from_title(title: str) -> str | None:
    t = _nfkc(title)
    m = _OS_HEAD.match(t) or _OS_TAIL.search(t)
    if m:
        return "iOS" if m.group(1).lower() in ("ios", "iphone") else "Android"
    return None


def clean_game_name(title: str) -> str:
    """Game name from a listing/detail title (OS tags, StepUp tags and a trailing condition removed)."""
    t = _unesc(title)
    t = _OS_HEAD.sub("", t)
    t = _TAGS.sub("", t)
    t = re.sub(r"[\s_＿]*[（(【\[]\s*(iOS|Android|iPhone)\s*[)）】\]]", "", t, flags=re.I)
    t = _OS_TAIL.sub("", t)
    t = _COND_PAREN.sub("", t)
    t = re.sub(r"(?:の詳細|でポイントを貯める|でポイントが貯まる).*$", "", t)
    t = _COND_PAREN.sub("", t)
    return re.sub(r"\s+", " ", t).strip(" _＿")


_INQUIRY_LINE = re.compile(r"問い合わせ|問合せ|調査|保証|申請期限")  # inquiry / investigation / guarantee windows are not achievement deadlines
_DEADLINE_PATTERNS = (
    # (regex, basis) - the first number of each pattern; all distinct numbers must agree (else the page is ambiguous)
    (re.compile(r"成果受付期限\s*[：:]\s*(?:広告)?クリックから(\d+)日以内(?!\s*[（(])"), "click"),
    (re.compile(r"[：:]\s*(?:広告)?クリックから(\d+)日以内\s*[（(]上記以外[^）)]*[）)]"), "click"),
    (re.compile(r"獲得条件達成期限はインストール日から起算して(\d+)日以内"), "install"),
    (re.compile(r"広告クリックから[（(]当日を1日目とし[)）]\s*(\d+)日以内"), "click"),
    (re.compile(r"(?:ミッション参加|参加)から(?:[（(]当日を1日目とし[)）])?\s*(\d+)日以内"), "mission"),
    (re.compile(r"クリック後[、,]?\s*(\d+)日以内"), "click"),
    (re.compile(r"(?:インストール後|インストール日から(?:起算して)?)[、,]?\s*(\d+)日以内"), "install"),
    (re.compile(r"広告クリックから[、,]?\s*(\d+)日以内に?(?!\s*[（(])"), "click"),
)
_BULLET_DEADLINE = re.compile(r"^[・･•]\s*(\d+)日以内に(.+?)\s*$")
_PAREN_DEADLINE = re.compile(r"(?:広告)?クリックから(\d+)日以内\s*[（(]([^）)]+)[）)]")


def _norm_cond(text: str) -> str:
    return re.sub(r"[\s　を・]", "", _nfkc(text or ""))


_LEADING_DEADLINE = re.compile(r"^\s*(\d+)日以内に\s*(.+)$")


def read_deadlines(text: str, steps: list[dict]) -> dict:
    """Deadlines from an offer's condition text.

    Returns ``{"state": "ok"|"missing"|"ambiguous", "days": int|None, "basis": str|None, "byStep": [int|None, ...]}``.
    ``days`` is the one deadline all conditions share (None when Steps differ - each step then carries its own).

    Sources, all of which must agree: a deadline written in the step's own condition ("1日以内に村レベル20をクリア"),
    a bullet list ("・5日以内に村レベル45をクリア"), a per-condition 成果受付期限 line ("…5日以内（村レベル45をクリア）"),
    a common "上記以外" deadline, and one common deadline for the whole offer. A step is never given a number that
    no page text states for it, and a page whose numbers disagree is ``ambiguous`` - never readable.
    """
    lines = [ln for ln in _nfkc(text).split("\n") if not _INQUIRY_LINE.search(ln)]
    joined = "\n".join(lines)
    stated: dict[str, set[int]] = {}   # normalized condition -> every deadline the page states for it

    def note(cond: str, days: int) -> None:
        stated.setdefault(_norm_cond(cond), set()).add(days)

    for ln in lines:
        m = _BULLET_DEADLINE.match(ln.strip())
        if m:
            note(m.group(2), int(m.group(1)))
        for m in _PAREN_DEADLINE.finditer(ln):
            note(m.group(2), int(m.group(1)))
    plain_conditions: list[str] = []
    for step in steps:
        m = _LEADING_DEADLINE.match(_nfkc(step["condition"]))
        if m:
            note(m.group(2), int(m.group(1)))
            plain_conditions.append(m.group(2))
        else:
            plain_conditions.append(step["condition"])
    found: dict[int, str] = {}
    for pattern, basis in _DEADLINE_PATTERNS:
        for m in pattern.finditer(joined):
            found.setdefault(int(m.group(1)), basis)
    default = None
    for pattern, basis in _DEADLINE_PATTERNS[:2]:
        m = pattern.search(joined)
        if m:
            default = (int(m.group(1)), basis)
            break
    if any(len(v) > 1 for v in stated.values()):
        return {"state": "ambiguous", "days": None, "basis": None, "byStep": [None] * len(steps)}
    explicit = [next(iter(stated[_norm_cond(c)])) if _norm_cond(c) in stated else None for c in plain_conditions]
    if any(d is not None for d in explicit):
        # per-condition deadlines exist: the remaining steps may only take a common "上記以外" / whole-offer number
        common = default[0] if default else (next(iter(found)) if len(found) == 1 else None)
        if common is None and any(d is None for d in explicit):
            return {"state": "ambiguous", "days": None, "basis": None, "byStep": explicit}
        by_step = [d if d is not None else common for d in explicit]
        basis = default[1] if default else ("click" if "クリック" in joined else None)
        return {"state": "ok", "days": by_step[0] if len(set(by_step)) == 1 else None, "basis": basis, "byStep": by_step}
    if len(found) == 1:
        (days, basis), = found.items()
        return {"state": "ok", "days": days, "basis": basis, "byStep": [days] * len(steps)}
    if len(found) > 1:
        return {"state": "ambiguous", "days": None, "basis": None, "byStep": [None] * len(steps)}
    return {"state": "missing", "days": None, "basis": None, "byStep": [None] * len(steps)}


_BLOCK_END = ("▼却下条件", "■獲得対象外条件", "【獲得対象外】", "■獲得対象外", "▼注意", "■注意事項", "【注意事項】", "■成果調査に関して", "お問い合わせに関して", "否認条件")


def _conditions_block(text: str) -> str:
    """The part of a conditions section that states conditions and deadlines (not the refusal / notice lists)."""
    end = len(text)
    for marker in _BLOCK_END:
        i = text.find(marker)
        if 0 < i < end:
            end = i
    return text[:end]


def _apply_deadlines(ev: dict, info: dict) -> str | None:
    """Store deadlines on the evidence (offer level and per step). Returns a failure reason or None."""
    if info["state"] != "ok":
        return "deadline_ambiguous" if info["state"] == "ambiguous" else "condition_or_deadline_missing"
    ev["deadlineDays"], ev["deadlineBasis"] = info["days"], info["basis"]
    for step, days in zip(ev["steps"], info["byStep"]):
        step["deadlineDays"] = days
    return None


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _base(site: str, offer_id: str, url: str) -> dict:
    return {
        "schemaVersion": 2, "offerKey": f"{site}:{offer_id}", "site": site, "siteLabel": SITES[site]["label"],
        "offerId": offer_id, "url": url, "state": "parse_failed", "live": False, "unavailableReason": None,
        "title": None, "gameName": None, "os": None, "osSource": None, "kind": "unknown",
        "pointUnit": None, "yenPerPoint": None, "rateVerified": False,
        "conditionText": None, "deadlineDays": None, "deadlineBasis": None,
        "steps": [], "totalPt": None, "totalYen": None, "stepSumMatchesTotal": False,
        "temporaryIncrease": None,
    }


def _unavailable(ev: dict, state: str, reason: str) -> dict:
    ev.update(state=state, live=False, unavailableReason=reason)
    return ev


def _finish(ev: dict) -> dict:
    ev["live"] = ev["state"] == "readable"
    if ev["state"] != "readable" and not ev.get("unavailableReason"):
        ev["unavailableReason"] = ev["state"]
    return ev


# ---------------------------------------------------------------- Amefuri
def parse_amefuri(raw: str, offer_id: str, url: str | None = None) -> dict:
    ev = _base("amefuri", offer_id, url or canonical_offer_url("amefuri", offer_id))
    canon = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', raw)
    if canon:
        found = site_and_offer_id(canon.group(1))
        if not found or found != ("amefuri", offer_id):
            return _finish(_unavailable(ev, "identity_mismatch", "canonical_offer_mismatch"))
    title = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S)
    h1 = re.search(r"<h1[^>]*>\s*案件詳細[:：]\s*(.+?)\s*でポイントが貯まる\s*</h1>", raw, re.S)
    name = _unesc(h1.group(1)) if h1 else (_unesc(re.sub(r"の詳細.*$", "", title.group(1))) if title else "")
    if not name or "案件詳細" not in raw and "projectList" not in raw:
        t = _text(raw)
        if re.search(r"掲載(?:を)?終了|受付(?:を)?終了|終了しました", t):
            return _finish(_unavailable(ev, "ended", "listing_end_notice_shown"))
        return _finish(_unavailable(ev, "not_found" if len(t) < 400 else "parse_failed", "offer_structure_not_found"))
    ev["title"] = name
    ev["gameName"] = clean_game_name(name)
    # Labels, device badge and reward belong to the main offer block only: related-offer cards further down the
    # page carry their own "多段階" / OS labels and must never be read as this offer's.
    start = h1.start() if h1 else (title.start() if title else 0)
    end = raw.find("ポイント獲得条件", start)
    scope = raw[start:end if end > start else start + 12000]
    devices = set(re.findall(r"deviceLabel__item--(ios|android)", scope))
    if len(devices) == 1:
        ev["os"], ev["osSource"] = ("iOS" if "ios" in devices else "Android"), "page"
    elif not devices:
        ev["os"] = os_from_title(name)
        ev["osSource"] = "title" if ev["os"] else None
    text = _nfkc(_text(raw))
    ev["pointUnit"] = "pt"
    if "10pt=1円" in text:
        ev["yenPerPoint"], ev["rateVerified"] = 0.1, True
    base = re.search(r'point--base">\s*([\d,]+)\s*<', scope)
    best = re.search(r'point--best">\s*([\d,]+)\s*<', scope)
    if not best:
        return _finish(_unavailable(ev, "parse_failed", "reward_header_not_found"))
    base_yen, best_yen = (_num(base.group(1)) if base else None), _num(best.group(1))
    stepup = bool(re.search(r"labelArea__item--stepup|【多段階】", scope)) or "多段階" in name
    cond = re.search(r'<th class="table-head">成果条件</th>\s*<td class="table-data">\s*(.*?)\s*</td>', scope, re.S)
    ev["conditionText"] = _unesc(re.sub(r"<[^>]+>", "", cond.group(1))) if cond else None
    block = _conditions_block(_text(raw[raw.find("ポイント獲得条件", start):] if raw.find("ポイント獲得条件", start) > 0 else raw))
    if (base_yen is not None and base_yen < best_yen) or re.search(r"labelArea__item--ptup", scope):
        ev["temporaryIncrease"] = {"regularYen": base_yen, "increasedYen": best_yen, "until": None, "endDateStated": False}
    if stepup:
        ev["kind"] = "stepup"
        steps = []
        for m in re.finditer(r"ステップ\s*\n\s*(\d+)\s*\n\s*(.+?)\s*\n\s*(?:認証済|未認証|認証中)?\s*\n?\s*([\d,]+)\s*\n\s*pt", _text(scope)):
            pt = _num(m.group(3))
            steps.append({"condition": m.group(2).strip(), "rewardPt": pt,
                          "rewardYen": pt // 10 if pt % 10 == 0 else None})
        ev["steps"] = steps
        if not steps:
            return _finish(_unavailable(ev, "steps_not_public", "stepup_steps_not_on_page"))
        ev["totalPt"] = sum(s["rewardPt"] for s in steps)
        ev["totalYen"] = best_yen
        ev["stepSumMatchesTotal"] = ev["rateVerified"] and ev["totalPt"] == best_yen * 10
        bad = _apply_deadlines(ev, read_deadlines(block, steps))
        if bad:
            return _finish(_unavailable(ev, "parse_failed", bad))
    else:
        ev["kind"] = "single" if ev["conditionText"] else "unknown"
        ev["steps"] = [{"condition": ev["conditionText"], "rewardPt": best_yen * 10, "rewardYen": best_yen}] if ev["conditionText"] else []
        ev["totalPt"], ev["totalYen"] = best_yen * 10, best_yen
        ev["stepSumMatchesTotal"] = bool(ev["steps"]) and ev["rateVerified"]
        if ev["steps"]:
            bad = _apply_deadlines(ev, read_deadlines(block, ev["steps"]))
            if bad:
                return _finish(_unavailable(ev, "parse_failed", bad))
    ready = ev["steps"] and ev["stepSumMatchesTotal"] and ev["rateVerified"] and all(s.get("deadlineDays") for s in ev["steps"])
    if not ready:
        why = "rate_not_verified" if not ev["rateVerified"] else ("step_sum_differs_from_displayed_total" if ev["steps"] and not ev["stepSumMatchesTotal"] else "condition_or_deadline_missing")
        return _finish(_unavailable(ev, "parse_failed", why))
    ev["state"] = "readable"
    return _finish(ev)


# ---------------------------------------------------------------- COINCOME
def parse_coincome(raw: str, offer_id: str, url: str | None = None) -> dict:
    ev = _base("coincome", offer_id, url or canonical_offer_url("coincome", offer_id))
    title = re.search(r'<p class="sale__title">(.*?)</p>', raw, re.S)
    if not title:
        # The error page is served for both "no such campaign" and a removed one; the HTTP status is not used
        # because live COINCOME offers are also delivered with a 404 status.
        if "error-content" in raw or "お探しのページは見つかりません" in raw:
            return _finish(_unavailable(ev, "not_found", "campaign_page_not_found"))
        return _finish(_unavailable(ev, "parse_failed", "offer_structure_not_found"))
    name = _unesc(re.sub(r"<[^>]+>", "", title.group(1)))
    ev["title"] = name
    ev["gameName"] = clean_game_name(name)
    ev["os"] = os_from_title(name)
    ev["osSource"] = "title" if ev["os"] else None
    ev["pointUnit"], ev["yenPerPoint"], ev["rateVerified"] = "円", 1, True  # the page prints the yen-equivalent itself
    up = re.search(r'<div class="sale__up[^"]*">(.*?)</div>', raw, re.S)
    cur = base = None
    if up:
        direct = re.sub(r"<span[^>]*>.*?</span>", "", up.group(1), flags=re.S)
        m = re.search(r"([\d,]+)\s*円", re.sub(r"<[^>]+>", " ", direct))
        cur = _num(m.group(1)) if m else None
        m = re.search(r"<span[^>]*>\s*([\d,]+)\s*円", up.group(1))
        base = _num(m.group(1)) if m else None
    if cur is None:
        return _finish(_unavailable(ev, "parse_failed", "reward_header_not_found"))
    text = _nfkc(_text(raw))
    approve = re.search(r"承認条件\s*\n(.*?)(?:\n否認条件|\Z)", text, re.S)
    block = approve.group(1) if approve else ""
    if base is not None and base < cur:
        ev["temporaryIncrease"] = {"regularYen": base, "increasedYen": cur, "until": None, "endDateStated": False}
    stepup = "StepUp" in name or "ステップアップ" in name or bool(re.search(r"STEP\s*1\.", text))
    if stepup:
        ev["kind"] = "stepup"
        steps = [{"condition": m.group(2).strip(), "rewardPt": _num(m.group(3)), "rewardYen": _num(m.group(3))}
                 for m in re.finditer(r"STEP\s*(\d+)\.\s*(.+?)で【([\d,]+)\s*円】", text)]
        ev["steps"] = steps
        if not steps:
            return _finish(_unavailable(ev, "steps_not_public", "stepup_steps_not_on_page"))
        ev["totalPt"] = ev["totalYen"] = sum(s["rewardPt"] for s in steps)
        ev["stepSumMatchesTotal"] = ev["totalYen"] == cur
        bad = _apply_deadlines(ev, read_deadlines(block, steps))
        if bad:
            return _finish(_unavailable(ev, "parse_failed", bad))
    else:
        m = re.search(r"新規[^\n]*?インストール後[、,]?[^\n]*?【([^】\n]+)】", block) or re.search(r"新規[^\n]*?インストール後[、,]?\s*(?:\d+日以内に)?\s*([^\n]+)", block)
        ev["conditionText"] = m.group(1).strip() if m else None
        ev["kind"] = "single" if ev["conditionText"] else "unknown"
        ev["steps"] = [{"condition": ev["conditionText"], "rewardPt": cur, "rewardYen": cur}] if ev["conditionText"] else []
        ev["totalPt"] = ev["totalYen"] = cur
        ev["stepSumMatchesTotal"] = bool(ev["steps"])
        if ev["steps"]:
            bad = _apply_deadlines(ev, read_deadlines(block, ev["steps"]))
            if bad:
                return _finish(_unavailable(ev, "parse_failed", bad))
    if not (ev["steps"] and ev["stepSumMatchesTotal"] and all(s.get("deadlineDays") for s in ev["steps"])):
        why = "step_sum_differs_from_displayed_total" if ev["steps"] and not ev["stepSumMatchesTotal"] else "condition_or_deadline_missing"
        return _finish(_unavailable(ev, "parse_failed", why))
    ev["state"] = "readable"
    return _finish(ev)


# ---------------------------------------------------------------- Moppy
_MOPPY_COND = re.compile(
    r"^(?:新規|初回|初めて)[^\n]*?(?:インストール|ダウンロード)[^\n]*?(?:で成果となります|で条件達成となります|で報酬獲得となります|でポイント獲得)")


def parse_moppy(raw: str, offer_id: str, url: str | None = None) -> dict:
    ev = _base("moppy", offer_id, url or canonical_offer_url("moppy", offer_id))
    canon = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', raw)
    if canon:
        found = site_and_offer_id(canon.group(1))
        if not found or found != ("moppy", offer_id):
            return _finish(_unavailable(ev, "identity_mismatch", "canonical_offer_mismatch"))
    h1 = re.search(r'<h1[^>]*class="a-item__h1"[^>]*>(.*?)</h1>', raw, re.S)
    reward = re.search(r'a-item__point--now">\s*([\d,]+)\s*P', raw)
    if not h1:
        t = _text(raw)
        if re.search(r"掲載(?:を)?終了|受付(?:を)?終了|終了しました", t):
            return _finish(_unavailable(ev, "ended", "listing_end_notice_shown"))
        return _finish(_unavailable(ev, "not_found" if len(t) < 400 else "parse_failed", "offer_structure_not_found"))
    name = _unesc(re.sub(r"<[^>]+>", "", h1.group(1)))
    ev["title"] = name
    ev["gameName"] = clean_game_name(name)
    ev["os"] = os_from_title(name)
    ev["osSource"] = "title" if ev["os"] else None
    ev["pointUnit"] = "P"
    text = _nfkc(_text(raw))
    if re.search(r"1P[＝=]1円|1ポイント=1円", text + _nfkc(raw)):
        ev["yenPerPoint"], ev["rateVerified"] = 1, True
    # Moppy prints the number of user reviews ("クチコミ（N件）") in the page tabs: a first-party signal that player
    # records may exist. It is a count only - reviews are never copied and never counted as independent players.
    rc = re.search(r'data-ga-label="クチコミ"[^>]*>.*?a-list__total">（\s*(\d+)\s*件', raw, re.S)
    ev["reviewCount"] = int(rc.group(1)) if rc else None
    if not reward:
        return _finish(_unavailable(ev, "parse_failed", "reward_not_found"))
    pt = _num(reward.group(1))
    body = text.split("[PR]", 1)[1] if "[PR]" in text else text
    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    cond = None
    for i, ln in enumerate(lines[:60]):
        if ln in ("【獲得条件】", "【獲得対象】", "▼ポイント獲得条件", "■獲得条件", "■ポイント獲得条件") and i + 1 < len(lines):
            cond = lines[i + 1]
            break
        if _MOPPY_COND.match(ln):
            cond = ln
            break
    # StepUp offers print only the total; every Step lives behind "POINT GET".
    stepup = bool(re.search(r"StepUp|各成果地点|各ミッション", name + " " + (cond or ""))) or "POINT GET」をタップ後に遷移するページ" in body
    if stepup:
        ev["kind"], ev["conditionText"], ev["totalPt"] = "stepup", cond, pt
        ev["totalYen"] = pt if ev["rateVerified"] else None
        return _finish(_unavailable(ev, "steps_not_public", "stepup_steps_behind_point_get_page"))
    ev["conditionText"] = cond
    ev["kind"] = "single" if cond else "unknown"
    ev["steps"] = [{"condition": cond, "rewardPt": pt, "rewardYen": pt if ev["rateVerified"] else None}] if cond else []
    ev["totalPt"], ev["totalYen"] = pt, (pt if ev["rateVerified"] else None)
    ev["stepSumMatchesTotal"] = bool(cond)
    if not cond:
        return _finish(_unavailable(ev, "parse_failed", "condition_or_deadline_missing"))
    bad = _apply_deadlines(ev, read_deadlines(_conditions_block(body), ev["steps"]))
    if bad:
        return _finish(_unavailable(ev, "parse_failed", bad))
    if not ev["rateVerified"]:
        return _finish(_unavailable(ev, "parse_failed", "rate_not_verified"))
    ev["state"] = "readable"
    return _finish(ev)


# ---------------------------------------------------------------- Warau
def parse_warau(raw: str, offer_id: str, url: str | None = None) -> dict:
    """Warau StepUp tables via the reviewed evidence parser, plus the single-condition header."""
    ev = _base("warau", offer_id, url or canonical_offer_url("warau", offer_id))
    legacy = warau_evidence.parse_offer(raw)
    t = _text(raw)
    ev.update(title=legacy.get("title"), gameName=clean_game_name(legacy.get("title") or ""),
              pointUnit="pt", yenPerPoint=1, rateVerified=True, advertiser=legacy.get("advertiser"),
              reviewIndex=legacy.get("reviewIndex", []), termNotes=legacy.get("termNotes", []))
    if legacy.get("unavailableReason"):
        reason = legacy["unavailableReason"]
        state = "ended" if reason == "listing_end_notice_shown" else "not_viewable"
        if reason == "listing_end_notice_shown":
            ev["relatedPointIds"] = legacy.get("relatedPointIds", [])
        return _finish(_unavailable(ev, state, reason))
    ev["os"], ev["osSource"] = legacy.get("os"), ("page" if legacy.get("os") else None)
    if legacy.get("live"):
        ev.update(kind="stepup", conditionText=legacy.get("condition"), steps=legacy["steps"],
                  totalPt=legacy["totalPt"], totalYen=legacy["totalPt"], stepSumMatchesTotal=legacy["stepSumMatchesTotal"],
                  temporaryIncrease=legacy.get("temporaryIncrease"))
        m = re.search(r"インストール日から起算して(\d+)日以内", t)
        ev["deadlineDays"], ev["deadlineBasis"] = (int(m.group(1)), "install") if m else (None, None)
        ev["state"] = "readable" if ev["stepSumMatchesTotal"] else "parse_failed"
        return _finish(ev)
    # single condition: "iOS / 初回アプリインストール後、レベル300クリア / 320 / pt"
    m = re.search(r"\n(iOS|Android)\s*\n\s*(初回アプリインストール後[^\n]*)\n\s*([\d,]+)\s*\n\s*pt\b", t)
    d = re.search(r"インストール日から起算して(\d+)日以内に", t)
    if m and d and "最大" not in m.group(0):
        pt = _num(m.group(3))
        cond = re.sub(r"^初回アプリインストール後、?", "", m.group(2)).strip()
        ev.update(os=m.group(1), osSource="page", kind="single", conditionText=cond,
                  steps=[{"condition": cond, "rewardPt": pt, "rewardYen": pt}], totalPt=pt, totalYen=pt,
                  stepSumMatchesTotal=True, deadlineDays=int(d.group(1)), deadlineBasis="install", state="readable")
        return _finish(ev)
    return _finish(_unavailable(ev, "parse_failed", "offer_structure_not_found"))


PARSERS = {"warau": parse_warau, "amefuri": parse_amefuri, "coincome": parse_coincome, "moppy": parse_moppy}


def parse_offer_page(site: str, offer_id: str, raw: str, url: str | None = None, http_status: int = 200) -> dict:
    """Normalized evidence for one already-downloaded page. HTTP status alone never decides the state."""
    if site not in PARSERS:
        raise ValueError(f"unregistered point site: {site}")
    ev = PARSERS[site](raw, offer_id, url)
    ev["httpStatus"] = http_status
    return ev


# ---------------------------------------------------------------- network (the only part that touches the web)
def _default_fetch(url: str) -> "tuple[int, bytes]":
    return warau_evidence.fetch(url)


def record(url: str, fetcher: Fetcher | None = None) -> dict:
    """One GET of one registered offer page -> evidence. Unregistered hosts are refused before any request."""
    found = site_and_offer_id(url)
    if not found:
        raise ValueError(f"not a registered first-party offer URL: {url}")
    site, offer_id = found
    code, body = (fetcher or _default_fetch)(url)
    raw = body.decode("utf-8", "replace")
    if code in (0, 403, 408, 429) or code >= 500:
        ev = _unavailable(_base(site, offer_id, url), "http_error", f"http_{code}")
        _finish(ev)
    elif code in (404, 410) and site != "coincome" and len(raw) < 4000:
        ev = _unavailable(_base(site, offer_id, url), "not_found", f"http_{code}")
        _finish(ev)
    else:
        ev = parse_offer_page(site, offer_id, raw, url, code)
    ev["httpStatus"] = code
    ev["retrievedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ev["responseSha256"] = _sha(body)
    return ev


# ---------------------------------------------------------------- Amefuri name search (cross-site lookup)
def amefuri_search_url(name: str) -> str:
    return "https://www.amefri.net/item_list?word=" + quote(name, safe="")


def parse_amefuri_search(raw: str) -> list[dict]:
    """Cards of an Amefuri search result page: offerId / url / title / os / stepup label."""
    out, seen = [], set()
    for card in re.split(r'<div class="projectList__box', raw)[1:]:
        m = re.search(r'href="(https://www\.amefri\.net/detail/id/(\d+))"', card)
        if not m or m.group(2) in seen:
            continue
        seen.add(m.group(2))
        name = re.search(r'projectList__name">(.*?)</p>', card, re.S)
        title = _unesc(re.sub(r"<[^>]+>", "", name.group(1))) if name else ""
        devices = set(re.findall(r"deviceLabel__item--(ios|android)", card))
        out.append({"offerId": m.group(2), "url": m.group(1), "title": title, "gameName": clean_game_name(title),
                    "os": ("iOS" if devices == {"ios"} else "Android" if devices == {"android"} else None),
                    "kind": "stepup" if "labelArea__item--stepup" in card else "single"})
    return out


def lookup_amefuri(name: str, fetcher: Fetcher | None = None, delay: float = 0.0) -> list[dict]:
    """One GET of Amefuri's own search ("案件名で検索"). Returns [] when nothing matched or the page failed."""
    if delay:
        time.sleep(delay)
    code, body = (fetcher or _default_fetch)(amefuri_search_url(name))
    if code != 200:
        return []
    return parse_amefuri_search(body.decode("utf-8", "replace"))
