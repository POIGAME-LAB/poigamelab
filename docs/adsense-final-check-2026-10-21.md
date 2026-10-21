# AdSense再審査前の最終確認（2026-10-21）

目的：公開済みのPR #331・#333・#335・#332（攻略10本）の内容を本番サイトとGoogle公式情報で検証し、再審査を申請してよいかを判定する。過去の調査は繰り返していない。**再審査は申請していない。** 本書の判定は「申請してよいか」の技術的な見立てで、AdSenseの合否を保証するものではない。

## 判定：B（軽微な修正後に申請を推奨）

| 区分 | 内容 |
|---|---|
| 修正すべき具体的な問題（1件） | プライバシーポリシーに、Google公式が求める広告Cookieの開示とオプトアウト案内が無い（本PRで修正案を提出） |
| 修正後に申請を妨げる重大な問題 | 本番で確認した範囲では見つからなかった |
| 確認できなかった項目 | Search ConsoleのURL検査（インデックス状況・Google選択canonical・レンダリング結果）。下記の理由で取得不可 |

Search Consoleが取得できないことだけを理由にC判定にはしていない。

## 1. Search Console（取得できなかった事実）
- Windsor.ai経由の読み取りを再試行：`searchconsole` に `sc-domain:poigamelab.com` は接続されているが、Windsor.aiの**無料プラン（接続1件まで）に対し6件が接続**されているため「読み取り停止」の偽のゼロ値（`0 clicks / 0 impressions`）が返る。**実データではないため使用していない。**
- Windsor.aiの検索パフォーマンス取得は「URL検査」（インデックス登録の有無・Google選択canonical・描画後HTML）を提供しない。**Googleがこれらのページをインデックスしているか・どのcanonicalを選んでいるか・JS描画結果を認識しているかは、確認できていない。推測もしない。**
- 運営者の最小操作（所要数分）：Search Console（プロパティ `poigamelab.com`）で、上部の検索欄に次の3URLを1つずつ入力して「URL検査」→結果と「公開URLをテスト」の「テスト済みページを表示」（HTML・スクリーンショット）を確認し、次の項目を教えてください。
  1. `https://poigamelab.com/game.html?game=Township`
  2. `https://poigamelab.com/game.html?game=%E3%83%9E%E3%82%B8%E3%83%83%E3%82%AF%E3%82%B8%E3%82%B0%E3%82%BD%E3%83%BC%E3%83%91%E3%82%BA%E3%83%AB`（マジックジグソーパズル）
  3. `https://poigamelab.com/game.html?game=Dice%20Dreams`
  - 見る項目：「URLはGoogleに登録されています／登録されていません」、「ユーザーが指定した正規URL」と「Googleが選択した正規URL」、「ページがクロールされた日時」、テスト済みHTMLに個別のtitle・本文が入っているか。
  - （任意）Windsor.aiの接続を5件解除すれば取得できるようになるが、他のサイトの接続も解除されるため推奨しない。

## 2. ゲーム詳細ページの3種（本番・2026-10-21）
| 項目 | Township（検証済み案件あり） | マジックジグソーパズル（参考値のみ） | Dice Dreams（検証済み案件なし） |
|---|---|---|---|
| JS実行前HTML | title「ゲーム詳細 \| POIGAME LAB」、description共通、h1「ポイ活ゲーム案件の詳細」、可視テキスト1,146文字。**3ページとも同一**。canonical・robots・og:titleはHTML上に無い | 同左 | 同左 |
| JS実行後 title | 「Township ポイ活案件の比較 \| POIGAME LAB」 | 「マジックジグソーパズル ポイ活案件の比較 \| …」 | 「Dice Dreams ポイ活案件の比較 \| …」 |
| JS実行後 description | ゲーム固有（「ポイントサイト2件の掲載枠…を比較」＝検証済み件数） | ゲーム固有（件数ではなく「確認状況をまとめています」） | 同左 |
| canonical / og:url | 自URL（`game.html?game=…`）1つのみ。HTMLとJSの矛盾なし | 同左 | 同左 |
| robots／noindex | robotsメタなし（インデックス可）。`X-Robots-Tag`ヘッダーなし | 同左 | 同左 |
| 表示内容 | 最高還元22,540円、比較サマリー、案件カード、攻略（township-lv70.html・progress.html?game=Township） | 最高還元「1,120円（参考）」、確認状況の説明、実プレイ記録「4件（完走4件）」、攻略記事リンク | 「検証済みの案件は未掲載」、確認状況の説明、実プレイ記録「8件（完走5／断念・未達2／挑戦中1）」、攻略記事リンク |
| 可視テキスト（描画後） | 約1,800字 | 約2,100字 | 約1,980字 |
| JSエラー／横スクロール | 0／なし（PC1280・スマホ390） | 同左 | 同左 |

- 取得失敗によるリクエスト失敗は、Google AnalyticsとAdSenseの計測ビーコン（`ERR_ABORTED`、ページ遷移時の中断）のみ。
- `data/comparison_candidate_queue.json` は `robots.txt` で拒否され本番も404だが、任意データとして読み込みを失敗させるだけで、描画には影響しない（JSエラー0）。ページの描画に必要なファイル（`games.csv`・`data/published_offers.csv`・`data/offer_history.csv`・`data/refresh_status.json`・`config/refresh_policy.json`・`data/guide-experiences/*.json`・各JS）は `robots.txt` で許可されている（Googleのrobots.txt仕様に従い、最長一致で評価）。

### Google公式の指針との照合（2026-10-21取得）
- JavaScript SEOの基礎：JSでtitle・descriptionを設定できる／canonicalはHTMLが最良だが、HTMLで指定できなければ「省略してJSだけで設定」してよい／HTMLにnoindexがあるとレンダリングを省略し得る／サーバー側または事前レンダリングは「依然として有効」。→ 現状はJSでの設定が公式に認められた範囲で、noindex・canonicalの矛盾はない。**初期HTMLが共通であることだけを理由に不合格・インデックス不可とは言えない**（Googleは200のページをレンダリングキューに入れる。ただしキューの待ち時間があり得る）。
- 結論：**ゲーム詳細の初期HTMLの共通化は「改善余地」であって、確認できた不具合ではない。** 静的ページ化（SSG）の必要性は、Search ConsoleのURL検査（上記3URL）の結果で判断すべき。結果が「登録されている・Google選択canonicalが自URL・テスト済みHTMLに個別内容がある」なら、SSGは不要または低優先。「登録されていない」「汎用titleで登録」等なら、別URL＋canonical設計のSSG（要承認）を提案する（影響範囲・リスクは `docs/adsense-review-2026-10-round3.md` §3-1）。

## 3. 残課題の確認結果
| 項目 | 結果 | 判定 |
|---|---|---|
| 検証済み案件のないゲーム詳細の有用性 | 9ゲームとも概要・達成目安・難易度・コツ・攻略記事リンクがあり、PR #335で確認状況の説明と実プレイ記録の件数内訳を追加済み。ページとしての中身はあるが、概要・コツは各約70〜100字と短く、価値の中心は攻略記事。Googleが低価値と見るかは確認不能 | 注意（致命的な問題は確認できず） |
| 参考値のみ4ゲームの紹介リンクと未検証報酬 | 「（参考）」と明示し「リンク未確認」。ただし未確認の金額の横に［PR］の登録リンク（rel=sponsored）が出る（マジックジグソー等）。Googleの公開ポリシー上、［PR］・sponsored付きのアフィリエイトリンク自体は禁止されていないが、未確認金額と並ぶと営利色が強く見える | 運営者判断（推奨：参考値のみの行では登録リンクを出さない） |
| 運営者情報 | about.htmlは運営方針・データの集め方・AI/自動化の利用・攻略の作り方・広告/アフィリエイト開示・免責まで記載。**運営者名・連絡先メールは無い**（お問い合わせはGoogleフォームとGitHub Issues）。Googleの「誰が作ったか」の観点では明示が望ましいが、公開情報にするかは運営者判断 | 注意（運営者判断） |
| お問い合わせ | Googleフォーム＋GitHub Issues。公開初期の窓口表記 | 問題なし |
| **プライバシーポリシー** | GA4の開示はあるが、**Google AdSenseについて「Googleを含む第三者配信事業者がCookieで過去のアクセスに基づく広告を配信する」旨と、広告設定／aboutads.infoでのオプトアウト案内が無い**。AdSenseヘルプ「Required content」とGoogle Publisher Policiesが求める開示 | **修正が必要（本PRで対応）** |
| 攻略の独自性と記録の根拠 | 攻略36記事＋実例JSON35ファイル・266人の記録。**全266件に出典URLあり**。完走189／断念・未達44／挑戦中・進行中33と成功例だけに偏らない。出典の上位はワラウ・X・ブログ。about.htmlで「推測の日数・架空の体験談は掲載しない」「運営者本人のプレイは記事内に明記」と方針を記載 | 問題なし |
| 表示不具合・リンク切れ | サイトマップ42URL全て200・リダイレクトなし。内部リンク89先（46ページ）で切れ0・存在しないアンカー0。外部リンク232件中217件が200、403/429（ボット拒否）10件は切れと断定せず。**404は4件**（`growth-route.com/poikatsu-king-shot/`＝kingshot記事、`web.mikoshi.jp/v2/skyflag/ads/33934`・`33937`＝rock-n-cash記事、`…/34282`＝slot-mate記事。終了した案件ページの引用元）、接続不可1件（`sepodi.com/mememori/`＝メメントモリ記事）。攻略記事の本文には手を入れていない | 軽微（出典リンク切れ5件。記事改変を避け報告のみ） |
| AdSenseコード | 広告コードは同一パブリッシャーID。about／contact／privacy／404／管理3ページ（noindex）には広告コードなし。広告枠（`ins`）の手動配置は0（自動広告のみ） | 問題なし |
| ads.txt | `google.com, pub-2224207953863103, DIRECT, f08c47fec0942fa0`。ページのIDと一致 | 問題なし |
| robots.txt | `Allow: /`、描画に必要なデータは許可、管理用ディレクトリは拒否、sitemap記載 | 問題なし |
| sitemap.xml | 42URL（トップ・運営情報・問い合わせ・プライバシー・攻略36・一覧など）。`game.html?game=…` は未掲載（設計上）。静的リンクは攻略一覧・トップ・案件一覧から発見可能 | 問題なし（ゲーム詳細の掲載は判断事項） |
| progress.html | 記録のある5ゲームのみ index,follow。初期HTMLは薄い（289文字）がJS描画後に実例を表示。広告コードあり | 注意（Search Console確認の対象に追加可） |

## 4. 本PRの変更（`privacy.html`のみ・本文の追記）
- 「広告配信（Google AdSense）について」を追加：①Googleを含む第三者配信事業者はCookieで過去のアクセスに基づく広告を配信、②Google広告Cookieにより、Googleやそのパートナーが当サイト・他サイトへのアクセスに基づき広告を表示でき、Cookie・ウェブビーコン・IPアドレスが設置・読み取りされる場合がある、③[Googleの広告設定](https://adssettings.google.com/)と[aboutads.info](https://optout.aboutads.info/)でのオプトアウト、④[Googleのデータ利用](https://policies.google.com/technologies/partner-sites?hl=ja)へのリンク。外部リンクは `rel="noopener"`。
- 「最終更新」を本変更の日付（2026年10月21日）に更新（制定日は2026年9月3日のまま）。
- 運営者へ：法的文面のため、内容をご確認ください。EEA／英国向けの同意管理（CMP）は本確認の対象外（日本語の日本向けサイトとして、対象は未評価）。
- テスト：`tests/test_public_site_build.py`（CIで実行）と `tests/test_adsense_quality_static.py` に開示文言・リンク・`noopener`・日付形式の検査を追加。

## 5. 申請前に推奨する順序
1. 本PRのレビューとマージ（プライバシーポリシー）。
2. Search ConsoleでURL検査（上記3URL）を実施し結果を共有。結果次第でSSGの要否を判断。
3. 運営者判断：参考値のみ4ゲームの紹介リンク表示、運営者情報（名義・連絡先）の公開方針。
4. 以上が完了した時点で、A判定として再審査を申請してよいか再確認。

## 6. テスト
- 全体pytest：main＝62 failed / 1,374 passed、本ブランチ＝62 failed / 1,376 passed（失敗の集合は同一）。
- CIステップ「Legacy collector regressions」再現：435 passed。node v24・v25・game_offer_summary 成功。ビルド＋公開前検証 valid。
- Chromium（PC1280／スマホ390）で `privacy.html` の横スクロールなし・JSエラー0・外部リンク4件が `noopener`。
- 未実施：iPhone Safari実機、Search Console。
