# PHASE 1 — Firecrawl実験版

目的は「ネット全体から適当にTownshipを探す」のをやめ、POIGAME LABに登録したポイントサイトだけを対象に案件を探すことです。

## 実行

既存の `.env` をこのフォルダ直下に置いた状態で、ターミナルから次を実行します。

```bash
python3 scripts/firecrawl_township_probe.py
```

必要なキー:

- `FIRECRAWL_API_KEY`
- `GEMINI_API_KEY`

Tavilyはこの実験では使いません。

## 今回の登録サイト

- モッピー
- ワラウ
- ちょびリッチ
- COINCOME

Firecrawlは各サイトについて、(1) 登録済みカテゴリ/入口URLの直接取得、(2) そのサイトのドメインだけに限定したTownship検索＋本文取得、の両方を試します。

## 出力

- `data/township_firecrawl_candidates.json` — Firecrawlが実際に取得したTownship候補とサイト別診断
- `data/township_firecrawl_result.json` — Gemini抽出＋掲載可否ゲートの結果

## 個人URLについて

Skyflag / AppDriver / Zucks / myChips / GF Rewards等の個人識別子付きURLはコードにも出力にも保存しません。今回判明したOfferwallは `config/point_sources.json` にドメイン名だけ記録しています。個別Offerwallの安全な自動発見は、親サイト収集が通った後の次バッチで実装します。
