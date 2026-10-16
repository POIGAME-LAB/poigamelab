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

## 追補（2026-10-16 ChatGPT監査を受けた再確認）

### 1. 運営情報のAI/API説明の訂正

初版の `about.html` は「日次の案件更新には外部の生成AIサービスやAPI課金型サービスを使用していません」と書いたが、
範囲の説明が不十分だった。コードとワークフローを再確認した結果:

| 工程 | 外部AI/APIの使用 | 根拠 |
| --- | --- | --- |
| 毎日の既存案件更新（`refresh-verified-offers.yml`、cron `17 16 * * *`＝01:17 JST） | **使用しない**。`daily_scan_review.py` とその推移的な import 9モジュールに Firecrawl/Gemini/Tavily の参照なし。ワークフローにもそれらのSecretsを渡していない | 静的解析（import閉包の全文検索）とワークフロー定義の確認 |
| `scripts/auto_refresh.py`（`FIRECRAWL_API_KEY`/`GEMINI_API_KEY` 必須） | 現行ワークフローからは**呼び出されていない**旧V23の入口。README.md の「自動更新フロー」はこの旧構成のまま（記述が古い） | `.github/workflows/*.yml` を検索しても参照なし。テストの deselect のみ |
| `research-new-game-content.yml`（日次更新成功後に自動起動） | `data/new_game_content_queue.json` の件数が0なら API 呼び出しなし（最新コミットの count は 0）。件数が1以上のときは Tavily / Gemini / Firecrawl を使用。リポジトリ変数 `ENABLE_NEW_GAME_CONTENT_RESEARCH` が `false` なら起動しない（変数の実値は未確認） | ワークフロー定義、`data/new_game_content_queue.json` |
| `publish-researched-new-games.yml` | 直近の実行は全て skipped。API呼び出しなし（`publish_top_five_content.py` は "No network or AI calls"）。`ENABLE_NEW_GAME_AUTO_PUBLISH` の実値は未確認 | 実行履歴、スクリプトの docstring |
| `discover-trending-games.yml` / `adopt-high-reward-games.yml` / `collect-guide-evidence.yml` | 手動実行のみ。Firecrawl/Gemini/Tavily を使用 | ワークフロー定義（`on: workflow_dispatch`）。discoverの最後の定期実行は 2026-09-16 |

Secrets・リポジトリ変数の実際の設定値は確認できない（権限なし）。`about.html` は「使う場合があります」と、確認できた範囲で書き直した。

### 2. 「（参考）は最高還元に含めていない」は誤りだった

`games.js` はカタログの参考値（`provisionalReward`）、`site-data.js` は旧 `offers.csv` の参考行を、検証済み案件のないゲームに限り
最高還元の欄に（参考／参考掲載ラベル付きで）表示する。トップの「掲載中の最高還元」の集計だけが検証済み金額のみ。
`about.html` と `game.html` の説明を実際の挙動に合わせて訂正した。

### 3. ゲーム詳細ページの再評価

- 初期HTML: 依然として全ゲーム共通の説明のみ（ゲーム固有情報はJS実行後）。
- JS実行後の本文量: 26ゲームで 約1,250〜3,000字（修正前）。検証済み案件のない9ゲームは約1,250〜1,450字で、固有の本文は概要1文と達成目安のみで薄い。
- 追加改善（安全な範囲）: 読み込んだ案件データだけから作る「比較サマリー」（件数・サイト数・還元額の幅・最高額の案件・OS別最高額・最新確認日）を追加。新しい数値や推測は作らない。
- 提案のみ: ゲームごとの静的ページ化（SSG相当）、検証済み案件のないゲームの扱い（noindex/統合）。
