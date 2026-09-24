#!/usr/bin/env python3
"""Render a safe, mobile-friendly guide page from a new-game content package.

The renderer performs no research and no AI calls. It only turns a package that
passes the deterministic pre-render gate into HTML, then re-runs the final gate so
V30 can never adopt a game whose guide file failed to render.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from urllib.parse import quote

import new_game_content_gate as gate

ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = ROOT / "data" / "new_game_content_packages"


def esc(value):
    return html.escape(str(value or ""), quote=True)


def source_map(payload):
    out = {}
    for channel in gate.REQUIRED_CHANNELS:
        lane = (payload.get("research") or {}).get(channel) or {}
        for row in lane.get("sources") or []:
            if isinstance(row, dict):
                sid = str(row.get("id") or "").strip()
                if sid:
                    out[sid] = {**row, "channel": channel}
    return out


def render_html(payload, validated):
    game = validated["game"]
    guide = payload["guide"]
    sources = source_map(payload)
    sections = []
    for index, section in enumerate(guide.get("sections") or [], 1):
        refs = []
        for sid in section.get("sourceRefs") or []:
            row = sources[sid]
            refs.append(f'<a href="{esc(row["url"])}" rel="noopener noreferrer" target="_blank">出典</a>')
        sections.append(
            f'<section class="section" id="s{index}"><h2>{esc(section["heading"])}</h2>'
            f'<p>{esc(section["text"])}</p><p class="refs">{" ／ ".join(refs)}</p></section>'
        )

    progress = []
    for row in payload.get("progress") or []:
        source = sources[row["sourceRef"]]
        progress.append(
            '<li><strong>公開プレイヤー記録</strong>'
            f'<span>{esc(row["summary"])}</span>'
            f'<a href="{esc(source["url"])}" rel="noopener noreferrer" target="_blank">元投稿・元ページを確認</a></li>'
        )

    progress_section = ""
    if progress:
        progress_section = (
            '<section class="section"><h2>みんなの進捗</h2>'
            '<p class="notice">公開投稿・公開ページから確認できた個人の進捗例です。'
            'プレイ時間や課金状況で差が出るため、保証値ではありません。</p>'
            f'<ul class="progress">{"".join(progress)}</ul></section>'
        )

    source_rows = []
    for sid, row in sorted(sources.items()):
        claim = str(row.get("claim") or "").strip()
        label = claim if claim else f'{row.get("channel", "source")}で確認した参照先'
        source_rows.append(
            f'<li><span>{esc(label)}</span><a href="{esc(row["url"])}" rel="noopener noreferrer" target="_blank">{esc(row["url"])}</a></li>'
        )

    description = guide["overview"]
    canonical = f'https://poigamelab.com/{validated["guidePath"]}'
    compare = 'game.html?game=' + quote(game, safe='')
    image = validated["image"]
    title = guide["title"]
    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="canonical" href="{esc(canonical)}">
<meta name="description" content="{esc(description)}">
<title>{esc(title)} | POIGAME LAB</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Hiragino Kaku Gothic ProN","Yu Gothic",Arial,sans-serif;background:#f8f6ff;color:#302744;line-height:1.85}}a{{color:#6540e8}}.page{{max-width:940px;margin:0 auto;padding:28px 18px 80px}}.hero,.section{{background:#fff;border-radius:22px;box-shadow:0 10px 34px rgba(69,39,137,.08)}}.hero{{overflow:hidden}}.hero-grid{{display:grid;grid-template-columns:minmax(210px,320px) 1fr;gap:0}}.hero img{{width:100%;height:100%;min-height:260px;object-fit:cover}}.hero-copy{{padding:30px}}.eyebrow{{font-size:11px;font-weight:900;color:#7047ff;letter-spacing:.12em}}h1{{margin:8px 0 12px;font-size:34px;line-height:1.35;color:#28125f}}.lead{{margin:0;color:#665d73}}.meta{{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}}.pill{{padding:6px 10px;border-radius:999px;background:#f1ecff;color:#4c2aa5;font-size:12px;font-weight:800}}.compare{{display:inline-flex;margin-top:18px;padding:11px 15px;border-radius:11px;background:#7047ff;color:#fff;font-weight:900;text-decoration:none}}.section{{margin-top:20px;padding:24px}}.section h2{{margin:0 0 12px;color:#321568;font-size:23px}}.section p{{margin:10px 0}}.refs{{font-size:11px;color:#8c8495}}.progress{{padding:0;list-style:none}}.progress li{{padding:14px 0;border-top:1px solid #eee9f8}}.progress strong,.progress span,.progress a{{display:block}}.progress span{{margin:5px 0;color:#51485d}}.notice{{padding:13px 15px;border-radius:12px;background:#fff7d8;color:#5b4812;font-size:13px;font-weight:700}}.sources{{padding-left:20px}}.sources li{{margin:10px 0;overflow-wrap:anywhere}}.sources span,.sources a{{display:block}}.sources span{{font-size:12px;color:#655c70}}.sources a{{font-size:10px}}@media(max-width:700px){{.page{{padding:18px 13px 60px}}.hero-grid{{grid-template-columns:1fr}}.hero img{{min-height:0;aspect-ratio:16/9}}.hero-copy{{padding:22px}}h1{{font-size:27px}}.section{{padding:20px;border-radius:18px}}}}
</style>
</head>
<body>
<div data-poigame-header></div>
<script src="site-header.js"></script>
<main class="page" data-current-offers-game="{esc(game)}">
<section class="hero"><div class="hero-grid"><img src="{esc(image)}" alt="{esc(game)}"><div class="hero-copy"><div class="eyebrow">POIGAME LAB 攻略</div><h1>{esc(title)}</h1><p class="lead">{esc(guide["intro"])}</p><div class="meta"><span class="pill">達成目安 {esc(validated["days"])}</span><span class="pill">難易度 {esc(validated["difficulty"])}</span></div><a class="compare" href="{esc(compare)}">現在の案件を比較する</a></div></div></section>
<section class="section"><h2>このゲームの進め方</h2><p>{esc(guide["overview"])}</p><p><strong>攻略の軸：</strong>{esc(guide["tips"])}</p></section>
{''.join(sections)}
{progress_section}
<section class="section"><h2>調査した出典</h2><ul class="sources">{''.join(source_rows)}</ul></section>
</main>
<script src="site-footer.js"></script>
</body>
</html>
'''


def render_game(game, content_dir=CONTENT_DIR, root=ROOT):
    payload, _ = gate.load_for_game(game, content_dir)
    validated = gate.validate(payload, game, root=root, require_guide_file=False)
    target = Path(root) / validated["guidePath"]
    text = render_html(payload, validated)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    final = gate.validate(payload, game, root=root, require_guide_file=True)
    return {**final, "bytes": target.stat().st_size}


def render_all(content_dir=CONTENT_DIR, root=ROOT):
    content_dir = Path(content_dir)
    rows = []
    if not content_dir.exists():
        return rows
    for path in sorted(content_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        game = str(payload.get("game") or "").strip()
        if game and payload.get("publicationReady") is True:
            rows.append(render_game(game, content_dir=content_dir, root=root))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", default="")
    args = parser.parse_args()
    rows = [render_game(args.game)] if args.game else render_all()
    print(json.dumps({"rendered": len(rows), "guides": [x["guidePath"] for x in rows]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
