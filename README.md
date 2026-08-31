# POIGAME LAB — PHASE 2 Auto Refresh V23

V22のライブ確認（きのこ伝説 23.6秒・6/6掲載・例外0）を受け、
検証済み案件の**日次自動更新**まで実装しました。

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
