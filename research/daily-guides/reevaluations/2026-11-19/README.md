# 2026-11-19 再評価（振り返り分析）

PR #351（2026-11-19）で候補178件から1本しか作れなかった件を、修正後の仕組みで調べ直した記録です。**記事でも公開データでもありません。**
`research/daily-guides/20*/` の外に置いているのは、日次バッチの検査対象に入れないためです。

- `reevaluation.json`：候補ごとの区分（B=条件確認済み・プレイヤー情報未確認、C=条件を確認できない、D=ゲーム以外）と読めた案件、読めなかった理由
- 解説：`docs/daily-guide-pipeline-fix-2026-11-19.md`
- 区分Aは0件。条件が確認できた上位6ゲームを検索して、独立した遊んだ人の記録が見つからなかったため。残りは未検索で「存在しない」の意味ではない。

再現（通常のRoutineは上限あり。この分析だけ上限を外した）：

```python
from scripts import daily_guide_triage as tri
# 2026-11-19の candidates.json（PR #351のブランチ）を置き、budget["maxRequests"]=400, budget["maxLookups"]=45 に上げて
# 候補ごとに tri.probe(item, budget, None, 0.7, True) を呼ぶ（約8分、リクエスト約200回）
```
