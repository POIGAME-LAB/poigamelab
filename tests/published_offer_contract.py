"""Contract checks for ``data/published_offers.csv`` that do not depend on one day's offer IDs.

Point-site campaigns end and are replaced under new IDs; the daily refresh retires an
offer only after three consecutive "ended" reads (``offer_unavailable_runs.json``). A test
that pins a specific campaign ID, or an exact set of IDs and amounts, therefore starts
failing on the *correct* behaviour (2026-10-15/18/20 retirements). These helpers verify what
must always hold instead:

* every published row is internally consistent (identity, platform, integer reward,
  verified, condition, date) and unique;
* a *pinned* offer that is still published keeps the identity it was verified against;
* a pinned offer that has ended leaves no row behind (not under another key either);
* an offer the refresh has confirmed ended is not published, and a retired offer that
  comes back under the same ID does so only with fresh evidence that it was re-listed.

Every function returns a list of problem codes so the checks can themselves be tested with
normal, ended, re-issued-ID and malformed data.
"""
import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published_offers.csv"

PLATFORMS = {"iOS", "Android", "不明"}
ID_PATTERNS = {
    "warau": re.compile(r"point_id=(\d+)"),
    "hapitas": re.compile(r"/itemid/(\d+)"),
    "moppy": re.compile(r"site_id=(\d+)"),
}
REQUIRED = ("offerKey", "game", "site", "platform", "reward", "condition", "deadline",
            "updatedAt", "url", "verified")


def load_rows(path=PUBLISHED):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def offer_id(row):
    """Stable campaign ID of a row for the sites that expose one in the URL, else ''."""
    pattern = ID_PATTERNS.get(row.get("site"))
    match = pattern.search(row.get("url") or "") if pattern else None
    return match.group(1) if match else ""


def _key_id(row):
    pattern = ID_PATTERNS.get(row.get("site"))
    match = pattern.search(row.get("offerKey") or "") if pattern else None
    return match.group(1) if match else ""


def row_problems(row):
    """Problems of one published row (empty list = consistent)."""
    problems = []
    for field in REQUIRED:
        if field not in row or not str(row[field] or "").strip():
            problems.append(f"missing:{field}")
    if problems:
        return problems
    if not re.fullmatch(r"[1-9]\d*", row["reward"].strip()):
        problems.append("reward_not_positive_integer")
    if row["platform"] not in PLATFORMS:
        problems.append("platform_invalid")
    if row["verified"].strip().lower() != "true":
        problems.append("not_verified")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["updatedAt"].strip()):
        problems.append("updatedAt_not_a_date")
    if not row["url"].startswith("https://"):
        problems.append("url_not_https")
    if not row["offerKey"].startswith(f"{row['game']}|{row['site']}|{row['platform']}|"):
        problems.append("offerKey_identity_mismatch")
    if row["site"] in ID_PATTERNS:
        if not offer_id(row):
            problems.append("url_without_offer_id")
        elif _key_id(row) != offer_id(row):
            problems.append("offerKey_url_id_mismatch")
    return problems


def rows_problems(rows):
    """Row-level problems plus uniqueness of offerKey and (site, campaign ID)."""
    problems = []
    seen_keys, seen_ids = set(), set()
    for row in rows:
        for problem in row_problems(row):
            problems.append(f"{problem}:{row.get('offerKey')}")
        key = row.get("offerKey")
        if key in seen_keys:
            problems.append(f"duplicate_offerKey:{key}")
        seen_keys.add(key)
        oid = offer_id(row)
        if oid:
            ident = (row.get("site"), oid)
            if ident in seen_ids:
                problems.append(f"duplicate_offer_id:{ident[0]}:{oid}")
            seen_ids.add(ident)
    return problems


def pin_problems(rows, pins):
    """Check pinned offers: still listed -> identity unchanged; ended -> nothing left.

    ``pins`` is an iterable of dicts with ``site``, ``id``, ``game`` and ``platform``.
    The reward is deliberately not pinned: it legitimately changes between refreshes.
    """
    problems = []
    for pin in pins:
        matches = [r for r in rows if r.get("site") == pin["site"] and offer_id(r) == pin["id"]]
        label = f"{pin['site']}:{pin['id']}"
        if not matches:
            continue  # ended and retired: valid state
        if len(matches) != 1:
            problems.append(f"pinned_offer_listed_more_than_once:{label}")
            continue
        row = matches[0]
        if row["game"] != pin["game"]:
            problems.append(f"pinned_offer_game_changed:{label}")
        if row["platform"] != pin["platform"]:
            problems.append(f"pinned_offer_platform_changed:{label}")
        problems.extend(f"{p}:{label}" for p in row_problems(row))
    return problems


def listed(rows, pins):
    """Rows of the pinned offers that are still published (possibly none)."""
    wanted = {(p["site"], p["id"]) for p in pins}
    return [r for r in rows if (r.get("site"), offer_id(r)) in wanted]


def pin(site, offer, game, platform):
    return {"site": site, "id": str(offer), "game": game, "platform": platform}


# Same threshold as scripts/structured_publication.UNAVAILABLE_RUNS_BEFORE_RETIREMENT
# (asserted equal in tests/test_warau_baseline_candidates.py).
UNAVAILABLE_RUNS_BEFORE_RETIREMENT = 3
UNAVAILABLE_RUNS = ROOT / "data" / "offer_unavailable_runs.json"
HISTORY = ROOT / "data" / "offer_history.csv"
JST = timezone(timedelta(hours=9))


def load_unavailable(path=UNAVAILABLE_RUNS):
    """``{identity: {"runs", "lastUnavailableAt"}}`` kept by the nightly refresh."""
    return json.loads(Path(path).read_text(encoding="utf-8"))["offers"]


def load_history(path=HISTORY):
    return load_rows(path)


def identity(row):
    """The identity key the nightly refresh uses (e.g. ``warau:point_id:205982``)."""
    import sys
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    from direct_offer_refresh import offer_identity_key
    return offer_identity_key(row.get("url"), row.get("site"))


def _instant(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def confirmed_ended_problems(rows, unavailable):
    """No published row may be one the refresh has read as ended on enough nights to retire it.

    1-2 "ended" readings are held on purpose (a single bad night must not drop a row).
    """
    problems = []
    for row in rows:
        runs = int((unavailable.get(identity(row)) or {}).get("runs") or 0)
        if runs >= UNAVAILABLE_RUNS_BEFORE_RETIREMENT:
            problems.append(f"confirmed_ended_offer_published:{row.get('site')}:{offer_id(row)}")
    return problems


def retired_problems(rows, retired, unavailable=None, history=None):
    """A retired offer may come back only on fresh evidence that the source re-listed it.

    Point sites re-open a paused campaign under the *same* ID (Warau 205982/206037
    メメントモリ, 201862/201872 ホワイトアウト, 2026-10). The nightly refresh then reads
    the live page, clears the ended count and publishes the row again, which is
    correct. So a retired ID is not banned forever. ``retired`` holds
    ``(site, id, retiredAt)``; a published row of such an ID is accepted only when

    * the refresh no longer counts the offer as confirmed ended,
    * the row was refreshed (``updatedAt``, JST date) after the retirement day, and
    * ``offer_history.csv`` has a snapshot of the same offerKey after the retirement.

    Without ``unavailable``/``history`` (or without ``retiredAt``) no such evidence
    exists and any reappearance is reported, as before.
    """
    by_id = {}
    for entry in retired:
        site, oid, *rest = entry
        by_id[(site, str(oid))] = rest[0] if rest else None
    problems = []
    for row in rows:
        key = (row.get("site"), offer_id(row))
        if key not in by_id:
            continue
        label = f"{key[0]}:{key[1]}"
        retired_at = by_id[key]
        if retired_at is None or unavailable is None or history is None:
            problems.append(f"retired_offer_republished:{label}")
            continue
        retired_at = _instant(retired_at)
        runs = int((unavailable.get(identity(row)) or {}).get("runs") or 0)
        if runs >= UNAVAILABLE_RUNS_BEFORE_RETIREMENT:
            problems.append(f"retired_offer_republished_while_ended:{label}")
        updated = str(row.get("updatedAt") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", updated) or updated <= retired_at.astimezone(JST).date().isoformat():
            problems.append(f"retired_offer_republished_without_fresh_verification:{label}")
        seen_after = any(h.get("offerKey") == row.get("offerKey") and _instant(h.get("observedAt")) > retired_at
                         for h in history if h.get("observedAt"))
        if not seen_after:
            problems.append(f"retired_offer_republished_without_history:{label}")
    return problems
