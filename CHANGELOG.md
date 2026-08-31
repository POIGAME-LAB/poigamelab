# PHASE2_DATA_HEALTH_V25

- 自動更新の成功・一部取得・失敗・古さをサイト表示に反映。
- `data/refresh_status.json` と `config/refresh_policy.json` をブラウザ側で安全に読み取り、ゲーム別データ状態を判定。
- 取得失敗/部分取得時は「直前の検証済みデータを保持中」と明示し、古い値を最新値のように見せない。
- データ状況ページを旧候補CSV中心の表示から、検証済み案件・自動更新・例外キュー中心へ更新。
- 48時間を超えた自動更新結果は stale として注意表示。
- V25専用の鮮度/異常系JSテストを追加。

# CHANGELOG

## PHASE2 Site Bridge V24
- `data/published_offers.csv` をトップ/詳細ページの最優先データソースへ接続
- 検証済みゲームでは旧 `offers.csv` を混在させない merge policy を実装
- 自動収集OFFゲームのみ旧データを「参考」としてフォールバック
- 共通 `site-data.js` を追加し、quoted CSV / embedded comma / CRLF を安全に解析
- 自動検証済みバッジと最終更新日をUIへ表示
- 外部由来文字列をHTMLエスケープし、案件URLを http/https のみに制限
- V24フロントエンドテスト追加（CSV、merge、fallback、URL/HTML safety）

## PHASE2 Auto Refresh V23
- 日次GitHub Actions自動更新を追加
- `scripts/auto_refresh.py` を追加
- Township / きのこ伝説のみ自動更新ON
- 完全取得時のみゲーム単位スナップショット置換
- 劣化取得時は前回掲載を保持して成功分だけマージ
- collectionComplete / degradedReasons をCollector出力へ追加
- Publisher出力をatomic replace
- `collect_games.py` が子Collector失敗を正しく終了コードへ反映
- GitHub Actions concurrencyで重複実行を禁止
- 旧6時間候補Collector workflowを停止・historyへ退避

## PHASE3_TREND_DISCOVERY_V26
- 話題/新着ゲーム候補を自動発見する `scripts/discover_trending_games.py` を追加。
- X + 登録ポイントサイト検索を候補ソース化し、Gemini抽出後にPythonで正規化・重複排除・複数ソーススコアリング。
- 候補は `data/trend_candidates.json` / `data/trend_status.json` のみに保存し、ゲーム/案件の公開データは変更しない安全境界を固定。
- GitHub Actions `Discover trending games` を毎日07:07頃(JST)に追加。既存Secretsを再利用。


## V27 — PHASE3 research promotion
- Added deterministic, API-free trend candidate promotion into `data/research_queue.json`.
- Requires independent-source, confidence, score, and point-site-evidence gates.
- Known games/aliases are blocked from promotion; publication and game target files remain untouched.
- Trend workflow now commits the research queue alongside candidate-only outputs.

## V28 — PHASE3 quarantined collector bridge
- Promoted research candidates can now enter the existing strict offer collector/verifier without being added to `game_targets.json`.
- Research runs force `POIGAMELAB_PUBLISH_MODE=quarantine`; verified offers are saved under `data/research_results/` and never written to public offer data.
- Daily trend workflow researches at most one promoted game per run to cap API cost.
- Unicode-only game names now receive collision-resistant hashed result slugs.

## V29 — PHASE3 final adoption gate
- Added API-free `scripts/evaluate_research_adoption.py` to judge quarantined research before any public-data mutation.
- Adoption readiness requires a complete, non-degraded collection plus at least 2 strict verified offers from at least 2 registered point-site sources.
- Every accepted offer must retain the V20 exact same-offer identity/reward consistency checks; weaker legacy-style verification cannot pass.
- Output is candidate-only `data/adoption_candidates.json`; V29 never edits `games.csv`, `game_targets.json`, `offers.csv`, or `published_offers.csv`.
- Research queue now fingerprints evidence and preserves completed/failed state when evidence is unchanged, preventing repeated daily API research of the same candidate.

## V30 — PHASE 3 Production Adoption
- V29 `adoption_ready` games can now be promoted into `games.csv`, `config/game_targets.json`, and strict verified offers into `data/published_offers.csv`.
- Production adoption is API-free and re-runs the V29 deterministic gate immediately before writes.
- New games enter `refresh_policy.json` with scheduled refresh disabled, preventing an unknown-game API crawl from silently becoming a recurring cost.
- Adoption is idempotent; game/offer duplicates are not created on reruns.
- Workflow records `data/adoption_status.json` and commits production changes only after the final gate.

## V31 — PHASE 3 Integration Safety Audit
- Added an API-free, fail-closed audit after production adoption and before Git commit.
- Blocks commits on duplicate games/targets/offer keys, orphan published games, invalid URLs, incomplete adoption registry state, enabled refresh for newly adopted games, or offer-count mismatch.
- Made `data/research_results/` staging conditional so a no-research run cannot fail on a missing directory.
- Added integration/negative-path tests; no live API calls are used by the audit.

## V32 — Discovery Evidence Recovery
- Point-site search failure/zero-result now falls back to stable first-party listing pages for Warau and COINCOME.
- Fallback runs only when needed, avoiding duplicate Firecrawl spend on healthy searches.
- Diagnostics distinguish search failure from fallback recovery/failure.
- Research thresholds are unchanged; V32 improves evidence collection instead of weakening the gate.
