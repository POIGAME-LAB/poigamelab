# PHASE 1 — Township 最小実験

## 今日やること
Townshipだけで **Tavily検索 → Gemini抽出/検証 → JSON保存** を1本通します。
サイト表示やUIはまだ変更しません。

## 実行
`.env` がプロジェクト直下にあり、次の2行が設定済みであること。

- `GEMINI_API_KEY=...`
- `TAVILY_API_KEY=...`

VS Codeのターミナルで:

```bash
python3 scripts/phase1_township.py
```

成功すると `data/township_phase1_result.json` ができます。
APIキーは結果ファイルに保存されません。

## 判定ルール
- 90以上 + URL + 根拠URL + 金額 + 条件 → `auto_publish_ready: true`
- 曖昧 → 自動掲載せず再取得
- 低信頼 → 不採用
- 「全件を人間が確認」はしない

※この最小実験ではまだ `offers.csv` を自動更新しません。まず収集・検証の精度を確認します。

## 2026-08-30 耐障害アップデート
Geminiが混雑(HTTP 429/5xx)した場合は自動再試行し、別のFlashモデルへ自動切替します。Geminiが全候補で失敗しても、Tavilyの検索候補は `data/township_tavily_candidates.json` に必ず保存されます。
