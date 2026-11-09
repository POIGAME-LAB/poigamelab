#!/usr/bin/env python3
"""Build the three spec JSON files of the 2026-10-28 batch from the ChatGPT Work delivery.

    python research/new-guides/2026-10-28/tools/build_specs.py

Input : research/new-guides/2026-10-28/work-originals/<slug>/{article.md,experiences.json}
Output: research/new-guides/2026-10-28/<slug>.json  (spec for scripts/render_guide_from_spec.py)

The Work wording is kept as delivered. Every deviation is listed in CORRECTIONS below as an exact
``old -> new`` replacement (the build fails if ``old`` is not found exactly once), so the audit diff
between the delivery and the published text is reproducible. Nothing here touches games.csv,
data/published_offers.csv or any collector.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
sys.path.insert(0, str(HERE))
from md_to_spec import parse_article  # noqa: E402

CHECKED = "2026-10-28"

AMEFRI_GM = "https://www.amefri.net/detail/id/137656"
WARAU_GM_ANDROID = "https://www.warau.jp/contents/point/pointEntrance.php?point_id=206954&pl=pc_categoryService"
WARAU_BB_ANDROID = "https://www.warau.jp/contents/point/pointEntrance.php?point_id=207591&pl=pc_categoryService"
WARAU_BB_IOS = "https://www.warau.jp/contents/point/pointEntrance.php?point_id=207589&pl=pc_categoryService"
WARAU_HV_IOS = "https://www.warau.jp/contents/point/pointEntrance.php?point_id=205754&pl=pc_categoryService"

# ---------------------------------------------------------------------------------------------
# Corrections to the Work article text: (section id or "intro", old, new). ``old`` must match once.
# ---------------------------------------------------------------------------------------------
CORRECTIONS: dict[str, list[tuple[str, str, str]]] = {
    "grand-mafia": [
        # 期限: 「インストールから60日」「アメフリの調査受付も60日以内」を撤回し、案件ページの表記差を明記する。
        ("condition",
         "※案件の全体期限はインストールから60日以内。短い個別期限を優先してください。表中の「30分程度」「1日程度」などはポイントサイトが示す進行目安であり、成果期限や実プレイヤーの所要時間とは区別が必要です。[G2]",
         "※アメフリの案件ページでは、成果到達期限・成果調査受付期限は「インストールから60日以内」、未承認の問い合わせは「ポイントを貯める」ボタンのクリック日から60日以内、非承認理由の問い合わせは成果判定日から30日以内と、起算日の違う期限が別々に書かれています。詳しくは「成果反映の注意点」を確認してください。個別Stepの7日・15日・30日・60日を何日目から数えるかも、アメフリiOSの案件ページには明記が見当たりません。短い個別期限を優先して計画してください。表中の「30分程度」「1日程度」などはポイントサイトが示す進行目安であり、成果期限や実プレイヤーの所要時間とは区別が必要です。[G2]"),
        ("condition",
         "こちらは序盤の別荘9・17、Tier2・3までが7日以内で、アメフリiOSと期限も配分も違います。",
         "こちらは別荘9・17・21とTier2・3が7日以内で、期限はすべてインストール日から数える表記です。Tier4アンロックは30日以内の1条件のみで、アメフリiOSと期限も配分も違います。"),
        ("condition",
         "全12条件の表示合計です。必ず受け取れる金額や、課金を引いた利益ではありません。[G2][R2]",
         "全12条件の表示合計です。必ず受け取れる金額や、課金を引いた利益ではありません。対象OSはiOSで、App Storeでの掲載名は「ザ・グランドマフィア」です。[G2][G6][R2]"),
        ("tracking",
         "アメフリの調査受付も60日以内の記載があるため、最終日の達成後に時間を置きすぎないことが大切です。",
         ""),
        ("faq",
         "別アプリです。似た城育成型でも、",
         "別アプリです。App Storeでも別のアプリとして掲載されています。似た城育成型でも、"),
        ("faq",
         "特に30日・60日のT4は同じ到達対象で期限違いの条件が並んでいます。両方の付与判定を含め、参加時の条件が優先されます。",
         "特に30日・60日のT4は同じ到達対象で期限違いの条件が並んでおり、両方の報酬が必ず付与されるとは言えません。付与の扱いを含め、参加時の条件が優先されます。"),
        ("intro",
         "報酬・期限は2026年10月27日の確認内容で、開始時の案件画面が優先されます。",
         "報酬・期限は2026年10月27日に確認し、10月28日に期限の記載を再確認した内容です。開始時の案件画面が優先されます。"),
    ],
    "bingo-blitz": [
        ("intro",
         "現行のキョート・アルプス完走日数ではありません。",
         "現行コースの最終都市（Androidはキョート、iOSはアルプス）までの完走日数ではありません。"),
        ("intro",
         "ストアの年齢区分だけで利用可否を決めないでください。[B6]",
         "ストアの年齢区分（App Storeでは17+の表示）だけで利用可否を決めないでください。[B1][B6][B8]"),
        ("condition",
         "両方とも購入条件を含む表示合計で、無課金で全額受け取れる意味ではありません。[B2][B3][R1]",
         "両方とも購入条件を含む表示合計で、無課金で全額受け取れる意味ではありません。ワラウの広告主表記（Playtika Santa Monica）とApp Storeの提供元は一致しています。案件ボタンから先のストアIDまでは確認していません。[B2][B3][B8][R1]"),
        ("condition",
         "最終条件も85日以内のアルプスです。",
         "最終条件も85日以内のアルプス（5,900円相当）です。"),
        ("condition",
         "どちらの案件も確認時は10月31日までの増額表示がありました。",
         "どちらの案件も確認時は10月31日までの増額表示があり、通常表示はAndroidが21,600pt、iOSが15,200ptでした。上の最大額は増額後の数字で、10月31日以降は変わる可能性があります。"),
    ],
    "heroes-vs-crazy-wiggler": [
        ("condition",
         "期限はインストール日から起算して30日以内です。",
         "ワラウの広告主表記（IMIYOO）とApp Store掲載の提供元（IMIYOO PTE. LTD.）は一致しています。案件ボタンから先のストアIDまでは確認していません。[H1][H2]\n期限はインストール日から起算して30日以内です。"),
        ("condition",
         "ノーマル2・6・10の合計は**50円相当**。",
         "ノーマル2・6・10の合計は**50円相当**です。[H2]"),
    ],
}

# ---------------------------------------------------------------------------------------------
# Blocks added by the audit (not in the Work article): (section id, insert after text, [blocks]).
# ---------------------------------------------------------------------------------------------
INSERTIONS: dict[str, list[tuple[str, str, list[dict]]]] = {
    "grand-mafia": [
        ("condition", "※アメフリの案件ページでは", [
            {"t": "warning", "x": "T4（Tier4）の2条件に注意してください。Step11（30日以内）とStep12（60日以内）は、どちらも「いずれかのTier4隊員をアンロック」という同じ到達目標で、期限と報酬だけが違います。表の合計70,198円は12条件をすべて足した表示合計で、30日以内に達成したときに両方のStepが付与されるのか、片方だけなのかは、案件ページの記載から判断できません。両方の報酬が必ず受け取れるとは考えないでください。参考までに、T4の2条件（33,600円＋16,800円）を除いた10条件の表示合計は19,798円相当ですが、これも達成の保証ではありません。[G2]"},
        ]),
        ("tracking", "案件ごとに記帳方式が", [
            {"t": "h3", "x": "成果の期限と問い合わせ期限を分けて読む"},
            {"t": "p", "x": "アメフリの案件ページ（2026年10月28日・30日に再確認）では、成果到達期限が「インストールから60日以内」、成果調査受付期限も「インストールから60日以内」と記載されています。一方、審査中にならない・承認されない場合の問い合わせは、「ポイントを貯める」ボタンのクリック日から60日以内、非承認理由の問い合わせは成果判定日から30日以内です。[G2]"},
            {"t": "warning", "x": "成果の期限はインストール日、未承認の問い合わせ期限はクリック日が起点で、起算日が違います。Step12の60日条件のように期限ぎりぎりで達成すると、未反映の問い合わせ期限との差が小さくなります。最終日まで待たず、達成画面とユーザーIDをその日のうちに保存し、反映されなければ早めに問い合わせてください。取り扱いは案件ページとアメフリの案内が優先です。[G2]"},
            {"t": "p", "x": "個別Stepの「7日間」「15日間」「30日間」「60日間」を何日目から数えるかは、アメフリiOSの案件ページに明記が見当たりません。ワラウAndroidは「すべてインストール日から」と明記していますが、同じ数え方をアメフリiOSに当てはめず、迷う場合は最も早い起点（「ポイントを貯める」ボタンをクリックした日）から数えた計画にしてください。[G2][G3]"},
        ]),
    ],
    "bingo-blitz": [],
    "heroes-vs-crazy-wiggler": [],
}

# 太字の注意書きをコールアウトに変換する（文言は変えない）。(section id, 開始テキスト, 種別)
CALLOUTS: dict[str, list[tuple[str, str, str]]] = {
    "grand-mafia": [],
    "bingo-blitz": [
        ("late", "キョートやアルプスまでの十分な完走ペースは", "warning"),
    ],
    "heroes-vs-crazy-wiggler": [
        ("offer", "ノーマル2・6・10の合計は", "key"),
    ],
}

SOURCE_ADDITIONS: dict[str, list[dict]] = {
    "grand-mafia": [
        {"id": "G6", "label": "G6：App Store掲載情報・ザ・グランドマフィア（iOS）", "url": "https://apps.apple.com/jp/app/id1612013407", "after": "G5"},
    ],
    "bingo-blitz": [
        {"id": "B8", "label": "B8：App Store掲載情報・Bingo Blitz（iOS）", "url": "https://apps.apple.com/jp/app/id529996768", "after": "B7"},
    ],
    "heroes-vs-crazy-wiggler": [],
}

PER_GAME = {
    "grand-mafia": {
        "game": "ザ・グランドマフィア",
        "file": "grand-mafia-guide.html",
        "heroStats": [
            {"label": "表示合計（アメフリiOS・全12条件）", "value": "70,198円相当"},
            {"label": "実例：別荘17・Tier3", "value": "無課金6日（1人）"},
            {"label": "実例：監禁所25", "value": "22日・24日（課金あり）"},
        ],
        "offerLinks": [
            {"label": "アメフリ（iOS）｜ザ・グランドマフィアの案件ページ", "url": AMEFRI_GM},
            {"label": "ワラウ（Android）｜ザ・グランドマフィアの案件ページ（別コース）", "url": WARAU_GM_ANDROID},
        ],
        "context": {"href": AMEFRI_GM, "label": "アメフリ（iOS）の現在の案件ページを見る →"},
        "registry": {
            "title": "ザ・グランドマフィア ポイ活攻略",
            "description": "アメフリiOSの12条件（別荘・Tier・監禁所25・投資センター25）と、無課金の序盤例・課金ありの監禁所25の実例、成果期限とT4条件の注意点をまとめています。",
            "label": "別荘17・監禁所25の攻略を読む →",
        },
        "sourceNote": "最終確認：2026年10月27日（成果期限の記載は10月28日に再確認）。本文の[G番号]・[R番号]は上の資料に対応します。公開クチコミは自己申告で、後から変更・削除される可能性があります。",
        "experience": {
            "updatedAt": CHECKED,
            "intro": "公開資料の個別実例です。A〜Cはワラウの案件ページ（Android・別コース）に投稿されたクチコミ、Dは個人記事で、アメフリiOS案件の実例ではありません。OS・条件・支出が同一ではなく、平均値や達成保証ではありません。",
            "player_notes": {"B": ("無課金・前提知識なしと記載。", "Aと同じ7日でも進行に差がある。無課金・前提知識なしと記載。"),
                              "D": ("2025年12月記事の最初の記録だけ採用。", "2025年12月記事の最初の記録だけ採用（当時の案件・OSは不明）。")},
        },
    },
    "bingo-blitz": {
        "game": "Bingo Blitz",
        "file": "bingo-blitz-guide.html",
        "heroStats": [
            {"label": "最大額（Android・購入条件込み）", "value": "27,770円相当"},
            {"label": "最大額（iOS・購入条件込み）", "value": "17,770円相当"},
            {"label": "過去条件の実例", "value": "マイアミ3日ほか"},
        ],
        "offerLinks": [
            {"label": "ワラウ（Android）｜Bingo Blitzの案件ページ", "url": WARAU_BB_ANDROID},
            {"label": "ワラウ（iOS）｜Bingo Blitzの案件ページ（別コース）", "url": WARAU_BB_IOS},
        ],
        "context": {"href": WARAU_BB_ANDROID, "label": "ワラウ（Android）の現在の案件ページを見る →"},
        "registry": {
            "title": "Bingo Blitz ポイ活攻略",
            "description": "ワラウAndroid／iOSの条件の違い、都市クリアと写真交換、無料クレジットの管理、短期限と課金条件の注意点を、過去条件の実例とあわせてまとめています。",
            "label": "都市クリア・写真交換の攻略を読む →",
        },
        "sourceNote": "最終確認：2026年10月27日（案件条件は10月28日に再確認）。公開記録は本人の自己申告です。平均値や達成保証としては使用していません。本文の[B番号]・[R番号]は上の資料に対応します。",
        "experience": {
            "updatedAt": CHECKED,
            "footnote_append": "速い例だけを見ると「数日で全額達成」と誤解しやすいゲームです。過去の都市条件と現行条件を分けて読む必要があります。",
        },
    },
    "heroes-vs-crazy-wiggler": {
        "game": "Heroes vs Crazy Wiggler",
        "file": "heroes-vs-crazy-wiggler-guide.html",
        "heroStats": [
            {"label": "最大額（ワラウiOS・購入条件込み）", "value": "11,400円相当"},
            {"label": "ノーマル2・6・10の合計", "value": "50円相当"},
            {"label": "実例：ノーマル10", "value": "2日（ヘル70は未確認）"},
        ],
        "offerLinks": [
            {"label": "ワラウ（iOS）｜Heroes vs Crazy Wigglerの案件ページ", "url": WARAU_HV_IOS},
        ],
        "context": {"href": WARAU_HV_IOS, "label": "ワラウ（iOS）の現在の案件ページを見る →"},
        "registry": {
            "title": "Heroes vs Crazy Wiggler ポイ活攻略",
            "description": "ワラウiOSのノーマル・ハード・ヘルの条件、ノーマル10までの実例と撤退例、広告とダイヤの注意点、赤いダイヤ購入条件をまとめています。",
            "label": "ノーマル・ヘル条件の攻略を読む →",
        },
        "sourceNote": "最終確認：2026年10月27日（案件条件は10月28日に再確認）。公開実例は自己申告で、投稿後の更新や削除もあり得ます。本文の[H番号]・[R番号]は上の資料に対応します。",
        "experience": {
            "updatedAt": CHECKED,
            "footnote_append": "ハードで期限内に次の条件へ進めなかったというApp Storeレビューもあります。ノーマルの短期例だけから、後半も同じ速度で進められるとは言えません。",
            "milestone_labels": {("A", 1): "日付不明", ("C", 0): "2〜3日"},
        },
    },
}


def walk_strings(node):
    """Yield (container, key, string) for every string in a nested structure."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str):
                yield node, k, v
            else:
                yield from walk_strings(v)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                yield node, i, v
            else:
                yield from walk_strings(v)


def apply_correction(scope: object, old: str, new: str, label: str) -> None:
    hits = [(c, k) for c, k, s in walk_strings(scope) if old in s]
    total = sum(s.count(old) for _, _, s in walk_strings(scope))
    if len(hits) != 1 or total != 1:
        raise SystemExit(f"correction not unique ({total} matches): {label}: {old[:40]}")
    container, key = hits[0]
    container[key] = container[key].replace(old, new)


def convert_callout(blocks: list[dict], start: str, kind: str) -> None:
    hits = [b for b in blocks if b["t"] == "p" and b["x"].startswith(start)]
    if len(hits) != 1:
        raise SystemExit(f"callout target not unique: {start}")
    hits[0]["t"] = kind


def split_multiline(blocks: list[dict]) -> None:
    """A correction may put a line break inside a paragraph: split it into two paragraphs."""
    out = []
    for b in blocks:
        if b["t"] == "p" and "\n" in b["x"]:
            out += [{"t": "p", "x": part} for part in b["x"].split("\n")]
        else:
            out.append(b)
    blocks[:] = out


def build(slug: str) -> dict:
    cfg = PER_GAME[slug]
    art = parse_article(BATCH / "work-originals" / slug / "article.md")
    meta = art["meta"]
    sections = copy.deepcopy(art["sections"])
    for s in sections:
        if s["id"] == "offer":
            s["id"] = "condition"
    toc = [{"id": "condition" if t["id"] == "offer" else t["id"], "label": t["label"]} for t in art["toc"]]
    sections = [s for s in sections if s["id"] != "pace"]  # shown by the shared experience panel
    intro = list(art["intro"])
    bucket = {"intro": intro, **{s["id"]: s for s in sections}}
    for sid, old, new in CORRECTIONS[slug]:
        target = bucket[sid]
        apply_correction(target if sid == "intro" else target["blocks"], old, new, f"{slug}:{sid}")
        if sid != "intro":
            split_multiline(target["blocks"])
    for sid, after, new_blocks in INSERTIONS[slug]:
        blocks = bucket[sid]["blocks"]
        idx = [i for i, b in enumerate(blocks) if b["t"] == "p" and b["x"].startswith(after)]
        if len(idx) != 1:
            raise SystemExit(f"insertion anchor not unique: {slug}:{after}")
        blocks[idx[0] + 1 : idx[0] + 1] = copy.deepcopy(new_blocks)
    for sid, start, kind in CALLOUTS[slug]:
        convert_callout(bucket[sid if sid != "offer" else "condition"]["blocks"], start, kind)
    # drop paragraphs a correction emptied
    for s in sections:
        s["blocks"] = [b for b in s["blocks"] if not (b["t"] == "p" and not b["x"].strip())]

    sources = copy.deepcopy(art["sources"])
    for add in SOURCE_ADDITIONS[slug]:
        pos = next(i for i, s in enumerate(sources) if s["id"] == add["after"]) + 1
        sources.insert(pos, {k: v for k, v in add.items() if k != "after"})

    exp = json.loads((BATCH / "work-originals" / slug / "experiences.json").read_text(encoding="utf-8"))
    ecfg = cfg["experience"]
    exp["updatedAt"] = ecfg["updatedAt"]
    if "intro" in ecfg:
        exp["intro"] = ecfg["intro"]
    if "footnote_append" in ecfg:
        exp["footnote"] = exp["footnote"] + ecfg["footnote_append"]
    for pid, (old, new) in ecfg.get("player_notes", {}).items():
        player = next(p for p in exp["players"] if p["id"] == pid)
        apply_correction(player, old, new, f"{slug}:player {pid}")
    for (pid, idx), label in ecfg.get("milestone_labels", {}).items():
        player = next(p for p in exp["players"] if p["id"] == pid)
        player["milestones"][idx]["dayLabel"] = label
    exp["initialVisible"] = 4

    return {
        "slug": slug,
        "game": cfg["game"],
        "file": cfg["file"],
        "inlineMarkup": True,
        "title": meta["title"],
        "description": meta["description"],
        "lead": intro[0],
        "heroStats": cfg["heroStats"],
        "heroNote": " ".join(intro[1:]),
        "toc": toc,
        "sections": sections,
        "sources": sources,
        "sourceNote": cfg["sourceNote"],
        "offerLinks": cfg["offerLinks"],
        "context": cfg["context"],
        "registry": cfg["registry"],
        "experience": exp,
    }


def main() -> int:
    for slug in PER_GAME:
        spec = build(slug)
        out = BATCH / f"{slug}.json"
        out.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("wrote", out.relative_to(BATCH.parent.parent.parent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
