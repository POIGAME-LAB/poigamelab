#!/usr/bin/env python3
"""Build, register and gate the daily new-guide batch (research/daily-guides/<date>/<slug>/).

Each completed article folder holds the editorial package written by the daily routine:

    article.md        manuscript (H1 = SEO title, 2 intro paragraphs, 目次, <a id> sections, FAQ, 出典 list)
    metadata.json     SEO + offer table (every Step, payment flag, deadline, totals)  status=manuscript_complete
    sources.json      every cited source with id / url / type / checkedAt
    experiences.json  experience-panel data (players with sources, unknown days stay null)
    page.json         page furniture only: heroStats, offerLinks, related, registry

and ``evidence/<slug>-offers.json`` written by ``scripts/daily_guide_evidence.py`` the same day. A later
pre-publication re-check (``evidence/<slug>-offers-recheck-YYYYMMDD.json``, ``--recheck``) supersedes it: the
offer table must then equal the *latest* first-party evidence, and offers recorded in ``metadata.previousOffers``
must be shown as no longer available there (an old point_id is never presented as the current offer).

This script only *converts* (body text is carried over verbatim, as in research/new-guides/2026-10-31/tools/
md_to_spec.py), renders with the existing ``scripts/render_cited_guide.py`` and registers guide-only with
the existing ``scripts/register_guide_pages.py`` + ``scripts/sync_static_guide_links.js``. It never writes
games.csv / data/published_offers.csv / offer data. ``--check`` runs the daily quality gate without writing.

    python scripts/build_daily_guides.py research/daily-guides/2026-11-05            # build + register
    python scripts/build_daily_guides.py --check research/daily-guides/2026-11-05    # gate only
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date as Date
from pathlib import Path
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import register_guide_pages, render_cited_guide  # noqa: E402

ROOT = render_cited_guide.ROOT
REQUIRED_FILES = ("article.md", "metadata.json", "sources.json", "experiences.json", "page.json")
REQUIRED_TOC = ("condition", "pace", "early", "middle", "late", "stop", "tracking", "faq", "sources")
RECORDS_ID, RECORDS_H2 = "records", "到達記録の比較表"
MIN_ARTICLE_CHARS = 3000
MIN_INDEPENDENT_PLAYERS = 2
MAX_PLAYER_RECORD_AGE_DAYS = 365
# The site has not played these games itself; promising wording is never allowed (AGENTS.md §5).
FORBIDDEN_CLAIMS = (
    "編集部がプレイ", "編集部のプレイ", "当サイトがプレイ", "当サイトのプレイ", "筆者がプレイ", "私がプレイ", "実際に遊んでみた",
    "必ずもらえる", "必ず稼げる", "確実に稼げ", "確実にもらえる", "誰でも達成", "誰でも簡単", "絶対に達成",
)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def completed_slugs(batch: Path) -> list[str]:
    out = []
    for meta in sorted(batch.glob("*/metadata.json")):
        if _json(meta).get("status") == "manuscript_complete":
            out.append(meta.parent.name)
    return out


# ---------------------------------------------------------------- manuscript -> spec
def _table(lines: list[str]) -> dict:
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    return {"t": "table", "head": rows[0], "rows": rows[2:]}


def parse_article(text: str) -> dict:
    lines = text.splitlines()
    if not lines or not lines[0].startswith("# "):
        raise ValueError("article must start with '# <SEO title>'")
    title = lines[0][2:].strip()
    i, intro = 1, []
    while i < len(lines) and not lines[i].startswith("## 目次"):
        if lines[i].strip():
            intro.append(lines[i].strip())
        i += 1
    i += 1
    toc = []
    while i < len(lines) and not lines[i].startswith("<a id="):
        m = re.match(r"\d+\. \[(.+?)\]\(#([a-z-]+)\)", lines[i].strip())
        if m:
            toc.append({"id": m.group(2), "label": m.group(1)})
        i += 1
    sections, sources, source_note, cur = [], [], "", None
    while i < len(lines):
        ln = lines[i]
        m = re.match(r'<a id="([a-z-]+)"></a>', ln)
        if m:
            cur = {"id": m.group(1), "h2": None, "blocks": []}
            sections.append(cur)
        elif cur is None:
            pass
        elif ln.startswith("## "):
            cur["h2"] = ln[3:].strip()
        elif ln.startswith("### "):
            cur["blocks"].append({"t": "h3", "x": ln[4:].strip()})
        elif ln.startswith("|"):
            tbl = []
            while i < len(lines) and lines[i].startswith("|"):
                tbl.append(lines[i])
                i += 1
            cur["blocks"].append(_table(tbl))
            continue
        elif ln.startswith("- ") and cur["id"] == "sources":
            m2 = re.match(r"- \[(([A-Z]\d+)：.+?)\]\((https://[^)]+)\)$", ln.strip())
            if not m2:
                raise ValueError(f"bad source line: {ln}")
            sources.append({"id": m2.group(2), "label": m2.group(1), "url": m2.group(3)})
        elif ln.startswith("- "):
            # consecutive bullet lines become one list block
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(lines[i][2:].strip())
                i += 1
            cur["blocks"].append({"t": "ul", "items": items})
            continue
        elif ln.strip():
            s = ln.strip()
            if cur["id"] == "sources":
                source_note = s
            elif re.fullmatch(r"\*\*[^*]+\*\*", s):
                cur["blocks"].append({"t": "key", "x": s})
            else:
                cur["blocks"].append({"t": "p", "x": s})
        i += 1
    return {"title": title, "intro": intro, "toc": toc, "sections": sections, "sources": sources, "sourceNote": source_note}


def evidence_path(batch: Path, slug: str) -> Path:
    """Latest offer evidence: the newest pre-publication re-check if any, else the production-day file."""
    rechecks = sorted((batch / "evidence").glob(f"{slug}-offers-recheck-*.json"))
    return rechecks[-1] if rechecks else batch / "evidence" / f"{slug}-offers.json"


def _evidence(batch: Path, slug: str) -> dict:
    return _json(evidence_path(batch, slug))


def _jp_date(iso: str) -> str:
    y, m, d = iso[:10].split("-")
    return f"{int(y)}年{int(m)}月{int(d)}日"


def build_spec(batch: Path, slug: str) -> dict:
    d = batch / slug
    art = parse_article((d / "article.md").read_text(encoding="utf-8"))
    meta, exp, page = _json(d / "metadata.json"), _json(d / "experiences.json"), _json(d / "page.json")
    ev = _evidence(batch, slug)
    sections = [s for s in art["sections"] if s["id"] != "sources"]
    for s in sections:
        if s["id"] == "pace":  # the shared experience panel owns id="pace"
            s["id"], s["h2"] = RECORDS_ID, RECORDS_H2
    toc = []
    for t in art["toc"]:
        toc.append(t)
        if t["id"] == "pace":
            toc.append({"id": RECORDS_ID, "label": RECORDS_H2})
    note = (
        f"{_jp_date(ev['checkedAtJst'])}（日本時間）に上表の案件ページを直接取得し、全Stepの条件・個別報酬・合計が上表と同じであることを確認しました。"
        "参加時の画面に表示される条件が優先されます。"
    )
    cond = next(s for s in sections if s["id"] == "condition")
    first_table = next(k for k, b in enumerate(cond["blocks"]) if b["t"] == "table")
    cond["blocks"].insert(first_table + 1, {"t": "key", "x": note})
    experience = {k: v for k, v in exp.items() if k not in ("schemaVersion", "game")}
    return {
        "slug": slug,
        "game": meta["game"],
        "file": meta["proposedPage"],
        "title": meta["seoTitle"],
        "description": meta["metaDescription"],
        "lead": art["intro"][0],
        "heroStats": page["heroStats"],
        "heroNote": art["intro"][1],
        "toc": toc,
        "sections": sections,
        "sources": art["sources"],
        "sourceNote": art["sourceNote"],
        "context": {"href": page["offerLinks"][0]["url"], "label": page.get("contextLabel", "現在の案件ページを見る →")},
        "offerLinks": page["offerLinks"],
        "related": page.get("related", []),
        "registry": {"title": f"{meta['game']} ポイ活攻略", **page["registry"]},
        "experience": experience,
    }


# ---------------------------------------------------------------- daily quality gate
def _plain(text: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"\[[^\]]*\]|\*\*|<[^>]+>|\|", "", text))


def gate(batch: Path, slug: str) -> list[str]:
    errs: list[str] = []
    d = batch / slug
    for name in REQUIRED_FILES:
        if not (d / name).is_file():
            errs.append(f"missing_file:{name}")
    ev_path = evidence_path(batch, slug)
    if not (batch / "evidence" / f"{slug}-offers.json").is_file() or not ev_path.is_file():
        errs.append("missing_offer_evidence")
    if errs:
        return errs
    batch_date = batch.name
    article = (d / "article.md").read_text(encoding="utf-8")
    meta, src, exp, page = (_json(d / n) for n in ("metadata.json", "sources.json", "experiences.json", "page.json"))
    ev = _json(ev_path)
    ev_date = ev.get("checkedAtJst", "")[:10]
    is_recheck = ev_path.name != f"{slug}-offers.json"
    try:
        art = parse_article(article)
    except ValueError as exc:
        return [f"article_unparsable:{exc}"]

    # SEO / identity
    if meta.get("slug") != slug:
        errs.append("metadata_slug_mismatch")
    if art["title"] != meta.get("seoTitle"):
        errs.append("h1_must_equal_seoTitle")
    if not 20 <= len(meta.get("seoTitle", "")) <= 60:
        errs.append("seoTitle_length_20_60")
    if not 50 <= len(meta.get("metaDescription", "")) <= 160:
        errs.append("metaDescription_length_50_160")
    if meta.get("proposedPage") != f"{slug}-guide.html":
        errs.append("proposedPage_must_be_slug-guide.html")
    if meta.get("canonical") != f"https://poigamelab.com/{slug}-guide.html":
        errs.append("canonical_mismatch")
    if len(art["intro"]) != 2:
        errs.append("intro_must_have_2_paragraphs")
    toc_ids = [t["id"] for t in art["toc"]]
    for must in REQUIRED_TOC:
        if must not in toc_ids:
            errs.append(f"toc_must_include:{must}")
    sec_ids = [s["id"] for s in art["sections"]]
    if toc_ids != sec_ids:
        errs.append("toc_and_sections_differ")
    body = "\n".join(ln for ln in article.splitlines() if not ln.startswith(("|", "- [", "<a id")))
    if len(_plain(body)) < MIN_ARTICLE_CHARS:
        errs.append(f"article_too_short:{len(_plain(body))}<{MIN_ARTICLE_CHARS}")
    for word in FORBIDDEN_CLAIMS:
        if word in article:
            errs.append(f"forbidden_claim:{word}")

    # sources
    src_by_id = {s["id"]: s for s in src.get("sources", [])}
    art_src = {s["id"]: s["url"] for s in art["sources"]}
    if set(src_by_id) != set(art_src):
        errs.append("sources_json_ids_differ_from_article")
    for sid, url in art_src.items():
        s = src_by_id.get(sid)
        if s and s.get("url") != url:
            errs.append(f"source_url_differs:{sid}")
        if s and s.get("checkedAt") not in {batch_date, ev_date}:
            errs.append(f"source_not_checked_today:{sid}")
        if s and s.get("type") == "point_site" and s.get("checkedAt") != ev_date:
            errs.append(f"offer_source_not_checked_with_latest_evidence:{sid}")
        if urlsplit(url).scheme != "https":
            errs.append(f"source_not_https:{sid}")

    # offer table vs same-day first-party evidence
    checks = {c["pointId"]: c for c in ev.get("checks", [])}
    if (not is_recheck and ev_date != batch_date) or (is_recheck and ev_date < batch_date):
        errs.append("offer_evidence_not_from_batch_date")
    current_ids = {str(o.get("pointId")) for o in meta.get("offers") or []}
    for prev in meta.get("previousOffers") or []:
        pid = str(prev.get("pointId"))
        c = {x["pointId"]: x for x in ev.get("checks", [])}.get(pid)
        if pid in current_ids:
            errs.append(f"previous_offer_listed_as_current:{pid}")
        if not c or c.get("live"):
            errs.append(f"previous_offer_not_shown_unavailable_in_latest_evidence:{pid}")
        if prev.get("url") in {l.get("url") for l in page.get("offerLinks", [])}:
            errs.append(f"previous_offer_linked_as_current:{pid}")
    offers = meta.get("offers") or []
    if not offers:
        errs.append("metadata_offers_required")
    offer_urls = {o.get("url") for o in offers}
    for link in page.get("offerLinks", []):
        if link.get("url") not in offer_urls:
            errs.append(f"offer_link_not_in_metadata:{link.get('url')}")
    for o in offers:
        pid = str(o.get("pointId"))
        c = checks.get(pid)
        if not c or not c.get("live"):
            errs.append(f"offer_not_live_in_evidence:{pid}")
            continue
        if o.get("os") != c.get("os"):
            errs.append(f"offer_os_mismatch:{pid}")
        if o.get("url") not in art_src.values():
            errs.append(f"offer_url_not_cited:{pid}")
        steps = o.get("steps") or []
        if [(s["condition"], s["rewardPt"]) for s in steps] != [(s["condition"], s["rewardPt"]) for s in c.get("steps", [])]:
            errs.append(f"offer_steps_differ_from_evidence:{pid}")
        total = sum(s["rewardPt"] for s in steps)
        if total != o.get("totalDisplayedPt") or total != c.get("totalPt"):
            errs.append(f"offer_total_mismatch:{pid}")
        if sum(s["rewardPt"] for s in steps if not s.get("requiresPayment")) != o.get("sumWithoutPurchaseStepsPt"):
            errs.append(f"offer_free_sum_mismatch:{pid}")
        for s in steps:
            if not isinstance(s.get("deadlineDays"), int) or s["deadlineDays"] <= 0:
                errs.append(f"step_deadline_missing:{pid}:{s.get('condition')}")
            if not isinstance(s.get("requiresPayment"), bool):
                errs.append(f"step_payment_flag_missing:{pid}:{s.get('condition')}")
            if re.search(r"購入|課金|パック|パス", s["condition"]) and not s.get("requiresPayment"):
                errs.append(f"purchase_step_not_flagged:{pid}:{s['condition']}")
            if f"{s['rewardPt']:,}pt" not in article:
                errs.append(f"step_reward_not_in_article:{pid}:{s['rewardPt']}")
        if f"{total:,}pt" not in article:
            errs.append(f"offer_total_not_in_article:{pid}")
        inc = c.get("temporaryIncrease")
        if inc and inc["until"] not in article:
            errs.append(f"temporary_increase_not_disclosed:{pid}")

    # player records
    players = exp.get("players", [])
    if len(players) < 3:
        errs.append("experience_needs_3_players")
    authors, today = set(), Date.fromisoformat(batch_date)
    for p in players:
        for m in p.get("milestones", []):
            if m.get("day") == 0:
                errs.append(f"player_day_zero:{p.get('id')}")
        for u in p.get("sources", []):
            if u not in {s["url"] for s in src_by_id.values()}:
                errs.append(f"player_source_not_in_sources:{p.get('id')}")
        posted = str(p.get("postedOn") or "")
        if not re.match(r"\d{4}-\d{2}(-\d{2})?", posted):
            errs.append(f"player_postedOn_missing:{p.get('id')}")
            continue
        if str(p.get("dateEligibility", "")).startswith("reference_only"):
            continue
        y, mth, *rest = (int(x) for x in re.match(r"(\d{4})-(\d{2})(?:-(\d{2}))?", posted).groups() if x)
        age = (today - Date(y, mth, rest[0] if rest else 1)).days
        if age > MAX_PLAYER_RECORD_AGE_DAYS:
            errs.append(f"player_record_older_than_365_days:{p.get('id')}")
            continue
        detail = p.get("sourceDetails") or []
        authors.add((detail[0] if detail else p.get("id"), tuple(p.get("sources", []))))
    if len({a for a, _ in authors}) < MIN_INDEPENDENT_PLAYERS:
        errs.append("needs_2_independent_current_players")

    # page furniture
    for key in ("heroStats", "offerLinks", "registry"):
        if not page.get(key):
            errs.append(f"page_missing:{key}")
    if page.get("registry") and not {"label", "description"} <= set(page["registry"]):
        errs.append("registry_needs_label_and_description")
    for r in page.get("related", []):
        if not (ROOT / r.get("href", "")).is_file():
            errs.append(f"related_missing:{r.get('href')}")
    return errs


def check_batch(batch: Path) -> dict[str, list[str]]:
    result = {}
    for slug in completed_slugs(batch):
        errs = gate(batch, slug)
        if not errs:
            spec = build_spec(batch, slug)
            errs = render_cited_guide.validate(spec)
            spec_path = batch / slug / "spec.json"
            if spec_path.exists() and _json(spec_path) != spec:
                errs.append("spec_json_stale_rebuild_required")
        result[slug] = errs
    return result


def build_batch(batch: Path) -> list[str]:
    results = check_batch(batch)
    bad = {k: v for k, v in results.items() if v and v != ["spec_json_stale_rebuild_required"]}
    if bad:
        raise SystemExit("daily gate failed: " + json.dumps(bad, ensure_ascii=False))
    changed = []
    for slug in results:
        spec = build_spec(batch, slug)
        (batch / slug / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed += [str(p.relative_to(ROOT)) for p in render_cited_guide.write_outputs(spec)]
        reg = {"file": spec["file"], "game": spec["game"],
               "registry": {"title": spec["registry"]["title"], "description": spec["registry"]["description"], "label": spec["registry"]["label"]}}
        changed += register_guide_pages.register(reg)
    if results:
        subprocess.run(["node", str(ROOT / "scripts" / "sync_static_guide_links.js")], check=True, cwd=ROOT)
        changed.append("guides.html")
    return sorted(set(changed))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("batch", help="research/daily-guides/<YYYY-MM-DD>")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    batch = (ROOT / args.batch).resolve() if not Path(args.batch).is_absolute() else Path(args.batch)
    if args.check:
        results = check_batch(batch)
        for slug, errs in results.items():
            print(f"{slug}: {'ok' if not errs else 'FAIL ' + ', '.join(errs)}")
        if not results:
            print("no completed articles in batch")
        return 1 if any(results.values()) else 0
    for path in build_batch(batch):
        print("wrote/updated", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
