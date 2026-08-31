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
