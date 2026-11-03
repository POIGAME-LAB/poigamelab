#!/usr/bin/env python3
"""Convert the 2026-10-31 ChatGPT Work manuscripts into render specs without rewriting them.

Body text (paragraphs, tables, FAQ, source IDs) is carried over from ``work-originals/<slug>/article.md``
verbatim; experience data is ``work-originals/<slug>/experiences.json`` unchanged. The only additions
are page furniture defined in ``PAGE`` below (hero stats taken from the manuscript's own numbers, the
offer link, related existing guides, and the 2026-11-04 re-check note backed by
``evidence/offer-recheck-20261104.json``).

    python -I research/new-guides/2026-10-31/tools/md_to_spec.py   # writes ../<slug>.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

BATCH = Path(__file__).resolve().parents[1]
ORIG = BATCH / "work-originals"
RECHECK = BATCH / "evidence" / "offer-recheck-20261104.json"

WARAU = "https://www.warau.jp/contents/point/pointEntrance.php?point_id="

PAGE = {
    "domino-dreams": {
        "heroStats": [
            {"label": "案件期限（iOS）", "value": "60日"},
            {"label": "全Step表示合計", "value": "9,500pt"},
            {"label": "課金条件", "value": "2Step"},
        ],
        "offerLinks": [{"label": "ワラウの案件ページ（iOS・192689）", "url": WARAU + "192689"}],
        "related": [
            {"label": "ディズニーソリティア ポイ活攻略", "href": "disney-solitaire-guide.html"},
            {"label": "クロンダイクの冒険 ポイ活攻略", "href": "klondike-adventures-guide.html"},
            {"label": "マジックジグソーパズル ポイ活攻略", "href": "magic-jigsaw-puzzles-guide.html"},
        ],
        "registry": {
            "linkLabel": "CHAPTER攻略を読む →",
            "description": "ワラウiOS案件（60日・CHAPTER30まで）の全Stepと、CHAPTERとLEVELの違い、コイン回収・救済・倍率の判断、23日でCHAPTER8を終えた記録などの実例と撤退ラインをまとめています。",
        },
    },
    "arrows": {
        "heroStats": [
            {"label": "期限（インストール起算）", "value": "7・15・25・60日"},
            {"label": "全11Step合計", "value": "15,200pt"},
            {"label": "課金Step", "value": "なし"},
        ],
        "offerLinks": [{"label": "ワラウの案件ページ（iOS・207054）", "url": WARAU + "207054"}],
        "related": [
            {"label": "Sea Block 1010 ポイ活攻略", "href": "sea-block-1010-guide.html"},
            {"label": "マジックジグソーパズル ポイ活攻略", "href": "magic-jigsaw-puzzles-guide.html"},
            {"label": "Merge Help ポイ活攻略", "href": "merge-help-guide.html"},
        ],
        "registry": {
            "linkLabel": "レベル5309・20000攻略を読む →",
            "description": "ワラウiOS案件（7・15・25・60日の期限別・計11Step）の条件と、レベル20000を59日でクリアした例・約10日で撤退した例、1日あたりの必要面数の計算、盤面の読み方をまとめています。",
        },
    },
    "sengoku-fubu": {
        "heroStats": [
            {"label": "案件期限（iOS・Android）", "value": "30日"},
            {"label": "全8Step表示合計", "value": "11,640pt"},
            {"label": "課金条件", "value": "2Step"},
        ],
        "offerLinks": [
            {"label": "ワラウの案件ページ（iOS・206085）", "url": WARAU + "206085"},
            {"label": "ワラウの案件ページ（Android・206086）", "url": WARAU + "206086"},
        ],
        "related": [
            {"label": "三國志 真戦 ポイ活攻略", "href": "sangokushi-shinsen-guide.html"},
            {"label": "天地英雄伝 ポイ活攻略", "href": "tenchi-eiyuden-guide.html"},
            {"label": "商人放浪記 ポイ活攻略", "href": "shounin-hourouki-guide.html"},
        ],
        "registry": {
            "linkLabel": "侍大将・少史攻略を読む →",
            "description": "ワラウ案件（iOS・Android共通、30日）の全Stepと、侍大将・少史・頂天武将の条件の違い、初心者配布が対象外になる点、操作時間の異なる実例、小判チャージと撤退判断をまとめています。",
        },
    },
}

# The manuscript's own "実際の到達ペース" section becomes the comparison table right after the shared
# experience panel (which owns id="pace" and the same title), so its heading must not repeat.
RECORDS_ID = "records"
RECORDS_H2 = "到達記録の比較表"
RECORDS_TOC = "到達記録の比較表"


def _table(lines: list[str]) -> dict:
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    return {"t": "table", "head": rows[0], "rows": rows[2:]}


def parse_article(text: str) -> dict:
    lines = text.splitlines()
    assert lines[0].startswith("# ")
    title = lines[0][2:].strip()
    i = 1
    intro: list[str] = []
    while not lines[i].startswith("## 目次"):
        if lines[i].strip():
            intro.append(lines[i].strip())
        i += 1
    i += 1
    toc = []
    while not lines[i].startswith("<a id="):
        m = re.match(r"\d+\. \[(.+?)\]\(#([a-z-]+)\)", lines[i].strip())
        if m:
            toc.append({"id": m.group(2), "label": m.group(1)})
        i += 1
    sections: list[dict] = []
    sources: list[dict] = []
    source_note = ""
    cur = None
    para_buf: list[str] = []
    while i < len(lines):
        ln = lines[i]
        m = re.match(r'<a id="([a-z-]+)"></a>', ln)
        if m:
            cur = {"id": m.group(1), "h2": None, "blocks": []}
            sections.append(cur)
            i += 1
            continue
        if ln.startswith("## "):
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
            assert m2, ln
            sources.append({"id": m2.group(2), "label": m2.group(1), "url": m2.group(3)})
        elif ln.strip():
            s = ln.strip()
            if cur["id"] == "sources":
                source_note = s
            elif re.fullmatch(r"\*\*[^*]+\*\*", s):
                cur["blocks"].append({"t": "key", "x": s})
            else:
                cur["blocks"].append({"t": "p", "x": s})
        i += 1
    assert not para_buf
    return {"title": title, "intro": intro, "toc": toc, "sections": sections, "sources": sources, "sourceNote": source_note}


def build(slug: str) -> dict:
    d = ORIG / slug
    art = parse_article((d / "article.md").read_text(encoding="utf-8"))
    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
    exp = json.loads((d / "experiences.json").read_text(encoding="utf-8"))
    recheck = json.loads(RECHECK.read_text(encoding="utf-8"))
    page = PAGE[slug]
    assert art["title"] == meta["seoTitle"] == meta["title"]
    assert len(art["intro"]) == 2, art["intro"]

    sections = [s for s in art["sections"] if s["id"] != "sources"]
    for s in sections:
        if s["id"] == "pace":
            s["id"], s["h2"] = RECORDS_ID, RECORDS_H2
    toc = []
    for t in art["toc"]:
        toc.append(t)
        if t["id"] == "pace":
            toc.append({"id": RECORDS_ID, "label": RECORDS_TOC})

    checks = [c for c in recheck["checks"] if c["slug"] == slug]
    assert checks and all(c["matchesManuscript"] for c in checks), slug
    when = recheck["checkedAtJst"][:10]
    y, mth, day = when.split("-")
    note = (
        f"{int(y)}年{int(mth)}月{int(day)}日（日本時間）に同じ案件ページを再取得し、"
        "全Stepの条件・個別報酬・合計・期限が上表と同じであることを確認しました。"
        "参加時の画面に表示される条件が優先されます。"
    )
    cond = next(s for s in sections if s["id"] == "condition")
    first_table = next(k for k, b in enumerate(cond["blocks"]) if b["t"] == "table")
    cond["blocks"].insert(first_table + 1, {"t": "key", "x": note})

    source_urls = {s["url"] for s in art["sources"]}
    for link in page["offerLinks"]:
        assert link["url"] in source_urls, link

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
        "sourceNote": art["sourceNote"] + f" 案件ページは{int(mth)}月{int(day)}日に再確認しています。",
        "context": {"href": page["offerLinks"][0]["url"], "label": "ワラウの現在の案件ページを見る →"},
        "offerLinks": page["offerLinks"],
        "related": page["related"],
        "registry": {"title": f"{meta['game']} ポイ活攻略", **page["registry"]},
        "experience": experience,
    }


def main() -> None:
    for slug in PAGE:
        spec = build(slug)
        out = BATCH / f"{slug}.json"
        out.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("wrote", out.relative_to(BATCH.parents[2]))


if __name__ == "__main__":
    main()
