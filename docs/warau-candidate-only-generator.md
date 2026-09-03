# Warau candidate-only baseline generator

## Purpose

`scripts/generate_warau_baseline_candidates.py` is a read-only helper for
preparing the next reviewed Warau baseline enrollment.

It exists so a maintainer can collect the exact source fingerprints needed for
MementoMori and Whiteout Survival without running the publication refresh and
without writing any approval.

Default games:

- メメントモリ
- ホワイトアウト・サバイバル

## Safety boundary

The generator:

- reads `config/game_targets.json`;
- reads `config/point_sources.json`;
- reads `data/published_offers.csv`;
- requests only exact registered Warau first-party target URLs;
- parses them with the existing strict `warau-stepup-v1` parser;
- prints candidate JSON to stdout.

The generator does **not**:

- write `published_offers.csv`;
- write `config/approved_offer_baselines.json`;
- write `data/warau_baseline_candidates.json`;
- change `updatedAt`;
- create an offer;
- mark a candidate approved;
- dispatch a publication workflow.

Every generated candidate contains `approved: false`.

## Fail-closed checks

A candidate is emitted only when all of the following match exactly:

1. the target URL is on a registered Warau first-party host;
2. the offer identity is unique in published data;
3. the source parser returns `warau-stepup-v1` parsed evidence;
4. published and source offer IDs match;
5. published and source platform match;
6. published reward equals the parsed Warau point total;
7. the published row is already `verified: true`;
8. the parsed source contains StepUp evidence.

If any target fails, the top-level output is `complete: false` and the process
returns a non-zero exit status. Partial candidates remain explicitly unapproved
and must not be enrolled.

## Output

The stdout payload contains:

- `mode: candidate_only_read_only`;
- `complete`;
- requested games;
- candidate/failure counts;
- unapproved candidate records;
- sanitized failure reasons.

Each candidate binds:

- offer key;
- game/source identity;
- source URL;
- parser version;
- source evidence fingerprint;
- full published-row fingerprint;
- StepUp count;
- reward points;
- the reviewed Warau 1pt = 1 JPY conversion evidence URL.

## Review flow

A future bounded read-only run may be used to generate the four MementoMori /
Whiteout candidates. The resulting JSON still requires human review. Enrollment
into `config/approved_offer_baselines.json` is a separate explicit change and
must carry a fresh expiry window.

This PR intentionally does not perform that live source run.
