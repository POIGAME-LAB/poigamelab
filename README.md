# POIGAME LAB — PHASE 2 Data Health V25

V23でGitHub Actionsの日次自動更新が本番稼働したため、V24ではその**検証済みデータを実サイトへ直結**しました。


## V24: サイト表示への接続
- トップ/詳細ページは `data/published_offers.csv` を最優先で読む
- 自動検証済みデータがあるゲームは、旧 `offers.csv` の未確認値を混ぜない
- まだ自動収集OFFのゲームだけ `offers.csv` を参考データとしてフォールバック
- 「✓ 自動検証済み / 更新日」と「△ 参考データ」を表示で区別
- CSVの引用符・カンマを正しく扱う共通パーサー `site-data.js` を追加
- スクレイピング由来テキストのHTMLエスケープ、リンクの http/https 制限を追加

## 自動更新フロー
GitHub Actions → `scripts/auto_refresh.py` → ゲーム別Collector →
Python deterministic verifier → Publisher → `data/published_offers.csv`

対象は現在:
- Township
- きのこ伝説

メメントモリ / ワーキングヒーローは、公式案件URLの精度検証前なので自動更新OFFです。

## データ保護
- 完全取得: そのゲームの掲載スナップショットを最新状態へ置換
- 429/取得失敗などの劣化取得: 成功した新データだけマージし、前回の正しい行を消さない
- CSV/JSONは一時ファイルからatomic replace
- exact offer identity / reward consistency gateは維持
- Firecrawl同時通信は全体最大2
- GitHub Actions自体も同時実行1本

## GitHub Actions
`.github/workflows/refresh-verified-offers.yml`
- 手動実行可能
- 毎日 21:17 UTC（日本時間 06:17頃）
- Repository Secretsとして `FIRECRAWL_API_KEY` と `GEMINI_API_KEY` が必要
- APIキーをコードやZIPへ保存しない

旧6時間Collector workflowは `docs/history/collect-data.legacy.yml` へ退避済み。

## V25: データ鮮度・異常表示

サイトは `data/refresh_status.json` を参照し、ゲームごとの自動更新状態を `正常 / 一部取得できず / 更新失敗 / 更新待ち` として表示します。部分取得や一時障害では Publisher が以前の検証済み案件を保持し、UI側もその状態を明示します。`config/refresh_policy.json` の `staleAfterHours`（既定48時間）を超えると更新待ち表示になります。

## V26: PHASE 3 話題ゲーム候補の自動発見

`Discover trending games` が毎日07:07頃(JST)に、X検索結果と登録ポイントサイトのゲーム案件検索から新規ゲーム名候補を収集します。Firecrawlは検索結果取得、Geminiはゲーム名候補の抽出だけを担当し、PythonがURL正規化・重複排除・複数ソースのスコアリングを行います。

**安全境界:** V26は候補発見専用です。`games.csv`、`offers.csv`、`data/published_offers.csv` を自動変更しません。出力は `data/trend_candidates.json` と `data/trend_status.json` のみです。既知ゲームは新規候補から区別されます。


## PHASE 3 V27 research promotion
Strong V26 trend candidates are deterministically promoted to `data/research_queue.json` only when score/confidence/source-count thresholds pass and point-site evidence exists. This stage makes zero API calls and never edits publication data or `game_targets.json`.

## PHASE 3 V28 research collector bridge
`collector_ready` candidates can be researched automatically with the existing Firecrawl + Gemini + deterministic verifier pipeline. V28 is deliberately quarantined: it does not add the game to `game_targets.json` and does not update `data/published_offers.csv`. At most one promoted game is researched per daily trend run; results are stored in `data/research_results/` for the next publication-decision stage.

### PHASE 3 V29: final adoption gate
`python scripts/evaluate_research_adoption.py` evaluates quarantined V28 research with zero API calls. A game becomes `adoption_ready` only after complete/non-degraded collection and multiple strict same-identity verified offers across multiple registered point sites. V29 still does not publish or add games automatically. Unchanged already-researched candidates retain their state so the daily trend workflow does not spend API calls researching them again.

### PHASE 3 V30 production adoption
`python scripts/adopt_verified_games.py` consumes only V29 `adoption_ready` decisions. It revalidates the quarantined collector result without API calls, adds the game to the catalog/target registry, and merges only strict verified offers into the canonical published CSV. Newly adopted games are intentionally added to the refresh policy with `enabled: false`; recurring unknown-game crawling is a separate controlled policy decision.

### PHASE 3 V31 safety audit
The trend workflow runs `scripts/audit_phase3_pipeline.py` after V30 adoption and before committing. The audit is API-free and fail-closed: inconsistent production state stops the workflow before Git writes are pushed. `data/research_results/` is staged only when present.
