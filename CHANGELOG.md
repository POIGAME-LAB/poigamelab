# CHANGELOG

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
