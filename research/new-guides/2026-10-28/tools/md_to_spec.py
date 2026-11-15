#!/usr/bin/env python3
"""Parse a Work ``article.md`` (2026-10-27 delivery) into the block structure used by
``scripts/render_guide_from_spec.py``.

Only structure is converted here. Audit corrections and per-article settings live in
``build_specs.py``; nothing in this module changes wording.
"""
from __future__ import annotations

import re
from pathlib import Path

ANCHOR = re.compile(r'^<a id="([a-z0-9-]+)"></a>$')
TOC_ITEM = re.compile(r"^\d+\. \[(?P<label>[^\]]+)\]\(#(?P<id>[a-z0-9-]+)\)$")
SOURCE_ITEM = re.compile(r"^- \[(?P<id>[A-Z]\d+)：(?P<label>[^\]]+)\]\((?P<url>https://[^)\s]+)\)$")


def split_front_matter(text: str) -> tuple[dict, str]:
    assert text.startswith("---\n"), "front matter missing"
    head, body = text[4:].split("\n---\n", 1)
    meta = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return meta, body


def parse_table(lines: list[str]) -> dict:
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in lines]
    head, sep, body = rows[0], rows[1], rows[2:]
    assert all(set(c) <= set(":- ") for c in sep), sep
    assert all(len(r) == len(head) for r in body), (head, body)
    return {"t": "table", "head": head, "rows": body}


def parse_blocks(lines: list[str]) -> list[dict]:
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("### "):
            blocks.append({"t": "h3", "x": line[4:].strip()})
            i += 1
        elif line.startswith("|"):
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            blocks.append(parse_table(lines[i:j]))
            i = j
        elif re.match(r"^- ", line) or re.match(r"^\d+\. ", line):
            ordered = bool(re.match(r"^\d+\. ", line))
            pat = re.compile(r"^\d+\. (.*)$" if ordered else r"^- (.*)$")
            items = []
            while i < len(lines) and pat.match(lines[i]):
                items.append(pat.match(lines[i]).group(1).strip())
                i += 1
            blocks.append({"t": "ol" if ordered else "ul", "items": items})
        else:
            blocks.append({"t": "p", "x": line.strip()})
            i += 1
    return blocks


def parse_article(path: Path) -> dict:
    meta, body = split_front_matter(path.read_text(encoding="utf-8"))
    lines = body.splitlines()
    h1 = next(i for i, l in enumerate(lines) if l.startswith("# "))
    toc_at = next(i for i, l in enumerate(lines) if l.strip() == "## 目次")
    intro = [b["x"] for b in parse_blocks(lines[h1 + 1 : toc_at])]
    toc: list[dict] = []
    i = toc_at + 1
    while i < len(lines) and not ANCHOR.match(lines[i]):
        m = TOC_ITEM.match(lines[i])
        if m:
            toc.append({"id": m["id"], "label": m["label"]})
        i += 1
    sections: list[dict] = []
    sources: list[dict] = []
    while i < len(lines):
        m = ANCHOR.match(lines[i])
        assert m, lines[i]
        sid = m[1]
        assert lines[i + 1].startswith("## "), lines[i + 1]
        heading = lines[i + 1][3:].strip()
        j = i + 2
        while j < len(lines) and not ANCHOR.match(lines[j]):
            j += 1
        chunk = lines[i + 2 : j]
        if sid == "sources":
            note = []
            for l in chunk:
                s = SOURCE_ITEM.match(l)
                if s:
                    sources.append({"id": s["id"], "label": f'{s["id"]}：{s["label"]}', "url": s["url"]})
                elif l.strip():
                    note.append(l.strip())
            sources_intro = note
        else:
            sections.append({"id": sid, "h2": heading, "blocks": parse_blocks(chunk)})
        i = j
    return {
        "meta": meta,
        "intro": intro,
        "toc": toc,
        "sections": sections,
        "sources": sources,
        "sourcesIntro": sources_intro,
    }
