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
