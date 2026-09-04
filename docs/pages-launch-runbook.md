# GitHub Pages launch runbook

## Current state

The repository is public and GitHub Pages has been enabled using GitHub Actions.

The deployment workflow in
`.github/workflows/deploy-pages.yml` is intentionally `workflow_dispatch`
only. It will not deploy from a pull request or from an ordinary push.

The workflow publishes an explicit `_site` allowlist built by
`scripts/build_public_site.py`; it does not upload the repository root.

## Public artifact boundary

The Pages artifact includes only the files needed by the public site:

- public HTML pages and shared JavaScript;
- public images and `assets/`;
- `games.csv`;
- `data/published_offers.csv`;
- `data/offer_history.csv`;
- `data/refresh_status.json`;
- `data/exception_queue.json`;
- `config/refresh_policy.json`;
- `robots.txt`.

It deliberately excludes repository internals such as:

- `.github/`;
- `docs/`;
- `scripts/`;
- `tests/`;
- approval/provider registries;
- research/trend candidate data;
- historical `offers.csv`.

Regression tests enforce this boundary.

## Pages configuration

GitHub Pages is configured to use **GitHub Actions** as the source. If this setting is ever reset, restore it under **Settings → Pages → Build and deployment → GitHub Actions** before running the deploy workflow.

## First deployment

After Pages is enabled:

1. Open **Actions**.
2. Select **Deploy POIGAME LAB to GitHub Pages**.
3. Choose **Run workflow** on `main`.
4. Review the pre-deploy regression result.
5. Read the deployment URL from the completed `github-pages` environment.

The workflow runs Python and frontend regressions before building and uploading
the public artifact.

## Custom domain

Do not add a `CNAME`, canonical URLs, or a production sitemap until the actual
custom domain and DNS target are confirmed.

After a custom domain is confirmed:

1. configure the domain in GitHub Pages and DNS;
2. verify HTTPS;
3. add the matching canonical/OG URLs;
4. add a sitemap using the exact production origin;
5. submit that sitemap to Search Console.

## Monetization boundary

The current published offer links are official destination URLs, not assumed
affiliate links. Do not invent referral or affiliate parameters.

Affiliate/advertising integrations should be added only after the actual
program/account identifiers and terms are known, with separate review from the
offer-verification logic.
