# Point Income iPhone / Pythonista bootstrap

Point Income redirects GitHub Actions/cloud traffic to its official domestic-only
access-control page. The current workaround is a Japan-residential iPhone
capture of the public category-68 catalog.

## Confirmed public retrieval path

The public category page is:

`https://sp.pointi.jp/list.php?cat_no=68`

Its actual offer cards are loaded from:

`/ajax_load/load_list_site.php?page=N&cat_no=68&od=1`

The capture script opens the category once to establish the first-party session,
then walks numbered listing pages until an empty or repeated page appears.

## iPhone steps

1. Open `scripts/point-income-device-capture.py` in Pythonista.
2. Run it. There is no URL input or paste step.
3. Copy the text printed below `POINT_INCOME_BASE64`.
4. Send it back to ChatGPT, or paste it into the GitHub Actions workflow
   **Import Point Income device catalog**.

The payload contains only public offer data:

- public `/ad/<id>/` identity and URL
- title
- iOS / Android hint when present in the title
- currently displayed point amount
- 10pt = 1JPY normalization

It never outputs raw HTML, cookies, passwords, account IDs, or login state.

The importer keeps every row candidate-only and publication-disabled. It does
not claim that category 68 is exclusively games, so non-game app rows must still
be filtered/classified before POIGAME LAB publication.
