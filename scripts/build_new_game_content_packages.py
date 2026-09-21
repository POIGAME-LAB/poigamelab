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
根拠が足りない場合、days と difficulty は捏造せず「調査中」とする。その場合対応するSourceRefsは空配列にする。
sections は根拠のあるものだけ1〜3件返す。3件を無理に埋めない。progress は根拠が無ければ空配列でよい。

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


def repair_prompt(game, rows, reason):
    return synthesis_prompt(game, rows) + f"""

前回のJSONは検証で却下された。却下理由: {reason}
同じsourcesだけを使ってJSONを1回だけ修正する。
- sourceRefsは必ずsourcesに存在するsourceIdだけを使う。
- overview/tipsは根拠がある内容だけを書く。sectionsは根拠のあるものだけ1〜3件でよく、3件を無理に作らない。
- 数字を含む文は、その数字が参照先textに実際にある場合だけ使う。根拠がなければ数字を削る。
- days/difficultyの根拠がない場合は「調査中」、対応SourceRefsは空配列にする。
- progressはx/youtube/instagramの直接取得済みsourceだけを使う。存在しなければ空配列にする。
- 根拠不足を埋めるための一般知識や推測は禁止。
JSONのみ返す。
"""


def evidence_for_refs(rows, refs, error):
    if not isinstance(refs, list) or not refs or any(str(ref) not in rows for ref in refs):
        raise gate.ContentHold(error)
    return " ".join(rows[str(ref)]["evidenceText"] for ref in refs)


def _safe_refs(rows, refs):
    if not isinstance(refs, list):
        return []
    out = []
    seen = set()
    for ref in refs:
        sid = str(ref or "").strip()
        if sid in rows and sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def _grounded_text(rows, text, refs, min_len=8):
    value = str(text or "").strip()
    valid_refs = _safe_refs(rows, refs)
    if len(value) < min_len or not valid_refs:
        return "", []
    evidence = " ".join(rows[sid]["evidenceText"] for sid in valid_refs)
    if not numeric_grounded(value, evidence):
        return "", []
    return value, valid_refs


def validate_synthesis(game, research, proposal):
    rows = source_rows(research)
    if not isinstance(proposal, dict):
        raise gate.ContentHold("synthesis_invalid")

    point_refs = [
        sid for sid, row in rows.items()
        if row.get("channel") == "pointSites" and str(row.get("evidenceText") or "").strip()
    ]
    guide_refs = [
        sid for sid, row in rows.items()
        if row.get("channel") != "pointSites" and str(row.get("evidenceText") or "").strip()
    ]
    if not point_refs or not guide_refs:
        raise gate.ContentHold("insufficient_guide_research")

    raw_days = str(proposal.get("days") or "").strip()
    days = "調査中"
    if raw_days and raw_days != "調査中":
        refs = _safe_refs(rows, proposal.get("daysSourceRefs"))
        evidence = " ".join(rows[sid]["evidenceText"] for sid in refs)
        if refs and numeric_grounded(raw_days, evidence):
            days = raw_days

    raw_difficulty = str(proposal.get("difficulty") or "").strip()
    difficulty = "調査中"
    if raw_difficulty and raw_difficulty != "調査中":
        refs = _safe_refs(rows, proposal.get("difficultySourceRefs"))
        evidence = " ".join(rows[sid]["evidenceText"] for sid in refs)
        if refs and numeric_grounded(raw_difficulty, evidence):
            difficulty = raw_difficulty

    guide = proposal.get("guide") if isinstance(proposal.get("guide"), dict) else {}
    title = str(guide.get("title") or "").strip()
    if len(title) < 8:
        title = f"{game} ポイ活攻略"

    overview, overview_refs = _grounded_text(
        rows, guide.get("overview"), guide.get("overviewSourceRefs"), 8
    )
    if not overview:
        overview = f"{game}のポイ活案件について、掲載中のポイントサイト情報と直接確認できた公開情報だけを整理しています。"
        overview_refs = [point_refs[0], guide_refs[0]]

    tips, tips_refs = _grounded_text(
        rows, guide.get("tips"), guide.get("tipsSourceRefs"), 8
    )
    if not tips:
        tips = "案件を始める前に達成条件を確認し、公開情報で裏取りできた内容だけを参考に進めてください。"
        tips_refs = [point_refs[0]]

    sections_out = []
    for section in guide.get("sections") or []:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading") or "").strip()
        text, refs = _grounded_text(rows, section.get("text"), section.get("sourceRefs"), 20)
        if len(heading) < 2 or not text:
            continue
        sections_out.append({"heading": heading, "text": text, "sourceRefs": refs})
        if len(sections_out) >= 3:
            break

    if not sections_out:
        raise gate.ContentHold("synthesis_sections_incomplete")

    guide_used_refs = set(overview_refs) | set(tips_refs)
    for section in sections_out:
        guide_used_refs.update(section["sourceRefs"])
    if len(guide_used_refs) < 2:
        raise gate.ContentHold("synthesis_guide_source_diversity_insufficient")
    if not any(rows[sid].get("channel") != "pointSites" for sid in guide_used_refs):
        raise gate.ContentHold("synthesis_non_point_guide_source_missing")

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

    normalized_guide = {
        "title": title,
        "intro": "ポイントサイトの案件情報と、直接確認できた公開情報を根拠付きで整理しています。",
        "overview": overview,
        "overviewSourceRefs": overview_refs,
        "tips": tips,
        "tipsSourceRefs": tips_refs,
        "sections": sections_out,
    }
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
    holds = []
    failures = []
    api_calls = 0
    paths = sorted(Path(research_dir).glob("*.json"))[:5]
    for path in paths:
        try:
            research = json.loads(path.read_text(encoding="utf-8"))
            if research.get("phase") != "NEW_GAME_MULTI_CHANNEL_RESEARCH_V1" or research.get("complete") is not True:
                raise gate.ContentHold("research_not_complete")
            rows = source_rows(research)
            game = str(research.get("game") or "").strip()

            api_calls += 1
            proposal = synthesizer(api_key, model, synthesis_prompt(game, rows))
            try:
                package = build_package(research, proposal, root=root)
            except gate.ContentHold as first_hold:
                # A bounded second synthesis can repair formatting/grounding
                # mistakes without widening the evidence set. If the evidence
                # itself is insufficient, the second pass remains held.
                api_calls += 1
                repaired = synthesizer(
                    api_key, model, repair_prompt(game, rows, str(first_hold)[:160])
                )
                try:
                    package = build_package(research, repaired, root=root)
                except gate.ContentHold as second_hold:
                    holds.append({
                        "file": path.name,
                        "reason": str(second_hold)[:160],
                        "initialReason": str(first_hold)[:160],
                        "repairAttempted": True,
                    })
                    continue

            out = Path(package_dir) / f"{gate.safe_slug(package['game'])}.json"
            atomic_json(out, package)
            outputs.append(package)
        except gate.ContentHold as exc:
            # Research-level evidence holds cannot be repaired by synthesis.
            holds.append({
                "file": path.name,
                "reason": str(exc)[:160],
                "repairAttempted": False,
            })
        except Exception as exc:
            # Infrastructure/API/programming failures are not evidence holds.
            # Keep failing the workflow so an operational problem is visible.
            failures.append({
                "file": path.name,
                "error": type(exc).__name__,
                "detail": str(exc)[:160],
            })
    status = {
        "phase": "NEW_GAME_CONTENT_PACKAGE_V1",
        "success": not failures,
        "allReady": not holds and not failures,
        "selected": len(paths),
        "games": len(outputs),
        "held": len(holds),
        "holds": holds,
        "failed": len(failures),
        "failures": failures,
        "apiCalls": api_calls,
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
