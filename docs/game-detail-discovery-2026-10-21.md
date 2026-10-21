# ゲーム詳細ページの発見・canonical調査（2026-10-21）

起点：運営者がSearch Consoleで `https://poigamelab.com/game.html?game=Township` を検査した実測結果。
対象は最新main（`dc153b2`、PR #337マージ後）と本番サイト。過去のPR #330（内部リンクを初期HTMLへ）、#331、#335（検証済み案件のないゲーム）、#337（プライバシーポリシー）の内容は繰り返していない。

## 1. Search Consoleの実測から確実に言えること／言えないこと

| 実測 | 確実に言えること | 言えないこと |
|---|---|---|
| 通常検査：URLはGoogleに認識されていない／参照元サイトマップ・参照元ページなし | 2026-10-21時点で、Googleのインデックス側にこのURLの処理記録が無い。サイトマップに載せていないので「参照元サイトマップなし」は当然 | 「リンクが存在しない」ことは意味しない。Google公式ヘルプは「URL is unknown to Google＝GoogleがそのURLをまだ見ていない」と説明し、コミュニティガイドは未認識URLでは参照元欄が常に空になると説明している。発見されていない原因はこの画面だけでは特定できない |
| ライブテスト：取得成功・クロール許可・インデックス登録可能 | robots.txt・HTTPステータス・noindexは障害になっていない。Googleはこのページを取得できる | インデックスされること自体は保証されない |
| スクリーンショット：Townshipの比較情報（ワラウ22,540円、Lv81到達、OS別案件）が描画された | Googleのレンダラーは `game.html` のJavaScriptを実行し、ゲーム固有データ（CSV取得を含む）を描画できる | AdSense審査クローラーが同様に評価している証拠にはならない。AdSenseのクローラー（Mediapartners-Google）はGooglebotとは別のクローラーで、キャッシュだけ共有する（AdSenseヘルプ）。JavaScriptの扱いは公式に記載が無い |
| ユーザーが指定した正規URL：なし | ライブテストの「ユーザー指定の正規URL」欄に値が表示されなかった | 「Googleが描画後のcanonicalを見ていない」とは断定できない（4章） |

## 2. A．ゲーム詳細URLの発見（静的リンクの実態）

ビルド成果物（`deploy-pages.yml` と同じ手順：build → generated guides → thumbnails → patch → `inject_static_index_fallback.py`）と本番HTMLを、JavaScript実行前の `<a href>` で数えた（`<script>`内のテンプレートは除外）。

- `index.html`：26ゲーム全てへ静的リンク（1ゲーム3本、計78本）。`offers.html`：同じく26ゲーム・78本。`guides.html`：26ゲーム・26本。
- 本番の `guides.html` / `game.html` はmainと同一（差分0）。本番の `index.html` / `offers.html` は、リポジトリ原本にはJS用テンプレートしか無く、デプロイ時の `inject_static_index_fallback.py` が静的カードを埋め込む構造（原本grepで3件しか出ないのはこのため。本番では81／80件）。
- 全ページのヘッダー／フッターに `index.html`・`offers.html`・`guides.html` への静的リンクがあり、トップから `game.html` までは2クリック以内。
- 全リンクのURLは `encodeURIComponent` と同じ形式で、JSが設定するcanonicalと一致（不一致0）。`#comparison` はフラグメントなのでGoogleは別URLとして扱わない。
- 攻略記事（`township-lv70.html` を含む36ページ）のうち23ページが自ゲームの詳細ページへ静的リンクを持つ。残り13ページは持たない（うち3ページ＝インポッシブルカート・さる山温泉旅館・Sea Block 1010は、カタログ掲載ゲームだが、index／offers／guidesから静的リンクされている）。
- `sitemap.xml` に載っているのは42URL（トップ・固定ページ・攻略記事）で、ゲーム詳細は載っていなかった（本PRで追加を提案）。
- Googleのリンク発見条件は「`href` を持つ `<a>` 要素」（JavaScript SEOの基礎）。上記は全て満たす。

**結論：構造上、Googleが発見できない状態ではない。** 「未認識」の原因として、リンクの欠落・URL生成ミス・robots.txtの遮断は見つからなかった。

### 未認識になっている原因の候補（証拠の強さ順に整理）
1. **ハブページ（index／offers／guides）をGoogleがまだ再クロールしていない／クロール需要が低い**。静的リンクが入ったのはPR #330（2026-10-13）で、`township-lv70.html` 等の攻略記事にあるリンクは2026-09-25以前からある。サイト全体のクロール頻度が低い小規模・新しいサイトでは、数週間未発見でも珍しくない。→ ハブページ自体のインデックス状況で検証できる（6章の手順2）。
2. **クエリパラメータURLの優先度が低い**。Google公式は `key=value` 形式を許容しており、それ自体は問題ではない。ただしクロール優先度が低くなる可能性は排除できない（公式に断定する記述は無い）。
3. **サイトマップに載せていない**（弱いシグナルの不在。サイトマップは公式に「ヒントであり保証ではない」）。
4. 低確率：初期HTMLが全ゲーム共通のため、レンダリング前の重複判定で優先度が下がる。公式には裏付けが無く、証拠が無い限り原因とは言えない。

どれが原因かは、サーバーログの無いGitHub Pagesでは確定できない。6章のSearch Console操作で絞り込める。

## 3. query parameter URL構造の妥当性
Google公式（URL構造）はパラメータを `key=value` で表現することを認め、非ASCIIは `href` 内でパーセントエンコードすることを求めている。現在のURLはどちらも満たす。一方で「単語で読めるURL」「音訳／ハイフン区切り」を推奨しており、`game.html?game=Township` は最適ではないが、**URL構造の変更は禁止事項かつ現時点で不要**。

## 4. B．canonicalと初期HTML

### 現状（実機確認）
- 初期HTMLに `<link rel="canonical">`・`robots`・og:titleは無い。titleとdescriptionは全ゲーム共通。
- `applyGameSeo()`（`game.html`）が、`games.csv` と案件データ4種を取得した後に、title・description・canonical・og:*を同じタイミングで設定する。
- 本番相当のビルドをChromiumで開き、**robots.txtでDisallowされたサブリソースを遮断し**（`/data/comparison_candidate_queue.json` のみ該当、任意取得で失敗しても描画は継続）、ネットワークを低速化して計測した。Township／マジックジグソーパズル／Dice Dreamsとも、高速時は約0.2〜1.2秒、低速時（200KB/s・遅延300ms）は約4.2秒で、**canonical・title・descriptionは案件表示（bestReward）が出る約30〜130ms前に同時にDOMへ入る**。canonicalタグは1個のみ、`noindex` なし、JSエラー0。
- つまり、ライブテストのスクリーンショットに比較情報が描画されていた時点で、canonicalもDOMに入っていた可能性が高い（タイミング競合の可能性は低い）。ただし「Googleのレンダリング時点のDOM」自体は、この環境からは見えない。

### 「ユーザーが指定した正規URL：なし」の理由の可能性
- (a) Search Consoleのこの欄が、JavaScriptで追加されたcanonicalを反映しない（または取得HTMLのみから算出する）。公式ドキュメントでこの欄の算出元を明記した記述は見つからなかった。
- (b) JS注入canonicalはGoogleが読むが、この欄の表示が別タイミング／別基準。
- (c) レンダリング時にcanonicalが入らなかった（上記計測では再現せず、可能性は低い）。
- いずれも**運営者がライブテストの「テスト済みのページ → HTML」でレンダリング後HTMLに `rel="canonical"` があるか確認**すれば判別できる（6章の手順1）。
- Google公式（重複URLの統合）：canonicalはHTMLソースに入れ、JSで変更しないのが最善。「HTMLソースに入れられない場合は、HTMLには書かず、JavaScriptだけで設定する」とも明記されている。現在は後者に該当し、**公式の許容範囲**。
- **やってはいけない修正**：`game.html` の静的HTMLに `<link rel="canonical" href=".../game.html">` のような固定値を入れること。全ゲームが同一URLを指す誤ったシグナルになり、公式の「JSでcanonicalを別のURLへ変えない」にも反する。

### 初期HTMLが全ゲーム共通であることのSEO上のリスク
- Googleは200応答を全てレンダリングキューに入れる（公式）。レンダリングに遅延が出ることはあるが、「共通だから必ず失敗」とは言えない。
- 実リスクは (1) レンダリング待ちの遅れ、(2) AdSenseクローラーのJS対応が非公開、(3) ゲーム別本文の独自性。
- 独自性の実測（26ゲーム、描画後 `main` の文字数1,500〜2,700字）：ゲーム固有の説明・コツ・注記は約110〜580字で、残りは比較表・見方などの共通テンプレート。検証済み案件のない9ゲームは、案件注記と実プレイ記録の件数で約450〜580字。**これはSSGでは改善しない（描画方式ではなく本文量の問題）**。深さは攻略記事36本が担っている。

## 5. C．改善方法の比較

| 案 | SEO効果 | 毎日の案件更新 | 既存攻略・内部リンク | canonical | 維持コスト・リスク |
|---|---|---|---|---|---|
| 1. 現構造維持＋sitemapにゲーム詳細26URL追加（＋既存の静的リンク） | 発見のヒントを追加。canonicalの弱いシグナル（公式：サイトマップ掲載は弱いシグナル）。レンダリング遅延の解消はしない | 影響なし（`sitemap.xml` のみ） | 影響なし。内部リンクとURLが完全一致 | JS canonicalと一致（テストで固定） | 極小。新ゲーム追加時は手動追記（またはビルド時生成＝別途承認）。戻すのは1コミット |
| 2. ビルド時にゲーム別HTMLを生成（SSG相当） | 初期HTMLにゲーム別title/description/canonical/本文。最も強い | 日次の金額更新と同時に再生成が必要＝日次ワークフローとデプロイの結合が増える。取得失敗時に古い金額を静的HTMLへ焼き込まないための保護が必要 | 新URL設計が必要。全内部リンクの切替、`.github/` 変更（要承認） | 旧 `game.html?game=` と新URLの並存で重複・canonical再設計（一括変更に該当） | 数日規模。テスト・リンク切れ検査・sitemap・リダイレクト方針の更新。**現時点では未承認・未実装** |
| 3. 既存URLのまま初期HTMLだけ個別化 | — | — | — | — | **GitHub Pagesはクエリ文字列を無視して同じファイルを返すため不可能**。エッジでの書き換えは新サービス導入（禁止）。`game.html` 静的HTMLへの固定canonical追加は誤り（4章） |
| 3'. 動的生成のcanonicalタイミングを早める（`games.csv` 取得直後に設定） | 低〜中：案件データ4種の完了を待たずにcanonical/titleを設定できる。ただし上記計測ではすでに同時に設定されており、効果は実測では確認できない | 影響なし | 影響なし | 一致 | 小。`game.html` を触るため全26ページの回帰確認が必要。**今回は根拠が弱いため見送り** |

## 6. 推奨と運営者向けの確認手順

**SSGは現時点では不要（提案のみ）。** 理由：静的リンクは26/26揃い、ライブテストでJS描画に成功しており、「未認識」はまだ原因が特定できていない。SSGが必要かどうかは下の手順の結果で決める。

### 運営者がSearch Consoleでやること（最小）
1. **Townshipのライブテスト結果**で「テスト済みのページ → HTML」を開き、`rel="canonical"` と `<title>Township ポイ活案件の比較` が出ているか確認（出ていれば、「ユーザー指定の正規URL：なし」は表示上の問題で、JS canonicalはGoogleに届いている）。
2. **ハブページの状態**：`https://poigamelab.com/guides.html`・`https://poigamelab.com/offers.html`・`https://poigamelab.com/township-lv70.html` を通常のURL検査にかけ、「Google に登録されています」かどうかと最終クロール日を確認。サイトマップのレポートで取得ステータスと「検出されたページ数」（現在42、本PR反映後は68）も確認。
   - ハブページが未登録／最終クロールが古い → サイト全体のクロール需要の問題。ゲーム詳細だけの構造問題ではなく、SSGでは解決しない。
   - ハブページは登録済みなのに詳細URLだけ未認識 → パラメータURLの優先度の問題。サイトマップ追加と「インデックス登録をリクエスト」を試す。
3. Township・マジックジグソーパズル・Dice Dreamsの3URLで「インデックス登録をリクエスト」（1日の上限あり）。数日後に再度URL検査し、「ユーザー宣言の正規URL」「Googleが選択した正規URL」を確認。
4. 1〜2週間後に「ページ」レポートの「クロール済み - インデックス未登録」「検出 - インデックス未登録」「重複」の理由に `game.html?game=` が出ていないか確認。

### 本PRの範囲（Draft）
- `sitemap.xml`：`<!-- POIGAME_GAME_DETAIL_URLS_START/END -->` で囲んだ26URLを追加（内部リンク・JS canonicalと同一URL）。生成ガイド用の自動パッチ（`include_generated_guides.py`／`register_generated_guides.py`）が自分のマーカー範囲だけを書き換えるため、この範囲は保持される（実機で確認）。
- `tests/test_static_internal_links.py`：サイトマップのゲーム詳細URLが `games.csv` に実在し、`encodeURIComponent` 形式で、`guides.html` の静的リンクと一致し、`game.html` のcanonical生成式と同じ接頭辞であること、素の `game.html` を載せないことを固定。**一方向のテスト**にしたのは、新ゲームが自動追加された際にサイトマップ追記漏れでCIが赤くなるのを避けるため（追記漏れは本書の残課題として扱う）。
- 変更していないもの：26ゲームのURL構造、`game.html`、CSV、案件金額、日次更新・新ゲーム処理、`.github/`、広告コード、robots.txt。

### 想定リスク
- 近似ページの増加：26ページは約1,500〜2,700字のうち固有部分が少ない。インデックスされない／重複扱いになる可能性がある（その場合はSearch Consoleに表示されるだけで、AdSense審査には直結しない）。
- サイトマップの手動管理：新ゲーム追加時の追記漏れ。恒久対応はビルド時の自動生成だが、`build_public_site.py` またはデプロイ手順の変更になるため要承認。
- 公式がサイトマップを「ヒント」と位置づけているため、掲載しても即インデックスされるとは限らない。

## 7. AdSense再審査前に必須と考える修正
- **ゲーム詳細ページのSEO変更はAdSense再審査の必須条件ではない。** AdSenseクローラーは広告タグのあるページを個別に取得し、Googlebotとは別物。審査時のJavaScript処理は公式に未記載のため、「描画できている」とも「できていない」とも言えない。
- 審査で最も確実に読まれる静的コンテンツ（攻略記事36本、`guides.html`、`index.html`／`offers.html` の静的カード、運営者情報、プライバシーポリシー）は、すでにJavaScript実行前のHTMLに本文・リンクがある。
- 再審査前に実施を推奨するのは、前回の最終確認（`docs/adsense-final-check-2026-10-21.md`）のBレベル項目のみ：参考値のみ4ゲームの紹介リンク表示の運営判断、運営者情報の公開範囲、切れた外部引用リンク5件（本文は未編集）。
- 本調査の6章の手順1・2は、申請前の判断材料として有益だが、結果が悪くても申請を止める根拠にはならない（Search Consoleの未認識は、AdSenseの品質基準とは別の問題）。

## 8. 実施した確認
- 静的リンク監査（成果物ビルド、26ゲーム×index／offers／guides）：欠落0・エンコード不一致0。
- Chromiumによるrobots.txt遮断＋低速回線のレンダリング計測（3ゲーム×2条件）：canonical 1個、noindex無し、JSエラー0。
- 26ゲームの描画後本文量計測。
- pytest全体：main 62 failed / 1,376 passed → 本ブランチ 62 failed / 1,378 passed（失敗62件は既存、追加テスト2件は成功）。CI「Legacy collector regressions」相当：435 passed。
- `node tests/test_site_data_v24.js`／`test_site_health_v25.js`／`test_game_offer_summary.js`：成功。`validate_daily_publication.py`：valid（53行維持・退役0・API呼び出し0）。
- 負のテスト：サイトマップのURLを1文字変えるとテストが失敗することを確認。
- 実施していない確認：Search Consoleの実画面（運営者のみ）、AdSenseクローラーの挙動、iPhone Safari実機。

## 参考（Google公式）
- JavaScript SEOの基礎（canonical・リンク・レンダリングキュー）
- 重複URLの統合（canonicalシグナルの強さ）
- サイトマップの作成と送信（ヒントであり保証ではない）
- URL構造のベストプラクティス（パラメータ・パーセントエンコード）
- AdSenseクローラーについて（Mediapartners-Googleは別クローラー）
