#!/usr/bin/env python3
"""Idempotently register rendered guide pages in the public-site plumbing.

Touches only: scripts/build_public_site.py (ROOT_FILES allowlist), sitemap.xml and
site-researched-guides.js (guide-only entries: no catalog/offer data is created).
Afterwards run ``node scripts/sync_static_guide_links.js`` to refresh the static guide hub.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def js_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def register(spec: dict, root: Path = ROOT) -> list[str]:
    changed: list[str] = []
    file = spec["file"]
    reg = spec["registry"]

    build = root / "scripts" / "build_public_site.py"
    text = build.read_text(encoding="utf-8")
    if f'"{file}"' not in text:
        anchor = '    "data-status.html",\n'
        if anchor not in text:
            raise SystemExit("build_public_site.py anchor missing")
        text = text.replace(anchor, f'    "{file}",\n' + anchor, 1)
        build.write_text(text, encoding="utf-8")
        changed.append("scripts/build_public_site.py")

    sm = root / "sitemap.xml"
    text = sm.read_text(encoding="utf-8")
    loc = f"https://poigamelab.com/{file}"
    if f"<loc>{loc}</loc>" not in text:
        text = text.replace("</urlset>", f"  <url><loc>{loc}</loc></url>\n</urlset>", 1)
        sm.write_text(text, encoding="utf-8")
        changed.append("sitemap.xml")

    js = root / "site-researched-guides.js"
    text = js.read_text(encoding="utf-8")
    if f'href: {js_str(file)}' not in text:
        entry = (
            f'  {js_str(spec["game"])}: {{\n'
            f'    title: {js_str(reg["title"])},\n'
            f'    description: {js_str(reg["description"])},\n'
            f'    links: [\n'
            f'      {{ label: {js_str(reg["label"])}, href: {js_str(file)} }}\n'
            f'    ]\n'
            f'  }}'
        )
        m = re.search(r"\n\}\);\s*$", text)
        if not m:
            raise SystemExit("site-researched-guides.js tail not recognised")
        text = text[: m.start()] + ",\n" + entry + text[m.start():]
        js.write_text(text, encoding="utf-8")
        changed.append("site-researched-guides.js")
    return changed


def main(argv=None) -> int:
    for path in (argv or sys.argv[1:]):
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
        print(path, register(spec) or "already registered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
