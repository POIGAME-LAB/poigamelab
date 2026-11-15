#!/usr/bin/env python3
"""Render a Kinoko-standard guide page (+ its player-experience JSON) from a content spec.

The head/style/header/footer markup is copied from ``kinoko-guide.html`` so every new guide
shares one design. The spec holds only facts that were traced to a source URL; this script
never invents data. Usage:

    python scripts/render_guide_from_spec.py research/new-guides/2026-10-16/topwar.json
    python scripts/render_guide_from_spec.py --check research/new-guides/2026-10-16/*.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "kinoko-guide.html"

# Reader-facing text must not carry research-process logs (Notion publication gate, 2026-09-22).
FORBIDDEN_PUBLIC = (
    "検索しました", "検索した結果", "見つかりませんでした", "見つからなかった", "調査しました",
    "Instagramでは", "YouTubeでは", "Xでは", "ウェブ検索", "Web検索", "Google検索",
    "読み込み中", "準備中", "調査中", "TODO", "ダミー", "サンプル文",
)
BLOCK_TYPES = {"p", "h3", "ul", "ol", "key", "warning", "decision", "table"}

# Opt-in inline markup (spec["inlineMarkup"] = true): **bold**, [label](https://...) and [G1]-style source
# citations that jump to the matching entry of the page's source list. Specs without the flag render as before.
_INLINE = re.compile(
    r"\*\*(?P<bold>.+?)\*\*|\[(?P<label>[^\[\]]+)\]\((?P<url>https?://[^)\s]+)\)|\[(?P<cite>[A-Z]\d+)\]"
)
CITATION = re.compile(r"\[([A-Z]\d+)\]")
SITE_ORIGIN = "https://poigamelab.com/"
# Citation links sit inside the purple hero too, where the default link colour is unreadable.
CITE_STYLE = "<style>\na.cite{font-size:.82em;font-weight:800;text-decoration:none;white-space:nowrap}\n.hero a.cite{color:#ffe663}\n</style>\n"


def e(value: object) -> str:
    return escape(str(value), quote=True)


def inline(text: object, ids: set | None) -> str:
    """Escape ``text``; with ``ids`` (inline markup enabled) also turn markup into HTML."""
    text = str(text)
    if ids is None:
        return e(text)
    parts: list[str] = []
    pos = 0
    for m in _INLINE.finditer(text):
        parts.append(e(text[pos:m.start()]))
        if m.group("bold") is not None:
            parts.append(f"<strong>{inline(m.group('bold'), ids)}</strong>")
        elif m.group("url") is not None:
            url = m.group("url")
            if url.startswith(SITE_ORIGIN):
                parts.append(f'<a href="{e(url[len(SITE_ORIGIN):])}">{e(m.group("label"))}</a>')
            else:
                parts.append(f'<a href="{e(url)}" target="_blank" rel="noopener">{e(m.group("label"))}</a>')
        elif m.group("cite") in ids:
            cid = m.group("cite")
            parts.append(f'<a class="cite" href="#src-{e(cid)}">[{e(cid)}]</a>')
        else:
            parts.append(e(m.group(0)))
        pos = m.end()
    parts.append(e(text[pos:]))
    return "".join(parts)


def _head_template() -> tuple[str, str]:
    html = TEMPLATE.read_text(encoding="utf-8")
    prefix = html[: html.index('<link rel="canonical"')]
    style = re.search(r"<style>\n.*?\n</style>", html, re.S).group(0)
    return prefix, style


def public_text(spec: dict) -> str:
    parts = [spec.get("title", ""), spec.get("description", ""), spec.get("lead", ""), spec.get("heroNote", "")]
    parts += [f"{s['label']}{s['value']}" for s in spec.get("heroStats", [])]
    for sec in spec.get("sections", []):
        parts.append(sec.get("h2", ""))
        for b in sec.get("blocks", []):
            for key in ("x", "h"):
                if key in b:
                    parts.append(str(b[key]))
            parts += [str(i) for i in b.get("items", [])]
            for card in b.get("cards", []):
                parts += [card.get("h", ""), card.get("x", "")]
            parts += [str(c) for c in b.get("head", [])]
            for row in b.get("rows", []):
                parts += [str(c) for c in row]
    parts.append(spec.get("sourceNote", ""))
    exp = spec.get("experience", {})
    parts += [exp.get(k, "") for k in ("title", "intro", "notice", "footnote")]
    for p in exp.get("players", []):
        parts += [p.get("summary", ""), p.get("note", "")]
        for m in p.get("milestones", []):
            parts += [str(m.get("label", "")), str(m.get("detail", "")), str(m.get("dayLabel", ""))]
    return "\n".join(str(p) for p in parts)


def validate(spec: dict) -> list[str]:
    errs: list[str] = []
    for key in ("slug", "game", "file", "title", "description", "lead", "heroStats", "toc", "sections", "sources", "experience", "context"):
        if not spec.get(key):
            errs.append(f"missing:{key}")
    if errs:
        return errs
    links = spec.get("offerLinks") or []
    if not links:
        errs.append("offerLinks_required")
    for link in links:
        u = urlsplit(link.get("url", ""))
        if u.scheme != "https" or not u.netloc or not link.get("label"):
            errs.append(f"bad_offer_link:{link}")
        if link.get("url") not in {x.get("url") for x in spec["sources"]}:
            errs.append(f"offer_link_not_in_sources:{link.get('url')}")
    ctx_url = urlsplit(spec["context"].get("href", ""))
    if ctx_url.scheme != "https":
        errs.append("context_href_must_be_external_offer_page")
    if not re.fullmatch(r"[a-z0-9-]+-guide\.html", spec["file"]):
        errs.append("bad_file_name")
    ids = [s["id"] for s in spec["sections"]]
    if len(ids) != len(set(ids)):
        errs.append("duplicate_section_ids")
    toc_ids = [t["id"] for t in spec["toc"]]
    for t in toc_ids:
        if t not in ids and t not in ("pace", "sources"):
            errs.append(f"toc_target_missing:{t}")
    for must in ("condition", "pace"):
        if must not in toc_ids:
            errs.append(f"toc_must_include:{must}")
    if "condition" not in ids:
        errs.append("section_missing:condition")
    source_urls = {s.get("url") for s in spec["sources"]}
    for sec in spec["sections"]:
        if sec["id"] not in toc_ids:
            errs.append(f"section_not_in_toc:{sec['id']}")
        for ref in sec.get("sourceRefs", []):
            if ref not in source_urls:
                errs.append(f"section_source_ref_not_in_sources:{sec['id']}:{ref}")
        for b in sec.get("blocks", []):
            if b.get("t") not in BLOCK_TYPES:
                errs.append(f"bad_block:{b.get('t')}")
    for src in spec["sources"]:
        u = urlsplit(src.get("url", ""))
        if u.scheme != "https" or not u.netloc:
            errs.append(f"bad_source_url:{src.get('url')}")
    players = spec["experience"].get("players", [])
    if len(players) < 3:
        errs.append("experience_needs_3_players")
    src_urls = {s["url"] for s in spec["sources"]}
    for p in players:
        if not p.get("sources"):
            errs.append(f"player_without_source:{p.get('id')}")
        for u in p.get("sources", []):
            if urlsplit(u).scheme != "https":
                errs.append(f"player_bad_url:{u}")
            if u not in src_urls and u.split("?")[0] not in {x.split("?")[0] for x in src_urls}:
                errs.append(f"player_source_not_in_sources:{u}")
        if not p.get("milestones"):
            errs.append(f"player_without_milestones:{p.get('id')}")
    text = public_text(spec)
    if spec.get("inlineMarkup"):
        source_ids = [s.get("id") for s in spec["sources"] if s.get("id")]
        if len(source_ids) != len(set(source_ids)):
            errs.append("duplicate_source_ids")
        for cid in sorted(set(CITATION.findall(text)) - set(source_ids)):
            errs.append(f"unknown_citation:{cid}")
    for word in FORBIDDEN_PUBLIC:
        if word in text:
            errs.append(f"forbidden_public_text:{word}")
    if "平均" in text and "平均ではなく" not in text and "平均化" not in text and "平均値" not in text:
        errs.append("average_claim_needs_review")
    return errs


def render_block(b: dict, ids: set | None = None) -> str:
    t = b["t"]

    def f(value: object) -> str:
        return inline(value, ids)

    if t == "p":
        return f"<p>{f(b['x'])}</p>"
    if t == "h3":
        return f"<h3>{f(b['x'])}</h3>"
    if t == "key":
        return f'<div class="key">{f(b["x"])}</div>'
    if t == "warning":
        return f'<div class="warning">{f(b["x"])}</div>'
    if t in ("ul", "ol"):
        return f'<{t} class="lab-list">\n' + "\n".join(f"<li>{f(i)}</li>" for i in b["items"]) + f"\n</{t}>"
    if t == "decision":
        cards = "\n".join(f'<div class="decision-card"><strong>{f(c["h"])}</strong>{f(c["x"])}</div>' for c in b["cards"])
        return f'<div class="decision">\n{cards}\n</div>'
    if t == "table":
        head = "".join(f"<th>{f(c)}</th>" for c in b["head"])
        rows = "\n".join("<tr>" + "".join(f"<td>{f(c)}</td>" for c in r) + "</tr>" for r in b["rows"])
        return f'<div class="table-wrap"><table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n{rows}\n</tbody>\n</table></div>'
    raise ValueError(t)


def render(spec: dict) -> str:
    prefix, style = _head_template()
    ids = {s["id"] for s in spec["sources"] if s.get("id")} if spec.get("inlineMarkup") else None
    canonical = f"https://poigamelab.com/{spec['file']}"
    ctx = spec["context"]
    head = (
        f"{prefix}"
        f'<link rel="canonical" href="{e(canonical)}">\n'
        f'<meta name="description" content="{e(spec["description"])}">\n'
        f"<title>{e(spec['title'])} | POIGAME LAB</title>\n"
        f"{style}\n"
        f"{CITE_STYLE if ids is not None else ''}"
        '<link rel="stylesheet" href="assets/guide-experience.css">\n'
        "</head>\n"
    )
    toc_items = "".join(f'<li><a href="#{e(t["id"])}">{e(t["label"])}</a></li>' for t in spec["toc"])
    stats = "".join(f'<div class="stat"><span>{e(s["label"])}</span><strong>{e(s["value"])}</strong></div>' for s in spec["heroStats"])
    body_sections: list[str] = []
    for sec in spec["sections"]:
        inner = "\n".join(render_block(b, ids) for b in sec["blocks"])
        body_sections.append(f'<section class="section" id="{e(sec["id"])}"><h2>{e(sec["h2"])}</h2>\n{inner}\n</section>')
        if sec["id"] == "condition":
            offer_items = "".join(
                f'<li><a href="{e(l["url"])}" target="_blank" rel="noopener nofollow">{e(l["label"])}</a></li>' for l in spec["offerLinks"]
            )
            body_sections[-1] = body_sections[-1].replace(
                "\n</section>",
                '\n<div class="key offer-guide">この攻略の案件は、当サイトの案件一覧（比較ページ）にはまだ掲載していません。'
                "現在の条件・金額は、次の案件ページで直接ご確認ください。"
                f'<ul class="lab-list">{offer_items}</ul></div>\n</section>',
            )
            body_sections.append(
                f'<section id="pace" class="experience-panel" data-experience-src="data/guide-experiences/{e(spec["slug"])}.json" aria-live="polite"></section>'
            )
    def source_line(s: dict) -> str:
        anchor = f' id="src-{e(s["id"])}"' if ids is not None and s.get("id") else ""
        return f'<span class="source-line"{anchor}><a href="{e(s["url"])}" target="_blank" rel="noopener">{e(s["label"])}</a></span>'

    sources = "\n".join(source_line(s) for s in spec["sources"])
    sources_open = '<section class="sources" id="sources">' if any(t["id"] == "sources" for t in spec["toc"]) else '<section class="sources">'
    page = f"""<body>
<div data-poigame-header><nav aria-label="メインメニュー"><a href="index.html">POIGAME LAB トップ</a> <a href="offers.html">案件一覧</a> <a href="guides.html">攻略一覧</a> <a href="about.html">POIGAME LABとは</a> <a href="contact.html">お問い合わせ</a></nav></div>
<script src="site-header.js?v=20260905-0315"></script>
<div class="poigame-context-bar">
  <div class="poigame-context-bar__inner">
    <span>{e(spec['game'])} 攻略ガイド</span>
    <a href="{e(ctx['href'])}" target="_blank" rel="noopener nofollow">{e(ctx['label'])}</a>
  </div>
</div>
<main class="page">
<section class="hero">
<div class="eyebrow">POIGAME LAB 攻略データ</div>
<h1>{e(spec['game'])} ポイ活攻略</h1>
<p class="lead">{inline(spec['lead'], ids)}</p>
<div class="stats">{stats}</div>
<p class="hero-note">{inline(spec['heroNote'], ids)}</p>
</section>

<nav class="toc" aria-label="目次"><h2>目次</h2><ol>
{toc_items}</ol></nav>

{chr(10).join(body_sections)}

{sources_open}
<h2>調査ソース</h2>
{sources}
<div class="source-note">{e(spec['sourceNote'])}</div>
</section>
</main>
<footer class="footer">POIGAME LAB｜ポイ活ゲーム案件をデータで比較・攻略</footer>
<script src="assets/guide-experience.js"></script>
  <footer data-poigame-footer-fallback><nav aria-label="サイト情報"><a href="index.html">トップ</a> <a href="offers.html">案件一覧</a> <a href="guides.html">攻略一覧</a> <a href="about.html">運営情報・免責事項</a> <a href="privacy.html">プライバシーポリシー</a> <a href="contact.html">お問い合わせ</a></nav></footer>
<script src="site-footer.js"></script>
</body>
</html>
"""
    return head + page


def experience_json(spec: dict) -> dict:
    exp = spec["experience"]
    out = {"schemaVersion": 1, "game": spec["game"], "updatedAt": exp["updatedAt"]}
    for key in ("title", "intro", "notice", "footnote", "initialVisible"):
        if key in exp:
            out[key] = exp[key]
    out["players"] = exp["players"]
    return out


def write_outputs(spec: dict, root: Path = ROOT) -> list[Path]:
    errs = validate(spec)
    if errs:
        raise SystemExit("spec invalid: " + ", ".join(errs))
    html_path = root / spec["file"]
    json_path = root / "data" / "guide-experiences" / f"{spec['slug']}.json"
    html_path.write_text(render(spec), encoding="utf-8")
    json_path.write_text(json.dumps(experience_json(spec), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return [html_path, json_path]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--check", action="store_true", help="validate only")
    args = ap.parse_args(argv)
    bad = 0
    for path in args.specs:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
        errs = validate(spec)
        if errs:
            bad += 1
            print(f"{path}: INVALID: {errs}")
            continue
        if args.check:
            print(f"{path}: ok")
        else:
            outs = write_outputs(spec)
            print(f"{path}: wrote {[str(o.relative_to(ROOT)) for o in outs]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
