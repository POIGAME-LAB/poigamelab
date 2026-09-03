# SKYFLAG provider review contract

## Scope

SKYFLAG is registered as a reviewed offerwall provider identity for passive
presence detection only. This change does not authorize direct SKYFLAG
offerwall requests, campaign parsing, reward publication, source confirmation,
or comparison readiness.

The reviewed provider ID is `skyflag`. The currently recognized presence
hostname is `ow.skyflag.jp`.

## Public evidence reviewed on 2026-09-03

Current official public materials describe SKYFLAG as a reward monetization
platform with an OfferWall product:

- https://skyflag.info/monetize/
- https://skyflag.info/case-post/case-14/

The current case material describes API integration and optimization by user
segments. Public materials reviewed for this change do not establish a
documented anonymous campaign catalog suitable for unattended evidence
collection.

This contract deliberately does not claim that every SKYFLAG URL contains a
user identifier. The reason for `presence_only` is narrower: an anonymous,
stable public evidence surface has not been established.

## Retrieval contract

`config/offerwall_providers.json` fixes SKYFLAG to:

- `retrievalMode: presence_only`;
- `followExternalLinks: false`;
- `persist: provider_domain_only`;
- `anonymousPublicCatalogEstablished: false`.

The scheduled collector may map a passive first-party observation of
`ow.skyflag.jp` to provider ID `skyflag`, but it must not request that
offerwall URL.

Only the normalized provider identity may be persisted. External paths, query
strings, fragments, tracking values and provider-side rewards are not stored.

## Publication boundary

A SKYFLAG presence signal does not create or refresh an offer, infer a reward,
infer OS or deadline, increment `standardConfirmed`, or make
`comparisonReady` true.

## Future upgrade gate

SKYFLAG must remain `presence_only` unless a separately reviewed change
establishes an official, permitted, anonymous evidence surface that can bind
current campaign identity, game, OS, reward unit, conditions, deadline,
freshness and provider/publication fingerprints.

No such upgrade is part of this change.
