# 既存ゲーム案件の厳格な日次公開レイヤー

## 対象と変更点

2026-09-28監査。Notion CONTROL ROOM確認後、最新main
`d9490388b413974b23db78c0496f77e227d3334c` から作業。
ブランチ: `feat/verified-existing-offer-publication`。
既存の毎日01:17 JSTの `daily_scan_review.py` 呼び出しを利用する。
Actions定義、収集先、実行時刻、対象ゲームの追加・変更は行っていない。

- `directRefreshNeverCreatesNewPublishedRows=true` は維持。direct単独では新規行を作らない。
- 日次hookに `verifiedExistingGameGate` を設置。候補JSONを公開入力にせず、
  同じ巡回の `inspect_detail` が返した公式詳細snapshotを独立したメモリ内レーンで渡す。
- games.csv収載、対象名・設定aliasの完全一致（限定したOS/案件注記のみ除去）、
  登録first-party、要求URL/最終URL/offer ID、OS、現行parser、金額/単位/円換算、
  条件・達成期限・StepUp合計、fingerprint、重複・矛盾・外部offerwallを検査。
- parserの既定 `publicationAuthorized=false` は許可ではない。明示した契約を
  独立検査した場合にだけ公開できる。外側candidate-only入力、比較候補、
  parser自体のcandidateOnly、未知契約、出典不足は保留する。候補フラグを書き換えない。
- 現在金額だけを先行変更していたモッピーのshortcutを撤去。
- 報酬と現在条件・期限を一緒に更新。同額でも確認日更新可。同一日の同一snapshotは無変更。
- COINCOME/アメフリは既存parserが既に抽出しているStepUp本文も補助fingerprint付きで渡す。
  取得処理・レート・legacy reward-only fingerprintは変更しない。
- 新規行は既存ゲームのみ。StepUp内訳がない「各ミッション達成」等の要約だけでは
  追加も更新も不可。モッピーの下流POINT GET型等は保留。
- 403/timeout/空・不明parser/明示終了も、この厳格レーンでは既存行を削除しない。
  atomic replace・同時更新検知を維持。公開CSVが巡回中に変わっていたら書き込まない。
- Pages前検証でも、新規行が当該gateの判定・行fingerprintと一致することを要求。

## サイト別レーン

「公開可能」は条件を満たすsnapshotを処理できるという意味であり、
本日の実サイトでの取得・更新成功を意味しない。

| レーン | サイト | 制約 |
| --- | --- | --- |
| 厳格検証後に公開可能 | ワラウ | 当日公式レート確認、完全StepUp・OS・期限が必要 |
| 厳格検証後に公開可能 | COINCOME | 円表示とStepUp合計、全文の条件内訳が必要 |
| 厳格検証後に公開可能 | ハピタス | タイトルの明示OSまたは既存の審査済offer-ID別OS、レート・合計照合 |
| 厳格検証後に公開可能 | アメフリ | 10pt=1円、現在円表示とStepUp合計・本文の一致 |
| 厳格検証後に公開可能 | モッピー | v3の自己完結した公式条件のみ。POINT GET等の下流依存・不完全StepUpは不可 |
| 厳格検証後に公開可能 | ポイントタウン、ECナビ | 明示OS・達成期限・非曖昧な金額が必要。OS/期限不足は保留 |
| candidate-only / 公開契約未対応 | MIKOSHI、げん玉、レシチャレ、Powl、トリマ、ニフティポイント、GMOポイント | 今回の公開allowlistに含めない。取得可否とは別の分類 |
| device-only | ちょびリッチ、ポイントインカム | クラウド巡回・ランキング・詳細fetchから除外。既存device取得/import経路は維持 |

## 状態の読み方

`data/comparison_refresh_status.json` の `sourceHealth` とActionsログに別々に出力する。

- `fetchSuccess` / `fetchFailed`: 同一巡回の共有HTTPリクエスト件数。取得成功だけでは案件確認成功ではない。
- `parseSuccess`: 既存ゲームの公式詳細について、parser成功した一意の案件ID数。
- `publicationEligible`: 全公開条件を通過した一意の案件数。同額・同日で書込み不要でも含む。
- `candidateOnly`: 公開可とならなかった解析済案件・新ゲーム候補の一意ID数。
- `deviceOnly`: 端末専用。クラウド取得0件を「取得失敗」と数えない。
- `state`: 上記の要約。部分成功では件数を併読する。

`standardConfirmed` は旧利用箇所互換のため残すが、fetch成功率として表示しない。
`daily_scan_review.json.existingPublication.decisions` に保留理由、出典identity、
evidence/row fingerprint、確認時刻、追加・更新判定を保持する（既存の非公開研究出力）。

## 検証結果と留保

- 新規53テスト通過: 金額更新、同額確認日、新規行、重複防止、candidate拒否、
  OS/円換算/ID/期限不足、誤ゲーム、未知ゲーム、alias衝突、矛盾、403/timeout保持、
  device通信0、StepUp課金条件保持、改ざん拒否、実CSV→Pages前gate。
- 関連オフライン回帰: 500 passed / 11 failed。
  比較した最新mainも同じ11件が失敗（447 passed / 11 failed）。追加失敗0。
  失敗は旧workflow文字列・古い設定/金額の固定期待値・旧ハピタスfixture等。
  全テスト成功とは扱わず、11件の既存課題は別途整理が必要。
- モッピーの旧テストは、危険なshortcutを期待する内容から「単独更新禁止」に変更。
  directテストの出力先漏れも修正し、候補/historyをtmp_pathに隔離した。
- 構文検査、`git diff --check`、Pages 130ファイルビルド、公開データ検証、
  Node V24 site-data / V25 site-healthは通過。
- 全体テストには実サイトに接続する検証が含まれ、端末専用サイトへのクラウド通信が
  安全チェックで停止された。そのテストは再試行せず、関連回帰はsocket接続を禁止して実施。
- 実サイトの本日報酬を使う本番巡回、本番Actions、main反映、pushは未実行。
  ブラウザ本体がないためPlaywrightの実ブラウザテストは未実行。HTML/CSS/JSは変更なし。
- `published_offers.csv`: 57 → 57件、SHA256
  `43365391b16dc9de8faa020b084969bda9670397057c15bd5afa4c81cff9634a` のまま。
  games.csv、公開記事・画像・URL・SEO・AdSense・Analytics・workflowは未変更。
- 旧commit `8659dfed8007239714f239674215c123198d9249` は元worktreeで保持。

## 反映前後の確認

1. bundleで同じcommitを別GitHub接続の作業ブランチへ取り込む（復元手順は成果物README）。
2. PRで差分・既存11失敗と本番未検証の留保を確認。ここでの成果物はmerge承認ではない。
3. 承認後の本番巡回では `sourceHealth` と `existingPublication` を照合し、
   fetch成功、公開保留、device-onlyを混同しない。
4. 公開後の金額・条件・OS、追加行、保持行を確認。未対応契約は手動レビューを維持。

API課金・外部AIは使用しない。この変更は新ゲーム自動掲載を有効にしない。
