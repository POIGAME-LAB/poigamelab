#!/usr/bin/env python3
"""Render a Kinoko-standard guide whose body text carries source citations such as ``[D1]``.

This is a thin, additive layer over ``scripts/render_guide_from_spec.py`` (which stays unchanged so
every existing guide keeps rendering byte-for-byte). The base renderer escapes all text; this module
post-processes only the page it produced for a cited spec:

* ``[D1]`` / ``[D3][D8]`` / ``[D1／編集部計算]`` -> each known source ID becomes a link to ``#src-D1``
  in the page's source list (labels such as 編集部計算 stay plain text, so editorial inferences remain
  visibly marked as such);
* ``**text**`` -> ``<strong>text</strong>``;
* the source list entries get ``id="src-<ID>"`` and the source block gets ``id="sources"`` so the
  table of contents can link to it;
* an optional ``related`` list of existing internal guide pages is inserted before the sources.

Usage::

    python scripts/render_cited_guide.py research/new-guides/2026-10-31/*.json
    python scripts/render_cited_guide.py --check research/new-guides/2026-10-31/*.json
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import render_guide_from_spec as base  # noqa: E402

ROOT = base.ROOT
e = base.e

BRACKET = re.compile(r"\[([^\[\]<>\n]{1,40})\]")
SOURCE_ID = re.compile(r"\b([A-Z]\d{1,2})\b")
BOLD = re.compile(r"\*\*([^*<>\n]+?)\*\*")
# Citation links also appear inside the purple hero, where the default link colour is unreadable.
CITE_STYLE = (
    "<style>\n"
    "a.cite{font-size:.82em;font-weight:800;text-decoration:none;white-space:nowrap}"
    ".hero a.cite{color:#ffe663}"
    ".source-line:target{background:#fff3c4}"
    ".related-guides .lab-list a{font-weight:800}\n"
    "</style>\n"
)
# A sentence may mention 平均 only to deny it (e.g. 「平均は出していません」「平均や達成保証ではありません」).
AVERAGE_DENIAL = re.compile(r"平均(?:は出していません|や達成保証ではありません|化していません|ではなく|値)")


def source_ids(spec: dict) -> list[str]:
    return [s["id"] for s in spec["sources"] if s.get("id")]


def base_view(spec: dict) -> dict:
    """The spec as the base renderer sees it: the ``sources`` TOC entry is provided by this layer."""
    view = copy.deepcopy(spec)
    view["toc"] = [t for t in view["toc"] if t["id"] != "sources"]
    return view


def citations(text: str) -> set[str]:
    found: set[str] = set()
    for m in BRACKET.finditer(text):
        found.update(SOURCE_ID.findall(m.group(1)))
    return found


def validate(spec: dict) -> list[str]:
    errs = [
        err for err in base.validate(base_view(spec))
        if err != "average_claim_needs_review"
    ]
    text = base.public_text(spec)
    if "平均" in text and text.count("平均") != len(AVERAGE_DENIAL.findall(text)):
        errs.append("average_claim_needs_review")
    ids = source_ids(spec)
    if not ids or len(ids) != len(spec["sources"]):
        errs.append("every_source_needs_id")
    if len(ids) != len(set(ids)):
        errs.append("duplicate_source_ids")
    cited = citations(text)
    for cid in sorted(cited - set(ids)):
        errs.append(f"unknown_citation:{cid}")
    for cid in sorted(set(ids) - cited):
        errs.append(f"uncited_source:{cid}")
    if "sources" not in [t["id"] for t in spec["toc"]]:
        errs.append("toc_must_include:sources")
    for item in spec.get("related", []):
        href = item.get("href", "")
        if not re.fullmatch(r"[a-z0-9-]+\.html", href) or not (ROOT / href).is_file():
            errs.append(f"related_link_missing:{href}")
        if href.startswith("game.html"):
            errs.append("related_link_must_not_be_comparison_page")
    return errs


def _link_bracket(m: re.Match, ids: set[str]) -> str:
    inner = SOURCE_ID.sub(
        lambda t: f'<a class="cite" href="#src-{t.group(1)}">{t.group(1)}</a>' if t.group(1) in ids else t.group(0),
        m.group(1),
    )
    return f"[{inner}]"


def render(spec: dict) -> str:
    html = base.render(base_view(spec))
    ids = set(source_ids(spec))
    head, body = html.split("<body>", 1)
    head = head.replace('<link rel="stylesheet" href="assets/guide-experience.css">', CITE_STYLE + '<link rel="stylesheet" href="assets/guide-experience.css">', 1)
    main, rest = body.split('<section class="sources">', 1)
    src_toc = next(t for t in spec["toc"] if t["id"] == "sources")
    assert main.count("</ol></nav>") == 1
    main = main.replace("</ol></nav>", f'<li><a href="#sources">{e(src_toc["label"])}</a></li></ol></nav>', 1)
    main = BOLD.sub(r"<strong>\1</strong>", main)
    main = BRACKET.sub(lambda m: _link_bracket(m, ids), main)
    for src in spec["sources"]:
        line = f'<span class="source-line"><a href="{e(src["url"])}" target="_blank" rel="noopener">{e(src["label"])}</a></span>'
        assert rest.count(line) == 1, src["id"]
        rest = rest.replace(line, line.replace('<span class="source-line">', f'<span class="source-line" id="src-{e(src["id"])}">', 1))
    related = ""
    if spec.get("related"):
        items = "".join(f'<li><a href="{e(r["href"])}">{e(r["label"])}</a></li>' for r in spec["related"])
        related = (
            '<section class="section related-guides" id="related"><h2>関連する攻略</h2>\n'
            f'<ul class="lab-list">{items}<li><a href="guides.html">攻略一覧を見る</a></li></ul>\n'
            "</section>\n\n"
        )
    return head + "<body>" + main + related + '<section class="sources" id="sources">' + rest


def write_outputs(spec: dict, root: Path = ROOT) -> list[Path]:
    errs = validate(spec)
    if errs:
        raise SystemExit("spec invalid: " + ", ".join(errs))
    html_path = root / spec["file"]
    json_path = root / "data" / "guide-experiences" / f"{spec['slug']}.json"
    html_path.write_text(render(spec), encoding="utf-8")
    json_path.write_text(json.dumps(base.experience_json(spec), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
