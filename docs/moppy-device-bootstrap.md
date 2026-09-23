# Moppy iPhone bootstrap (temporary validation route)

This route is intentionally manual until a real residential-device payload proves that the public app catalog can be captured completely.

Expected JSON before Base64 encoding:

```json
{"siteIds":["160726","160688"]}
```

The production importer accepts only numeric IDs or official `https://pc.moppy.jp/ad/detail.php?site_id=...` URLs, removes duplicates, rejects fewer than 100 unique IDs, and marks accepted data candidate-only. It does not publish rewards or overwrite last-known-good data.

Do not send full HTML, cookies, login data, or account information.
