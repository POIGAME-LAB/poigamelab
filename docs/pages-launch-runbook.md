# GitHub Pages launch runbook

## Current state

The repository is public and GitHub Pages has been enabled using GitHub Actions.

The deployment workflow in `.github/workflows/deploy-pages.yml` runs automatically after a push to `main` and can also be started manually with `workflow_dispatch`. Pull-request branches do not deploy.

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
- `robots.txt` and `sitemap.xml`.

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

## Deployment

Every merge to `main` now triggers the Pages deployment automatically. The workflow runs Python and frontend regressions before building and uploading the public artifact. Manual **Run workflow** remains available for an intentional redeploy.

## Custom domain

The production origin is `https://poigamelab.com`.

GitHub Pages is configured with `poigamelab.com` as the custom domain, and the
registrar DNS is configured with the four GitHub Pages apex A records plus a
`www` CNAME to `poigame-lab.github.io`.

The public artifact includes canonical/OG metadata for indexable static pages and
a production `sitemap.xml`. Pages that are intentionally noindex or dynamic
comparison shells are excluded from the sitemap.

Before submitting the sitemap to Search Console:

1. confirm public DNS propagation;
2. confirm GitHub Pages reports the DNS check as successful;
3. enable and verify HTTPS;
4. verify `https://poigamelab.com` and `https://www.poigamelab.com` resolve as intended;
5. then submit `https://poigamelab.com/sitemap.xml` to Search Console.

## Monetization boundary

The current published offer links are official destination URLs, not assumed
affiliate links. Do not invent referral or affiliate parameters.

Affiliate/advertising integrations should be added only after the actual
program/account identifiers and terms are known, with separate review from the
offer-verification logic.
