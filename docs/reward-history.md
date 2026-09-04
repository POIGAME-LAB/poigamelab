# Verified reward history

## Scope

POIGAME LAB records reward history only from verified rows in
`data/published_offers.csv`.

History starts with repository-reconstructable snapshots from 2026-08-31.
Earlier values are not invented.

## Grouping

History is grouped by:

- game
- point site
- platform

If multiple verified offer identities exist for the same game/site/platform in a
snapshot, the highest verified reward is recorded for that group.

This lets a site/platform history continue across offer-ID replacements without
treating tracking URLs as the identity of the trend.

## Storage

`data/offer_history.csv` contains:

- observedAt
- game
- site
- platform
- reward
- offerKey

`scripts/append_offer_history.py` runs after a successful scheduled direct
refresh. It appends a new snapshot only when the current verified
game/site/platform reward state differs from the latest stored snapshot.

An unchanged scheduled refresh does not grow the history file.

## Display

The game detail page shows two levels of trend information.

### Game-level best reward

For the selected OS filter:

- current highest verified reward
- change from the previous distinct highest reward
- percentage change
- comparison with the highest value that existed before the current value

If the current value exceeds the prior high, the UI can say the prior high was
updated by +N%.

If no current verified offer remains, the UI shows "現在掲載なし". The numeric
comparison may still represent the drop from the last verified maximum, but the
site does not present an ended offer as a zero-yen active offer.

### Site/platform trend cards

For each currently published point-site/platform group:

- current reward
- previous distinct reward
- previous-change amount and percentage
- prior historical high comparison
- recent distinct reward points

## Safety

Search snippets, offerwall presence, unverified candidates and legacy
`offers.csv` rows never enter reward history.

The history job runs only after the direct-refresh step succeeds. If history
generation fails, the workflow stops before committing the local refresh output.

The history file is included in the public Pages artifact, but approval
registries and internal review data remain excluded.
