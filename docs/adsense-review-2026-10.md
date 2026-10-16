# AdSense審査対応 記録（2026-10-16）

詳細な記録は Notion「POIGAME LAB｜AdSense審査改善」にあります（先に 00 を読む）。
このファイルは、同じ内容の要約をリポジトリ側に残すためのものです。Notionとこのファイルが食い違う場合はNotionの最新版を優先してください。

- Notion親ページ: https://app.notion.com/p/3fb664b9cf278153b8dcf0c0fe0d5429
- 00 ChatGPT引き継ぎ用まとめ: https://app.notion.com/p/3fb664b9cf2781f4badccd58660c897a
- 01 不承認原因の詳細調査: https://app.notion.com/p/3fb664b9cf278129ad49ea331dcd7ba0
- 02 修正履歴・変更したファイル: https://app.notion.com/p/3fb664b9cf2781589226dd2ffe270385
- 03 テスト・改善効果の検証: https://app.notion.com/p/3fb664b9cf2781e8ad5ef953174f3cf0
- 04 残課題・再審査の準備: https://app.notion.com/p/3fb664b9cf2781d099c6e9730cf23cc1
- GitHub PR: https://github.com/POIGAME-LAB/poigamelab/pull/331（実装コミット `29e8c72`）

## 位置づけ

- AdSenseの不承認理由は「有用性の低いコンテンツ」。具体的な原因はGoogleから示されておらず、**直接原因は確定していない**。
- 本PRは、確認できた事実（初期HTMLのプレースホルダー、運営情報の不足など）に対する改善であり、**AdSense合格を保証するものではない**。

## 確認できた事実（修正前、公開サイトを2026-10-16に取得）

| 項目 | 内容 |
| --- | --- |
| `game.html` 初期HTML | 見える本文 約530字。「ゲーム名」「読み込み中」×5「--- 円」。titleは全ゲーム共通 |
| `offers.html` 初期HTML | 見える本文 約198字。案件カード0件、「-- 件」 |
| `index.html` 初期HTML | 「最新案件データを読み込み中」×26、「確認中」×26 |
| JS実行後 | 案件データのない5ゲームで「--- 円」「調査中」を表示 |
| `about.html` | 916字。データの集め方・検証方法・更新日の読み方の説明なし。運営者名・連絡先メールなし |
| 攻略記事26本 | 本文 約2,000〜4,300字。記事間の類似度は平均0.02で水増しではない。著者・確認日の表示なし |
| 問題なし | HTTPS/転送、robots.txt、ads.txt、sitemap、canonical、Mediapartners-Google/GooglebotのUAでも200、内部リンク切れ0、スマホ横スクロールなし |

## 修正内容（PR #331）

- `scripts/inject_static_index_fallback.py`: `offers.html` の初期HTMLに games.csv の26ゲーム（還元額は出さない）を出力。トップの静的カードの「読み込み中」を概要文に置換。既存の `deploy-pages.yml` の呼び出しをそのまま利用（Actions変更なし）
- `offers.html` / `index.html` / `game.html`: 「読み込み中」「--- 円」「調査中」「攻略準備中」を中立の文言に統一。`game.html` に「この比較ページの見方」を追加し、ゲーム確定後に canonical / description / og を設定、存在しないゲームは noindex
- `about.html`: 案件の集め方と検証方法、更新日・（参考）の見方、攻略記事の作り方、訂正方針を追記（リポジトリ内docsの実際の仕様のみ）
- `tests/test_adsense_quality_static.py`: 新規6テスト
- 変更していないもの: `data/` `config/` `games.csv` `offers.csv` `.github/` 広告タグ GA4 紹介リンク

## 検証

- 全テスト: main 62 failed / 1,245 passed → PR 62 failed / 1,256 passed。失敗の集合は同一（既存課題）。
- `node tests/test_site_data_v24.js` / `test_site_health_v25.js`: PASS
- 本番と同じビルド手順の成果物を Chromium（PC 1280px / スマホ 390px）で13ページ確認: JSエラー0、横スクロール0
- 未実施: 本番での実表示確認、Search ConsoleのURL検査、PageSpeed、iPhone実機

## 注意（今後の作業者向け）

- `python -m pytest tests` を実行すると、追跡対象の `data/research_bridge_status.json` と `research/new-games/2026-09-27/*` が書き換わる。コミット前に `git status` で確認し、意図しない変更は `git checkout` で戻すこと。
- 既存テスト62件はmainでも失敗している（今回の変更とは無関係）。

## 未対応（許可・判断が必要）

1. ゲームごとの静的詳細ページ化（SSG相当。AGENTS.md §11 により明示許可が必要）
2. 運営者名・連絡先メールの公開（運営者の判断）
3. 攻略記事の著者・確認日・実プレイ記録の拡充（実際の記録のみ。架空は不可）
4. `progress.html` の扱い（1.とあわせて判断）
5. AdSenseタグの設置場所（運営者の判断）
