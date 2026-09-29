#!/usr/bin/env python3
"""Evidence-first, preview-only editorial pipeline. No publishing and no AI API.

Existing discovery/parser contracts remain unchanged. All writes are isolated
under research/new-games, which the public-site allowlist does not include.
"""

from __future__ import annotations
import argparse, csv, hashlib, html, json, math, re, tempfile, unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit
import daily_scan_review as discovery

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = (
    "overview",
    "difficulty",
    "strategy",
    "efficiency",
    "spending",
    "warnings",
    "failures",
)
LABELS = dict(
    zip(
        SECTIONS,
        (
            "案件概要",
            "難易度と狙う地点",
            "段階別の進め方",
            "効率を上げるポイント",
            "課金と損益",
            "注意点",
            "失敗・未達の記録",
        ),
    )
)
CHANNELS = ("official", "web", "x", "youtube", "instagram", "pointSites")


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def digest(v):
    return hashlib.sha256(
        json.dumps(v, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def atomic(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=p.parent, delete=False
    ) as f:
        f.write(json.dumps(v, ensure_ascii=False, indent=2) + "\n")
        tmp = Path(f.name)
    tmp.replace(p)


def norm(s):
    return re.sub(
        r"[\s・･:：\-－＆&]+", "", unicodedata.normalize("NFKC", str(s))
    ).casefold()


def safe_url(s):
    try:
        p = urlsplit(s)
        return (
            p.scheme == "https"
            and bool(p.hostname)
            and not p.username
            and not p.password
            and p.port in (None, 443)
        )
    except (ValueError, TypeError):
        return False


def url_key(s):
    if not safe_url(s):
        raise ValueError("unsafe_url")
    p = urlsplit(s)
    q = [
        (k, v)
        for k, v in parse_qsl(p.query)
        if k
        not in (
            "pl",
            "track_ref",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "hl",
            "lang",
        )
    ]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(sorted(q)), ""))


def age_days(value, now):
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(
                tzinfo=(
                    timezone(timedelta(hours=9)) if len(value) == 10 else timezone.utc
                )
            )
        return (now - t).total_seconds() / 86400
    except (TypeError, ValueError, AttributeError):
        return None


def fresh(value, now, days):
    age = age_days(value, now)
    return age is not None and 0 <= age <= days


def catalog(root):
    with (root / "games.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def select(root, registry):
    """Conservative exact reviewed aliases; uncertain identities never auto-merge."""
    existing = {norm(x["name"]) for x in catalog(root)}
    aliases = {norm(a): g["slug"] for g in registry for a in [g["name"], *g["aliases"]]}
    games = {g["slug"]: g for g in registry}
    merged = {}
    excluded = []
    unresolved = []
    inputs = [
        (name, read(root / name))
        for name in ("data/new_game_candidate_queue.json", "data/new_game_monitor.json")
    ]
    inputs.append(
        (
            "registry:historical_discovery",
            {"items": [r for g in registry for r in g.get("discoveryEvidence", [])]},
        )
    )
    for filename, doc in inputs:
        for row in doc.get("items", []):
            title = row.get("titleHint", "")
            name = discovery.discovery_name(title)
            key = norm(name)
            if key in existing:
                excluded.append({"title": title, "reason": "already_published"})
                continue
            slug = aliases.get(key)
            if not slug:
                unresolved.append(
                    {
                        "nameHint": name,
                        "source": row.get("source"),
                        "url": row.get("firstPartyCandidateUrl"),
                        "status": "identity_review_required",
                    }
                )
                continue
            if any(
                norm(a) in existing
                for a in [games[slug]["name"], *games[slug]["aliases"]]
            ):
                continue
            url = row.get("firstPartyCandidateUrl", "")
            if not safe_url(url):
                continue
            ident = (slug, row.get("source"), url_key(url))
            stamp = row.get("checkedAt") or doc.get("checkedAt")
            value = {**row, "checkedAt": stamp, "inputFile": filename}
            if ident not in merged or str(stamp) > str(merged[ident].get("checkedAt")):
                merged[ident] = value
    out = []
    for slug, g in games.items():
        rows = [r for k, r in merged.items() if k[0] == slug]
        if not rows:
            continue
        out.append(
            {
                **g,
                "offers": rows,
                "listingSourceCount": len({r["source"] for r in rows}),
                "status": "research_required",
            }
        )
    return {
        "schemaVersion": 1,
        "candidates": out,
        "excluded": excluded,
        "unresolved": unresolved,
        "publicationAuthorized": False,
    }


def verify_offer(o, now):
    reasons = []
    for key in (
        "gameId",
        "site",
        "platform",
        "condition",
        "deadline",
        "url",
        "retrievedAt",
        "evidenceSha256",
    ):
        if not o.get(key):
            reasons.append("missing_" + key)
    if o.get("platform") not in ("iOS", "Android"):
        reasons.append("invalid_os")
    if not safe_url(o.get("url", "")):
        reasons.append("unsafe_offer_url")
    if not fresh(o.get("retrievedAt"), now, 2):
        reasons.append("stale_offer")
    if o.get("identityReviewed") is not True or o.get("termsReviewed") is not True:
        reasons.append("offer_review_missing")
    if o.get("parserState") != "parsed":
        reasons.append("unparsed_offer")
    amount = o.get("rewardYen")
    if type(amount) not in (int, float) or not math.isfinite(amount) or amount <= 0:
        reasons.append("invalid_reward")
    if o.get("conversion", {}).get("verified") is not True:
        reasons.append("unverified_conversion")
    steps = o.get("steps", [])
    if not steps or any(
        not s.get("condition")
        or type(s.get("rewardYen")) not in (int, float)
        or s["rewardYen"] < 0
        or not math.isfinite(s["rewardYen"])
        for s in steps
    ):
        reasons.append("invalid_steps")
    elif (
        type(amount) in (int, float)
        and abs(sum(s["rewardYen"] for s in steps) - amount) > 0.005
    ):
        reasons.append("step_total_mismatch")
    if len({s.get("condition") for s in steps}) != len(steps):
        reasons.append("duplicate_steps")
    return sorted(set(reasons))


def evaluate(p, now):
    issues = []
    sources = {}
    seen_urls = set()
    if p.get("schemaVersion") != 2:
        issues.append("schema_invalid")
    if not re.fullmatch("[a-z0-9]+(?:-[a-z0-9]+)*", p.get("slug", "")):
        issues.append("slug_invalid")
    for s in p.get("sources", []):
        sid = s.get("id")
        url = s.get("url", "")
        if not sid or sid in sources or not safe_url(url):
            issues.append("source_identity_invalid")
            continue
        sources[sid] = s
        if s.get("access") != "body_verified":
            issues.append("source_body_unverified:" + sid)
        if not s.get("locator") or not s.get("summary"):
            issues.append("source_trace_missing:" + sid)
        if s.get("gameId") != p.get("gameId"):
            issues.append("source_game_mismatch:" + sid)
        if not fresh(s.get("checkedAt"), now, 30):
            issues.append("source_check_stale:" + sid)
        if s.get("kind") in ("player", "strategy") and not fresh(
            s.get("publishedAt"), now, 365
        ):
            if s.get("historicalOnly") is not True:
                issues.append("source_date_old_or_unknown:" + sid)
    for ch in CHANNELS:
        lane = p.get("research", {}).get(ch, {})
        if (
            lane.get("status")
            not in ("searched", "body_verified", "no_usable_result", "access_limited")
            or not lane.get("queries")
            or not lane.get("checkedAt")
        ):
            issues.append("research_lane_missing:" + ch)
    if not any(
        s.get("kind") == "official" and s.get("access") == "body_verified"
        for s in sources.values()
    ):
        issues.append("official_missing")
    valid = []
    offer_ids = set()
    for o in p.get("offers", []):
        errs = verify_offer(o, now)
        if o.get("gameId") != p.get("gameId"):
            errs.append("offer_game_mismatch")
        key = (o.get("site"), o.get("platform"), o.get("url"))
        if key in offer_ids:
            errs.append("duplicate_offer")
        offer_ids.add(key)
        if errs:
            issues.extend("offer:" + o.get("site", "?") + ":" + e for e in errs)
        else:
            valid.append(o)
    if not valid:
        issues.append("current_offer_missing")
    # Independent players, not URLs: a blog and its author's X are a single person.
    players = set()
    progress = []
    for r in p.get("progress", []):
        sid = r.get("sourceRef")
        s = sources.get(sid, {})
        supported = any(
            digest(r.get("observation")) == digest(f) for f in s.get("observations", [])
        )
        o = r.get("observation", {})
        if (
            not supported
            or not o.get("target")
            or type(o.get("days")) not in (int, float)
            or o.get("days", 0) <= 0
        ):
            issues.append("progress_unbound:" + str(sid))
            continue
        if not s.get("playerKey") or s.get("kind") != "player":
            issues.append("player_identity_missing:" + str(sid))
            continue
        if s.get("historicalOnly"):
            continue
        if s.get("access") != "body_verified":
            continue
        if not all(k in o for k in ("spendYen", "playHours", "outcome")):
            issues.append("progress_context_missing:" + str(sid))
            continue
        players.add(s["playerKey"])
        progress.append(r)
    if len(players) < 2:
        issues.append("independent_progress_below_two")
    if not fresh(p.get("researchDate"), now, 30):
        issues.append("research_date_stale_or_future")
    guide = p.get("guide", {})
    chars = 0
    for section in SECTIONS:
        blocks = guide.get(section, [])
        if not blocks:
            issues.append("section_missing:" + section)
        for b in blocks:
            t = b.get("text", "")
            refs = b.get("sourceRefs", [])
            chars += len(t)
            if not t or not refs or any(ref not in sources for ref in refs):
                issues.append("section_evidence_missing:" + section)
            if b.get("kind") not in ("fact", "editorial"):
                issues.append("block_kind_missing:" + section)
            # Numbers are never sufficient evidence. Binding records plus final semantic
            # review are mandatory. This only catches obvious unsupported numeric tokens.
            if b.get("kind") == "fact":
                evidence = " ".join(
                    json.dumps(
                        sources.get(ref, {}).get("observations", []), ensure_ascii=False
                    )
                    + sources.get(ref, {}).get("summary", "")
                    for ref in refs
                )
                if set(re.findall(r"\d+(?:\.\d+)?", t.replace(",", ""))) - set(
                    re.findall(r"\d+(?:\.\d+)?", evidence.replace(",", ""))
                ):
                    issues.append("unbound_numeric_claim:" + section)
            for ref in refs:
                if sources.get(ref, {}).get("historicalOnly") and not b.get(
                    "historicalLabel"
                ):
                    issues.append("historical_claim_unlabelled:" + section)
    if chars < 1800:
        issues.append("editorial_depth_below_baseline")
    # These attestations bind to the entire evidence + text digest, so a changed
    # reward, source, or paragraph invalidates prior semantic/copy/quality review.
    review = p.get("editorialReview", {})
    content = {k: v for k, v in p.items() if k != "editorialReview"}
    required = (
        "amount_identity_os_terms",
        "pace_semantics",
        "specific_strategy",
        "originality",
        "baseline_quality",
    )
    if (
        review.get("contentDigest") != digest(content)
        or not review.get("reviewer")
        or not all(review.get(k) is True for k in required)
    ):
        issues.append("editorial_signoff_required")
    if (
        p.get("image", {}).get("mode") != "original_typographic_card"
        or p.get("image", {}).get("rightsConfirmed") is not True
    ):
        issues.append("image_rights_unconfirmed")
    if p.get("unresolved"):
        issues.extend("unresolved:" + x for x in p["unresolved"])
    return {
        "status": "review_required" if issues else "publication_candidate",
        "issues": sorted(set(issues)),
        "currentMaxObservedYen": max((o["rewardYen"] for o in valid), default=None),
        "verifiedOfferCount": len(valid),
        "verifiedOfferDigests": [digest(o) for o in valid],
        "verifiedProgressDigests": [digest(r) for r in progress],
        "independentPlayerCount": len(players),
        "editorialCharacters": chars,
        "publicationAuthorized": False,
        "contentDigest": digest(content),
    }


def render(p, result, root):
    esc = html.escape
    offers = [o for o in p["offers"] if digest(o) in result["verifiedOfferDigests"]]
    css = re.search(
        r"<style>(.*?)</style>", (root / "kinoko-guide.html").read_text(), re.S
    ).group(1)
    css += "\n.source-note{font-size:12px}.section{overflow-wrap:anywhere}.preview-status{padding:12px;background:#fff7d8}.pace-grid{display:grid;gap:12px}.pace-card{padding:18px;background:#f8f6ff;border-left:4px solid #7047ff;border-radius:12px}.sources{font-size:13px}.sources a{font-size:13px}"
    sources = {s["id"]: s for s in p["sources"]}

    def refs(ids):
        return " ".join(
            f'<a href="{esc(sources[i]["url"],quote=True)}" rel="noopener noreferrer">[{esc(i)}]</a>'
            for i in ids
            if i in sources
        )

    parts = [
        f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{esc(p["name"])} ポイ活攻略｜POIGAME LAB 確認用</title><style>{css}</style></head><body><header class="topbar"><a class="brand" href="index.html">POIGAME <b>LAB</b></a><span>掲載前プレビュー</span></header><main class="page">',
        f'<section class="hero"><div class="eyebrow">POIGAME LAB 攻略データ</div><h1>{esc(p["name"])} ポイ活攻略</h1><p class="lead">{esc(p["lead"])}</p><p class="hero-note">公開されたプレイヤー記録を整理した記事です。運営者本人のプレイ記録ではありません。日数は各投稿者の実績で、達成を保証しません。</p></section>',
        f'<p class="source-note">情報調査日：{esc(p["researchDate"])}。金額は下記の確認日時・確認範囲に限定します。</p>',
    ]
    toc = (
        [
            ("offers", "現在確認できる還元とポイントサイト比較"),
            ("conditions", "達成条件・期限・StepUp"),
            ("pace", "実際の到達ペース"),
        ]
        + [(k, LABELS[k]) for k in SECTIONS]
        + [("sources", "調査ソース")]
    )
    parts.append(
        '<nav class="toc" aria-label="目次"><h2>目次</h2><ol>'
        + "".join(f'<li><a href="#{k}">{v}</a></li>' for k, v in toc)
        + "</ol></nav>"
    )
    maxyen = result["currentMaxObservedYen"]
    parts.append(
        '<section class="section" id="offers"><h2>現在確認できる還元とポイントサイト比較</h2><div class="key">'
        + (
            f"今回、詳細を確認できた範囲の最大額：{maxyen:,.0f}円相当"
            if maxyen is not None
            else "現在報酬を確定できる案件なし"
        )
        + '</div><p>最大額には課金・高難易度ステップを含みます。全サイトの最高額や、無課金で受け取れる金額を示すものではありません。異なるOS・期限・コースは別案件として比較しています。</p><div class="table-wrap"><table><tr><th>サイト</th><th>OS</th><th>合計</th><th>期限</th><th>確認日時</th></tr>'
    )
    for o in offers:
        parts.append(
            f'<tr><td><a href="{esc(o["url"],quote=True)}">{esc(o["site"])}</a></td><td>{esc(o["platform"])}</td><td>{o["rewardYen"]:,.0f}円相当</td><td>{esc(o["deadline"])}</td><td>{esc(o["retrievedAt"])}</td></tr>'
        )
    parts.append(
        "</table></div><p>"
        + esc(p.get("comparisonNote", ""))
        + '</p></section><section class="section" id="conditions"><h2>達成条件・期限・StepUp</h2>'
    )
    for o in offers:
        parts.append(
            f'<h3>{esc(o["site"])} / {esc(o["platform"])}</h3><p>{esc(o["condition"])}。{esc(o["deadline"])}</p><div class="table-wrap"><table><tr><th>達成条件</th><th>段階報酬</th><th>課金条件</th></tr>'
        )
        for s in o["steps"]:
            parts.append(
                f'<tr><td>{esc(s["condition"])}</td><td>{s["rewardYen"]:,.0f}円</td><td>{"あり" if s.get("purchaseRequired") else "なし（達成難易度とは別）"}</td></tr>'
            )
        parts.append("</table></div>")
    parts.append(
        '</section><section class="section" id="pace"><h2>実際の到達ペース</h2><p>条件が違う実例を平均化していません。不明な課金額・プレイ時間は不明のまま記載しています。</p><div class="pace-grid">'
    )
    for r in p["progress"]:
        if digest(r) not in result["verifiedProgressDigests"]:
            continue
        o = r["observation"]
        s = sources[r["sourceRef"]]
        spend = (
            "不明"
            if o["spendYen"] is None
            else ("無課金" if o["spendYen"] == 0 else f'{o["spendYen"]:,}円')
        )
        parts.append(
            f'<article class="pace-card"><strong>{esc(o["target"])}：{o["days"]}日</strong><p>課金：{spend} ／ プレイ時間：{esc(str(o["playHours"])) if o["playHours"] is not None else "不明"}<br>結果：{esc(o["outcome"])}<br>記録日・記事更新日：{esc(s.get("publishedAt") or "不明")} ／ {esc(s["playerKey"])}</p><p>{esc(o.get("context",""))} {refs([r["sourceRef"]])}</p></article>'
        )
    parts.append("</div></section>")
    for key in SECTIONS:
        parts.append(f'<section class="section" id="{key}"><h2>{LABELS[key]}</h2>')
        for b in p["guide"].get(key, []):
            parts.append(
                "<p>" + esc(b["text"]) + " " + refs(b.get("sourceRefs", [])) + "</p>"
            )
        parts.append("</section>")
    parts.append(
        '<section class="section sources" id="sources"><h2>調査ソース</h2><ul>'
    )
    for s in sources.values():
        parts.append(
            f'<li>{refs([s["id"]])} {esc(s["title"])}／{esc(s.get("publishedAt") or "日付表示なし")}<br>{esc(s["locator"])}</li>'
        )
    parts.append(
        '</ul></section></main><footer class="footer">POIGAME LAB｜ポイ活ゲーム案件をデータで比較・攻略</footer></body></html>'
    )
    return "\n".join(parts)


def run(root, folder, now):
    folder = folder.resolve()
    allowed = (root / "research/new-games").resolve()
    if allowed not in folder.parents:
        raise ValueError("output_outside_quarantine")
    registry = read(folder / "registry.json")
    selection = select(root, registry)
    atomic(folder / "selection.json", selection)
    results = []
    slugs = {c["slug"] for c in selection["candidates"]}
    existing = {norm(x["name"]) for x in catalog(root)}
    listed = {
        g["slug"] for g in registry
        if any(norm(a) in existing for a in [g["name"], *g["aliases"]])
    }
    for file in sorted((folder / "dossiers").glob("*.json")):
        p = read(file)
        if not re.fullmatch("[a-z0-9]+(?:-[a-z0-9]+)*", p.get("slug", "")):
            raise ValueError("unsafe_slug")
        if p.get("slug") in listed:
            # Published since this run was researched; the live page supersedes
            # the quarantined preview, so it is no longer a candidate.
            continue
        if p.get("slug") not in slugs:
            raise ValueError("dossier_not_in_discovered_candidates")
        result = evaluate(p, now)
        results.append({"slug": p["slug"], "name": p["name"], **result})
        preview = folder / "preview"
        preview.mkdir(exist_ok=True)
        (preview / (p["slug"] + "-guide.html")).write_text(
            render(p, result, root), encoding="utf-8"
        )
    # This is editorial triage, not a prediction of revenue or search demand.
    # Cap the reward contribution so impossible high-end steps cannot dominate.
    counts = {c["slug"]: c["listingSourceCount"] for c in selection["candidates"]}
    for r in results:
        parts = {
            "verifiedReward": round(
                min(30, math.log10(1 + (r["currentMaxObservedYen"] or 0)) * 6), 2
            ),
            "independentPace": min(40, r["independentPlayerCount"] * 20),
            "listingBreadthProxy": min(20, counts[r["slug"]] * 4),
            "currentTerms": 10 if r["verifiedOfferCount"] else 0,
        }
        r["priority"] = {
            "score": round(sum(parts.values()), 2),
            "components": parts,
            "searchDemand": "not_measured",
            "scope": "reviewed_identities_only",
        }
    results.sort(key=lambda r: (-r["priority"]["score"], r["slug"]))
    atomic(
        folder / "gate-report.json",
        {
            "checkedAt": now.isoformat(),
            "publicationWrites": 0,
            "externalAiCalls": 0,
            "results": results,
        },
    )
    links = "".join(
        f'<li><a href="{r["slug"]}-guide.html">{html.escape(r["name"])}</a> — {r["status"]}<ul>'
        + "".join("<li>" + html.escape(x) + "</li>" for x in r["issues"])
        + "</ul></li>"
        for r in results
    )
    (folder / "preview/index.html").write_text(
        '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>掲載前レビュー</title><body style="font-family:sans-serif;max-width:900px;margin:30px auto;padding:20px"><h1>新ゲーム掲載前レビュー</h1><p>本番への登録・公開は行いません。各記事の未解決項目を確認してください。</p><ul>'
        + links
        + "</ul></body></html>"
    )
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--as-of")
    args = ap.parse_args()
    now = (
        datetime.fromisoformat(args.as_of) if args.as_of else datetime.now(timezone.utc)
    )
    if now.tzinfo is None:
        raise ValueError("timezone_required")
    print(json.dumps(run(ROOT, ROOT / args.run, now), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
