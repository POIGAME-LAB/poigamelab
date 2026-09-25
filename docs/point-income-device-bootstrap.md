# Point Income iPhone / Pythonista bootstrap

Point Income currently redirects GitHub Actions/cloud traffic to its official
"domestic only" access-control page. This temporary route lets a Japan-residential
iPhone collect **public offer identities only** so the catalog can be audited
without sending login state or personal data.

## iPhone steps

1. In Safari, open Point Income's current **app/game offer list** and copy that page URL.
2. Open `scripts/point-income-device-capture.py` in Pythonista.
3. Run it and paste the copied Point Income URL when prompted.
4. Copy the text printed under `POINT_INCOME_BASE64`.
5. Send that Base64 text back to ChatGPT, or paste it into the GitHub Actions
   workflow **Import Point Income device catalog**.

The capture follows explicit "next page" links up to 30 pages and outputs only
public `/ad/<id>/` identities. It does **not** output HTML, cookies, passwords,
account IDs, or login data.

Accepted payload shape:

```json
{
  "schemaVersion": 1,
  "source": "point_income",
  "sourceUrl": "https://pointi.jp/...",
  "pageCount": 1,
  "candidateOnly": true,
  "catalogCompleteClaim": false,
  "adIds": ["149843", "149388"],
  "count": 2
}
```

The importer always keeps the result candidate-only and never claims a complete
catalog. A later parser must verify each live offer's title, reward, OS and terms
before ranking/publication.
