#!/usr/bin/env python3
"""Build publication-gated new-game guide packages from quarantined research.

Gemini is used only for bounded synthesis. Python re-validates every source
reference and every numeric token in guide/progress/catalog text against the
directly fetched source evidence. A neutral POIGAME LAB title-card SVG is
generated locally, so unattended runs do not need a third-party image API or
unlicensed game artwork. Nothing is published or committed here.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import unicodedata
from pathlib import Path

import new_game_content_gate as gate
from extract_guide_claims import live_gemini

ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = ROOT / "data" / "new_game_channel_research"
PACKAGE_DIR = ROOT / "data" / "new_game_content_packages"
STATUS = ROOT / "data" / "new_game_content_package_status.json"
MODEL = "gemini-3.5-flash-lite"
SOCIAL_CHANNELS = {"x", "youtube", "instagram"}


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def numbers(text):
    value = unicodedata.normalize("NFKC", str(text or ""))
    return [x.replace(",", "") for x in re.findall(r"\d+(?:[.,]\d+)?", value)]


def numeric_grounded(text, evidence):
    available = numbers(evidence)
    required = numbers(text)
    for token in set(required):
        if available.count(token) < required.count(token):
            return False
    return True


def source_rows(research):
    rows = {}
    lanes = research.get("research") if isinstance(research, dict) else {}
    for channel in gate.REQUIRED_CHANNELS:
        lane = (lanes or {}).get(channel) or {}
        if lane.get("searched") is not True or lane.get("complete") is not True:
            raise gate.ContentHold(f"research_channel_incomplete:{channel}")
        for row in lane.get("sources") or []:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("id") or "").strip()
            url = str(row.get("url") or "").strip()
            if not sid or sid in rows or not gate.safe_https(url):
                raise gate.ContentHold("research_source_identity_invalid")
            evidence = str(row.get("excerpt") or row.get("claim") or "").strip()
            rows[sid] = {**row, "id": sid, "channel": channel, "evidenceText": evidence}
    return rows


def synthesis_prompt(game, rows):
    compact = []
    for sid, row in rows.items():
        text = str(row.get("evidenceText") or "").strip()
        if not text:
            continue
        compact.append({
            "sourceId": sid,
            "channel": row.get("channel"),
            "text": text[:1400],
        })
    return f'''POIGAME LABの新規ゲーム攻略記事を構造化する。対象ゲーム: {game}

以下のsourcesだけを根拠にする。一般知識・推測・検索スニペット・別ゲーム情報は禁止。
事実を含む文には必ずsourceRefsを付ける。数字・レベル・日数・金額を出す場合、その数字が参照元text内に存在するものだけ使う。
「みんなの進捗」は x / youtube / instagram の公開プレイヤー記録だけから作り、同一URLを重複させない。
根拠が足りない項目は捏造せず空にする。difficulty も根拠がある表現だけにする。

JSONのみ返す。
形式:
{{
 "days":"例: 7〜14日",
 "daysSourceRefs":["sourceId"],
 "difficulty":"例: 普通〜やや難",
 "difficultySourceRefs":["sourceId"],
 "guide":{{
   "title":"... ポイ活攻略",
   "overview":"...",
   "overviewSourceRefs":["sourceId"],
   "tips":"...",
   "tipsSourceRefs":["sourceId"],
   "sections":[
     {{"heading":"案件条件","text":"20文字以上","sourceRefs":["sourceId"]}},
     {{"heading":"達成ペース","text":"20文字以上","sourceRefs":["sourceId"]}},
     {{"heading":"攻略のポイント","text":"20文字以上","sourceRefs":["sourceId"]}}
   ]
 }},
 "progress":[{{"sourceRef":"sourceId","summary":"公開プレイヤーの進捗を短く要約"}}]
}}

sources:
''' + json.dumps(compact, ensure_ascii=False)


def evidence_for_refs(rows, refs, error):
    if not isinstance(refs, list) or not refs or any(str(ref) not in rows for ref in refs):
        raise gate.ContentHold(error)
    return " ".join(rows[str(ref)]["evidenceText"] for ref in refs)


def validate_synthesis(game, research, proposal):
    rows = source_rows(research)
    if not isinstance(proposal, dict):
        raise gate.ContentHold("synthesis_invalid")
    days = str(proposal.get("days") or "").strip()
    difficulty = str(proposal.get("difficulty") or "").strip()
    guide = proposal.get("guide")
    if not days or days == "調査中" or not difficulty or difficulty == "調査中" or not isinstance(guide, dict):
        raise gate.ContentHold("synthesis_catalog_incomplete")

    days_evidence = evidence_for_refs(rows, proposal.get("daysSourceRefs"), "synthesis_days_evidence_invalid")
    difficulty_evidence = evidence_for_refs(rows, proposal.get("difficultySourceRefs"), "synthesis_difficulty_evidence_invalid")
    if not numeric_grounded(days, days_evidence):
        raise gate.ContentHold("synthesis_days_numeric_ungrounded")
    if not numeric_grounded(difficulty, difficulty_evidence):
        raise gate.ContentHold("synthesis_difficulty_numeric_ungrounded")

    title = str(guide.get("title") or "").strip()
    overview = str(guide.get("overview") or "").strip()
    tips = str(guide.get("tips") or "").strip()
    if len(title) < 8 or len(overview) < 8 or len(tips) < 8:
        raise gate.ContentHold("synthesis_guide_summary_missing")
    overview_evidence = evidence_for_refs(rows, guide.get("overviewSourceRefs"), "synthesis_overview_evidence_invalid")
    tips_evidence = evidence_for_refs(rows, guide.get("tipsSourceRefs"), "synthesis_tips_evidence_invalid")
    if not numeric_grounded(overview, overview_evidence):
        raise gate.ContentHold("synthesis_overview_numeric_ungrounded")
    if not numeric_grounded(tips, tips_evidence):
        raise gate.ContentHold("synthesis_tips_numeric_ungrounded")

    # The intro is deliberately deterministic instead of free-form AI prose.
    normalized_guide = dict(guide)
    normalized_guide["title"] = title
    normalized_guide["intro"] = "ポイントサイトの案件情報と、直接確認できた公開攻略・進捗記録を根拠付きで整理しています。"
    normalized_guide["overview"] = overview
    normalized_guide["tips"] = tips

    sections = guide.get("sections")
    if not isinstance(sections, list) or len(sections) < 3:
        raise gate.ContentHold("synthesis_sections_incomplete")
    for section in sections:
        if not isinstance(section, dict):
            raise gate.ContentHold("synthesis_section_invalid")
        text = str(section.get("text") or "").strip()
        evidence = evidence_for_refs(rows, section.get("sourceRefs"), "synthesis_section_evidence_invalid")
        if len(text) < 20:
            raise gate.ContentHold("synthesis_section_evidence_invalid")
        if not numeric_grounded(text, evidence):
            raise gate.ContentHold("synthesis_section_numeric_ungrounded")

    progress_out = []
    seen = set()
    for row in proposal.get("progress") or []:
        if not isinstance(row, dict):
            continue
        ref = str(row.get("sourceRef") or "").strip()
        summary = str(row.get("summary") or "").strip()
        source = rows.get(ref)
        if not source or source.get("channel") not in SOCIAL_CHANNELS or len(summary) < 8:
            continue
        if not numeric_grounded(summary, source.get("evidenceText")):
            continue
        identity = f'{source.get("channel")}:{source.get("url")}'
        if identity in seen:
            continue
        seen.add(identity)
        progress_out.append({"identityKey": identity, "sourceRef": ref, "summary": summary})
    if not progress_out:
        raise gate.ContentHold("synthesis_progress_missing")

    return {
        "days": days,
        "difficulty": difficulty,
        "guide": normalized_guide,
        "progress": progress_out,
        "rows": rows,
    }


def neutral_svg(game):
    title = html.escape(str(game or ""))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675" role="img" aria-label="{title}">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6d4aff"/><stop offset="1" stop-color="#ff6fae"/></linearGradient></defs>
<rect width="1200" height="675" rx="56" fill="url(#g)"/>
<circle cx="1040" cy="115" r="190" fill="#fff" opacity=".10"/><circle cx="165" cy="610" r="250" fill="#fff" opacity=".08"/>
<text x="70" y="100" font-family="Arial,sans-serif" font-size="28" font-weight="700" fill="#fff" opacity=".92">POIGAME LAB</text>
<foreignObject x="70" y="175" width="1060" height="330"><div xmlns="http://www.w3.org/1999/xhtml" style="font-family:-apple-system,BlinkMacSystemFont,'Yu Gothic',sans-serif;font-weight:900;font-size:68px;line-height:1.22;color:white;display:flex;align-items:center;height:100%;word-break:break-word">{title}</div></foreignObject>
<text x="70" y="600" font-family="Arial,sans-serif" font-size="25" font-weight="700" fill="#fff" opacity=".9">ポイ活攻略・案件比較</text>
</svg>'''


def write_image(game, root=ROOT):
    slug = gate.safe_slug(game)
    relative = f"assets/game-art/{slug}-auto.svg"
    target = Path(root) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(neutral_svg(game), encoding="utf-8")
    return relative


def build_package(research, proposal, root=ROOT):
    game = str(research.get("game") or "").strip()
    checked = validate_synthesis(game, research, proposal)
    image_path = write_image(game, root=root)
    slug = gate.safe_slug(game)
    package = {
        "schemaVersion": 1,
        "game": game,
        "publicationReady": True,
        "research": research["research"],
        "guide": checked["guide"],
        "progress": checked["progress"],
        "image": {
            "path": image_path,
            "provenance": "generated",
            "rightsConfirmed": True,
            "note": "POIGAME LABがゲーム名だけから自動生成した独自タイトルカード。ゲーム公式素材は未使用。",
        },
        "guidePath": f"{slug}-guide.html",
        "days": checked["days"],
        "difficulty": checked["difficulty"],
        "sourceResearchPhase": research.get("phase"),
    }
    gate.validate(package, game, root=root, require_guide_file=False)
    return package


def run(research_dir=RESEARCH_DIR, package_dir=PACKAGE_DIR, root=ROOT,
        api_key=None, model=MODEL, synthesizer=live_gemini):
    api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY unavailable")
    outputs = []
    failures = []
    for path in sorted(Path(research_dir).glob("*.json"))[:5]:
        try:
            research = json.loads(path.read_text(encoding="utf-8"))
            if research.get("phase") != "NEW_GAME_MULTI_CHANNEL_RESEARCH_V1" or research.get("complete") is not True:
                raise gate.ContentHold("research_not_complete")
            rows = source_rows(research)
            proposal = synthesizer(api_key, model, synthesis_prompt(research.get("game"), rows))
            package = build_package(research, proposal, root=root)
            out = Path(package_dir) / f"{gate.safe_slug(package['game'])}.json"
            atomic_json(out, package)
            outputs.append(package)
        except Exception as exc:
            failures.append({"file": path.name, "error": str(exc)[:160]})
    status = {
        "phase": "NEW_GAME_CONTENT_PACKAGE_V1",
        "success": not failures,
        "games": len(outputs),
        "failed": len(failures),
        "failures": failures,
        "apiCalls": len(outputs) + len(failures),
        "publicationWrites": 0,
    }
    atomic_json(STATUS, status)
    return status


def main():
    status = run()
    print(json.dumps(status, ensure_ascii=False))
    return 0 if status["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
