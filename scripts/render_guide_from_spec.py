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
BLOCK_TYPES = {"p", "h3", "ul", "key", "warning", "decision", "table"}


def e(value: object) -> str:
    return escape(str(value), quote=True)


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
    if not re.fullmatch(r"[a-z0-9-]+-guide\.html", spec["file"]):
        errs.append("bad_file_name")
    ids = [s["id"] for s in spec["sections"]]
    if len(ids) != len(set(ids)):
        errs.append("duplicate_section_ids")
    toc_ids = [t["id"] for t in spec["toc"]]
    for t in toc_ids:
        if t not in ids and t != "pace":
            errs.append(f"toc_target_missing:{t}")
    for must in ("condition", "pace"):
        if must not in toc_ids:
            errs.append(f"toc_must_include:{must}")
    if "condition" not in ids:
        errs.append("section_missing:condition")
    for sec in spec["sections"]:
        if sec["id"] not in toc_ids:
            errs.append(f"section_not_in_toc:{sec['id']}")
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
    for word in FORBIDDEN_PUBLIC:
        if word in text:
            errs.append(f"forbidden_public_text:{word}")
    if "平均" in text and "平均ではなく" not in text and "平均化" not in text and "平均値" not in text:
        errs.append("average_claim_needs_review")
    return errs


def render_block(b: dict) -> str:
    t = b["t"]
    if t == "p":
        return f"<p>{e(b['x'])}</p>"
    if t == "h3":
        return f"<h3>{e(b['x'])}</h3>"
    if t == "key":
        return f'<div class="key">{e(b["x"])}</div>'
    if t == "warning":
        return f'<div class="warning">{e(b["x"])}</div>'
    if t == "ul":
        return '<ul class="lab-list">\n' + "\n".join(f"<li>{e(i)}</li>" for i in b["items"]) + "\n</ul>"
    if t == "decision":
        cards = "\n".join(f'<div class="decision-card"><strong>{e(c["h"])}</strong>{e(c["x"])}</div>' for c in b["cards"])
        return f'<div class="decision">\n{cards}\n</div>'
    if t == "table":
        head = "".join(f"<th>{e(c)}</th>" for c in b["head"])
        rows = "\n".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in b["rows"])
        return f'<div class="table-wrap"><table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n{rows}\n</tbody>\n</table></div>'
    raise ValueError(t)


def render(spec: dict) -> str:
    prefix, style = _head_template()
    canonical = f"https://poigamelab.com/{spec['file']}"
    ctx = spec["context"]
    head = (
        f"{prefix}"
        f'<link rel="canonical" href="{e(canonical)}">\n'
        f'<meta name="description" content="{e(spec["description"])}">\n'
        f"<title>{e(spec['title'])} | POIGAME LAB</title>\n"
        f"{style}\n"
        '<link rel="stylesheet" href="assets/guide-experience.css">\n'
        "</head>\n"
    )
    toc_items = "".join(f'<li><a href="#{e(t["id"])}">{e(t["label"])}</a></li>' for t in spec["toc"])
    stats = "".join(f'<div class="stat"><span>{e(s["label"])}</span><strong>{e(s["value"])}</strong></div>' for s in spec["heroStats"])
    body_sections: list[str] = []
    for sec in spec["sections"]:
        inner = "\n".join(render_block(b) for b in sec["blocks"])
        body_sections.append(f'<section class="section" id="{e(sec["id"])}"><h2>{e(sec["h2"])}</h2>\n{inner}\n</section>')
        if sec["id"] == "condition":
            body_sections.append(
                f'<section id="pace" class="experience-panel" data-experience-src="data/guide-experiences/{e(spec["slug"])}.json" aria-live="polite"></section>'
            )
    sources = "\n".join(
        f'<span class="source-line"><a href="{e(s["url"])}" target="_blank" rel="noopener">{e(s["label"])}</a></span>' for s in spec["sources"]
    )
    page = f"""<body>
<div data-poigame-header><nav aria-label="メインメニュー"><a href="index.html">POIGAME LAB トップ</a> <a href="offers.html">案件一覧</a> <a href="guides.html">攻略一覧</a> <a href="about.html">POIGAME LABとは</a> <a href="contact.html">お問い合わせ</a></nav></div>
<script src="site-header.js?v=20260905-0315"></script>
<div class="poigame-context-bar">
  <div class="poigame-context-bar__inner">
    <span>{e(spec['game'])} 攻略ガイド</span>
    <a href="{e(ctx['href'])}">{e(ctx['label'])}</a>
  </div>
</div>
<main class="page">
<section class="hero">
<div class="eyebrow">POIGAME LAB 攻略データ</div>
<h1>{e(spec['game'])} ポイ活攻略</h1>
<p class="lead">{e(spec['lead'])}</p>
<div class="stats">{stats}</div>
<p class="hero-note">{e(spec['heroNote'])}</p>
</section>

<nav class="toc" aria-label="目次"><h2>目次</h2><ol>
{toc_items}</ol></nav>

{chr(10).join(body_sections)}

<section class="sources">
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
