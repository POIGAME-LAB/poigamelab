# Point Income iPhone / Pythonista bootstrap

Point Income redirects GitHub Actions/cloud traffic to its official domestic-only
access-control page. Public category-68 retrieval therefore runs from a
Japan-residential iPhone/Pythonista session.

## Confirmed public retrieval path

The public category page is:

`https://sp.pointi.jp/list.php?cat_no=68`

Its actual offer cards are loaded from:

`/ajax_load/load_list_site.php?page=N&cat_no=68&od=1`

The capture script opens the category once to establish the first-party session,
then walks numbered listing pages until an empty or repeated page appears.

## One-time setup

Create a GitHub fine-grained personal access token with repository access limited
to `POIGAME-LAB/poigamelab` and repository permission **Actions: Read and write**.

On the first run of `scripts/point-income-device-capture.py`, paste that token
into the secure prompt. Pythonista stores it in the iOS Keychain. It is never
added to the captured payload or printed.

To replace the token later, run the script with `--clear-token` once, then run
it normally and enter the new token.

## Normal daily/manual run

After setup, the normal flow is one tap:

1. Open `scripts/point-income-device-capture.py` in Pythonista.
2. Press Run.
3. The script captures all category-68 pages, gzip-compresses the candidate-only
   public payload and dispatches **Import Point Income device catalog** directly.
4. GitHub Actions validates the payload, separates reviewed existing-game matches
   from unmatched app candidates, and persists all accepted outputs to
   Cloudflare R2 under `device/point-income/latest/` plus a dated archive.

No ChatGPT paste is required after setup.

The payload contains only public offer data:

- public `/ad/<id>/` identity and URL
- title
- iOS / Android hint when present in the title
- currently displayed point amount
- 10pt = 1JPY normalization

It never outputs raw HTML, cookies, passwords, account IDs, login state, or the
GitHub token.

The importer remains fail-closed: every row is candidate-only and publication is
disabled. Category 68 also contains non-game apps, so unmatched rows stay in a
review queue rather than being published automatically.

## Recovery mode

If GitHub dispatch fails, the script copies the compressed Base64 payload to the
clipboard as a recovery path. `--manual` forces this mode without dispatching.
