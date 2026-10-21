# サイトマップのゲーム詳細URL自動更新：設計とテスト方針（2026-10-21）

状態：**設計のみ。実装していない。** 前提はPR #338（`sitemap.xml` にゲーム詳細26URLを固定で追加）。この文書は、新ゲームが公開されたときに、そのURLが自動でサイトマップへ入る仕組みの提案である。実装には運営者の承認が必要（5章）。

## 1. 現状の調査結果

### 1-1. 「公開済みのゲーム」の正本は `games.csv`
- 公開ページはすべて `games.csv` を唯一の正本として生成・参照している：`index.html`／`offers.html` の静的カード（`scripts/inject_static_index_fallback.py`）、`guides.html` の静的リンク、`game.html` のゲーム検索（`games.csv` に無い名前は noindex の「見つかりません」ページ）。
- 検証中・候補のゲームは別のデータにある（`data/new_game_candidate_queue.json`、`data/new_game_content_queue.json`、`config/game_targets.json` など）。`games.csv` に載るのは採用ゲートを通過した行だけ。`config/game_targets.json` は `games.csv` の部分集合（現在、`games.csv` のうち7ゲームは案件取得対象外）で、公開判定には使えない。
- したがって「公開済みだけを対象にする」「候補・検証中を誤登録しない」は、**`games.csv` の行だけを読めば満たされる**。候補（運営者が明示的に候補へ加えたFreecashを含む）はこの設計の対象外で、一切触らない。

### 1-2. `games.csv` を書き換える経路は複数ある
| 経路 | サイトマップも更新するか |
|---|---|
| `publish-researched-new-games.yml` → `publish_top_five_content.run()` → `v30.run()`（`games.csv` 追加）→ `register_generated_guides.run()`（攻略記事のサイトマップ更新）。`sitemap.xml` もコミット対象 | 攻略記事のURLのみ。**ゲーム詳細URLは入らない** |
| `adopt-high-reward-games.yml`（手動実行。コメントで「自動採用は保留中」）。`games.csv` をコミット対象にするが `sitemap.xml` は対象外 | 更新しない |
| `discover-trending-games.yml` → `adopt_verified_games.py` | 同上（コミット対象は `games.csv` を含まないファイル群） |
| 運営者による手動編集 | 手動 |

### 1-3. 再利用できる既存の仕組み
- **マーカー付きブロックの書き換え**：`register_generated_guides.patch_sitemap`（ソース側）と `include_generated_guides.patch_sitemap`（成果物側）は、`<!-- POIGAME_GENERATED_GUIDES_V1_START/END -->` の範囲だけを再生成し、それ以外の行（42URLと、PR #338の26URL）を保持する。マーカー不整合は例外で停止、書き込みは `atomic_text`（一時ファイル→置換）。今回この性質を実測で確認し、テストに固定した（PR #338）。
- **`--check` 付き同期スクリプトの前例**：`scripts/sync_static_guide_links.js --check`（`tests/test_static_internal_links.py` が呼ぶ）。
- **成果物側の後処理の前例**：`inject_static_index_fallback.py`（`_site/games.csv` を読んで `_site/index.html` に静的カードを埋め込む）。デプロイ手順に組み込み済み。
- **エンコード**：`inject_static_index_fallback.py` は `quote(name, safe='')`、JSのcanonicalは `encodeURIComponent`。両者は `-_.~` 以外のASCII記号（`!'()*`）の扱いだけが違うが、現在のカタログにこれらを含む名前は無い（全角括弧のみ）ので、現状は一致。**将来 `(` などを含む名前が来ると、静的リンク（`%28`）とcanonical（`(`）がずれる潜在リスク**がある。サイトマップ生成は `encodeURIComponent` と同じ文字集合を使い、同値性をテストで固定する（6章）。

## 2. 要件と設計の対応

| 要件 | 設計 |
|---|---|
| 公開済みのゲームだけ | `games.csv` の `name` 列（`strip()` 後に空でない行）。候補キュー・`game_targets.json` は読まない |
| 新規掲載でサイトマップにも自動追加 | `games.csv` からゲーム詳細ブロックを**全置換で再生成**（差分追記ではなく導出）。同じ入力から常に同じ出力になる＝冪等 |
| 重複登録しない | エンコード後URLの集合で重複排除。`games.csv` 内の同名行も1件にまとめる（`game.html` は先頭の一致を使う） |
| 非公開・検証中を誤登録しない | 上記1-1のとおり正本は `games.csv` のみ。URL自体が実在ゲームかを、`game.html` と同じ判定（`name` の完全一致）で検査する |
| 既存の攻略記事URLを消さない | 書き換えるのは専用マーカー `POIGAME_GAME_DETAIL_URLS_START/END` の内側のみ。それ以外の行は一切変更しない（既存の2つの自動パッチと同じ流儀） |
| 日本語のURLエンコード | `urllib.parse.quote(name, safe="-_.!~*'()")`＝`encodeURIComponent` と同じ。大文字16進、UTF-8。XML特殊文字は発生しない（`&` も `%26` になる） |
| GitHub Actions・日次更新を壊さない | 新規ワークフローを増やさない。日次更新（`refresh-verified-offers.yml`）は変更しない。下記3章の導線は、すでに `sitemap.xml` をコミット対象にしている新ゲーム公開ワークフローの中の関数呼び出しに限定 |
| API課金・新サービス不要 | 純粋なローカル処理（標準ライブラリのみ、API呼び出し0） |
| 追加漏れをテストで検出 | 6章。`games.csv` → サイトマップの**双方向**一致テストを、実際にCIで走るファイルに置く |

## 3. 推奨設計

### 3-1. 部品：`scripts/sitemap_game_urls.py`（新規・小さな単機能）
```text
game_detail_locs(games_csv)      -> 重複排除済みのURL一覧（games.csv の並び順）。nameヘッダー無し／0行なら例外（fail closed）
patch_block(sitemap_text, locs)  -> マーカー内側だけを置換した文字列。マーカー不整合は例外。無ければ </urlset> の直前に新設
write(sitemap_path, games_csv)   -> patch_block を atomic_text で書き込む。内容が変わらなければ書き込まない（不要な差分を作らない）
main(--check | --write)          -> --check はずれがあれば非0終了して差分を表示。--write は更新
```
- 取得失敗や空データを「ゲーム0件」と解釈しない：`games.csv` が読めない／`name` 列が無い／有効行0件のときは、**既存ブロックを触らず**例外で停止（AGENTS.md 4章に沿う）。
- 既存ブロックから一度に大量に消える変更（例：50%超の減少）は、`--allow-shrink` を付けない限り拒否する。`games.csv` の破損が公開サイトマップを空にするのを防ぐ。

### 3-2. 導線（ワークフローを編集せずに済む順）
1. **`register_generated_guides.run()` の末尾で `sitemap_game_urls.write(sitemap, root/"games.csv")` を呼ぶ**。`publish_top_five_content.run()` は `v30.run()` で `games.csv` を更新した**後**にこの関数を呼び、`publish-researched-new-games.yml` は既に `sitemap.xml` をコミット対象にしているため、**`.github/` を変更せずに**新ゲーム公開時にサイトマップが更新される。既存の `sitemap=` 引数（テスト用の差し替えパス）をそのまま使うので、既存テストの構造も保てる。
2. **成果物（`_site/sitemap.xml`）の最終整合は検査のみ**：`deploy-pages.yml` の「Pre-deploy public-site checks」で `python scripts/sitemap_game_urls.py --check --artifact _site`（読み取りのみ）を実行し、ずれを検出したらデプロイ前に失敗させる案。これは `.github/` の変更なので**要承認**。承認が得られない場合は、`tests/test_deploy_smoke.py`（既にデプロイ前に実行される）に同等の検査を足す案もある（`.github/` は不変だが、デプロイ停止の可能性があるため、リスクは同程度）。
3. **手動の `adopt-high-reward-games.yml`**：自動採用が保留中のため現時点では対応不要。再開する際に、`python scripts/sitemap_game_urls.py --write` を1行足して `sitemap.xml` をコミット対象に加える（要承認の `.github/` 変更。再開の判断と同時に行う）。

### 3-3. 採用しなかった案
| 案 | 見送り理由 |
|---|---|
| `build_public_site.py` で成果物のサイトマップだけを毎回生成 | すべてのビルド（日次更新を含む）に影響し、リポジトリの `sitemap.xml` と本番が乖離してレビューできなくなる。日次更新の経路を触る |
| `deploy-pages.yml` に生成ステップを追加 | `.github/` の変更が必須。本番だけ生成すると、リポジトリとの差分が見えない |
| `games.csv` の変更ごとに別ワークフローで再生成してコミット | 新規ワークフロー・書き込み権限が増える。本番書き込みの直列化（`poigamelab-production-writer`）との整合も要検討 |
| 動的サイトマップ（サーバー側生成） | GitHub Pagesでは不可。新サービスが必要 |
| 手動運用のまま | 追記漏れが起きる。テストで検出できるだけ（6章）で、予防にならない |

## 4. 想定リスクと対策

| リスク | 対策 |
|---|---|
| `register_generated_guides.run()` の副作用が増え、新ゲーム公開が失敗する | `write()` は失敗時に例外を出しても `sitemap.xml` を壊さない（一時ファイル→置換）。公開ワークフローのpytest（`test_generated_guide_registry.py` ほか）で事前に検証され、失敗はコミット前に止まる。公開自体を止めたくない場合は、サイトマップ更新の失敗を警告に落とす選択もあるが、**追加漏れを検出する6章のテストを併用**すること |
| 手動の `games.csv` 編集・他経路でサイトマップが追従しない | 6章の双方向テストがPRのCIで検出（`games.csv` 変更で起動するワークフローに含まれる）。直接pushされる経路は3-2の(2)のデプロイ前検査で最終防衛 |
| 上記ブロック以外を壊す | マーカー内側のみ置換。テストで「ブロック外の全行がバイト単位で不変」を確認 |
| `games.csv` から名前が消えたゲームのURLが残る | 全置換方式のため、次回の再生成で消える（`--check` が検出）。ゲーム削除時はサイトマップからも消えるのが正しい |
| 近似ページ（固有本文が少ない）が増える | URLを増やすだけで、`game.html` の本文は変えない。サイトマップはGoogle公式で「ヒント」。インデックスされるかはGoogleが決める |
| `encodeURIComponent` と Python `quote(safe="")` の記号差 | サイトマップは `encodeURIComponent` 準拠。静的カード生成側（`inject_static_index_fallback.py`）との同値性テストを追加し、将来のずれを検出（修正は別途） |

## 5. 実装に必要な変更（承認後）

| ファイル | 内容 | 規模 |
|---|---|---|
| `scripts/sitemap_game_urls.py`（新規） | 3-1の部品 | 約80行 |
| `scripts/register_generated_guides.py` | `run()` の末尾に1呼び出し | 数行 |
| `tests/test_sitemap_game_urls.py`（新規） | 6章の単体テスト | 約150行 |
| `tests/test_five_new_guides.py` | `games.csv` ⇔ サイトマップの双方向テスト（PR #338の一方向テストを置き換え） | 数十行 |
| `tests/test_generated_guide_registry.py` | 新ゲーム追加時にゲーム詳細URLが追加され、攻略記事URLが残る統合テスト | 数十行 |
| （任意・要承認）`.github/workflows/validate-five-new-guides.yml` | 新規テストファイルをpytest対象に追加 | 1行 |
| （任意・要承認）`.github/workflows/deploy-pages.yml` | デプロイ前に `--check` を追加 | 1行 |

**変更しないもの**：日次更新（`refresh-verified-offers.yml`、`daily_scan_review.py` など）、`v30` の採用ゲート、新ゲーム自動掲載のキュー生成（`write_new_game_content_queue.py`）、公開CSV、`games.csv`、URL構造、`game.html`。

## 6. テスト方針

### 6-1. CIで確実に走らせる配置
`tests/test_static_internal_links.py` はどのワークフローにも含まれておらずCIで走らない（今回確認）。そのため、サイトマップの検査は次のいずれかに置く：
- 既存で走るファイル：`tests/test_five_new_guides.py`（`validate-five-new-guides.yml`。`sitemap.xml`・`games.csv`・`guides.html` の変更で起動）、`tests/test_generated_guide_registry.py`（`publish-researched-new-games.yml` が公開前に実行）。
- 新規ファイルを足す場合は、上記ワークフローのpytest対象にそのファイルを加える（要承認）。ファイルを足しただけではCIで走らない点に注意。

### 6-2. テスト項目
**単体（`sitemap_game_urls`）**
1. 正常：日本語・英語・空白・コロン・全角記号・ハイフン付きの名前が `encodeURIComponent` と一致する（Nodeで計算した期待値、または固定テーブルと比較）。
2. 重複：`games.csv` の同名行、前後空白違いが1URLにまとまる。
3. 冪等：2回実行しても出力が同一、変更が無いときはファイルを書き換えない。
4. ブロック外不変：ブロック外の全行（42URL＋攻略記事＋生成ガイドのブロック）がバイト単位で不変。
5. 異常系：`games.csv` が無い／空／`name` 列が無い／BOM付き／0行→例外で停止し、`sitemap.xml` は変更されない。マーカーが片方だけ→例外。ブロックが無い場合は新設される。
6. 縮小ガード：行数が大きく減る入力は `--allow-shrink` が無ければ拒否。
7. XML：結果が有効なXMLで、`<loc>` に非ASCII・`&`・空白が無い。

**統合**
8. 新ゲーム追加：一時ディレクトリで `games.csv` に1行足して `register_generated_guides.run()` を実行 → ゲーム詳細URLが1件増え、既存の26URLと攻略記事URL、生成ガイドのブロックが残る。再実行しても重複しない。
9. `include_generated_guides.patch_sitemap`（成果物側）と併用してもゲーム詳細ブロックが保持される（PR #338で導入済み）。
10. 候補・未採用のゲーム（`games.csv` に無い名前）は、`new_game_candidate_queue` などに存在してもサイトマップに入らない（Freecashを含む候補データは入力にしない）。

**整合（追加漏れの検出＝双方向）**
11. `games.csv` の全ゲームがサイトマップにあり、サイトマップのゲーム詳細URLが全て `games.csv` にある（過不足なし）。
12. サイトマップのURL＝`guides.html` の静的リンク＝`game.html` のcanonical生成式（`encodeURIComponent(game.name)`）。さらに、静的カード生成（`inject_static_index_fallback.py`）の `quote(safe='')` との同値性。
13. 成果物検証：ビルド後の `_site/sitemap.xml` に、全ゲームURLと全ガイドURLが重複なく入っている。

### 6-3. 実装時の安全確認
- 実装前後で `pytest` 全体を最新mainと比較（失敗62件の集合が不変）。
- 「Legacy collector regressions」相当、`validate-five-new-guides` 相当、公開ワークフロー相当の各コマンドをローカル再現。
- `validate_daily_publication.py` が valid（公開案件行・退役件数が不変）。
- 負のテスト：URLの誤記、不正エンコード、重複、実在しないゲーム、マーカー欠落でテストが失敗することを確認。
- 実際の公開ワークフローの実行はしない（手動実行は運営者の承認が必要）。

## 7. 推奨する進め方
1. PR #338（26URLの固定追加）をまず確認・マージ。これだけで現在のカタログは完全にカバーされる。
2. 新ゲームの自動公開（`publish-researched-new-games.yml`）が実際に動く前に、3-2の(1)と6章を実装する。承認が出るまでは実装しない。
3. 3-2の(2)(3)（`.github/` 変更）は、1・2の実績を見てから別途判断する。
