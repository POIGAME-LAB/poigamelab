# AppDriver provider review contract

## Scope

AppDriver is registered as a reviewed offerwall provider identity for passive
presence detection only. This change does not authorize direct AppDriver
offerwall requests, campaign parsing, reward publication, source confirmation,
or comparison readiness.

The reviewed provider ID is `appdriver`. The currently recognized presence
hostname is `appdriver.jp`.

## Public evidence reviewed on 2026-09-03

Current AppDriver public pages describe a wall-type reward-ad product and an API
integration option:

- https://appdriver.jp/
- https://appdriver.jp/public/info/terms

A publicly accessible AppDriver integration guide also documents the web
OfferWall request shape:

- https://appdriver.jp/static/file/Reward_for_publisher_ver1.4_English.pdf

That guide shows the web OfferWall URL carrying `identifier` (described as a
UserID), `media_id`, and `digest`. The guide is older documentation and is not
used as evidence that the exact current production URL format is unchanged.
Instead, it is sufficient reason to avoid treating AppDriver's offerwall URL as
an anonymous public catalog.

## Retrieval contract

`config/offerwall_providers.json` fixes AppDriver to:

- `retrievalMode: presence_only`;
- `followExternalLinks: false`;
- `persist: provider_domain_only`;
- `requiresUserTrackingContext: true`.

The scheduled collector may map a passive first-party observation of
`appdriver.jp` to provider ID `appdriver`, but it must not request that
offerwall URL.

Only the normalized provider identity may reach review metadata. Path, query,
fragment, identifier, media ID, digest, and other tracking values are not
persisted.

## Publication boundary

An AppDriver presence signal:

- does not create or refresh an offer;
- does not infer a reward;
- does not infer OS or deadline;
- does not increment `standardConfirmed`;
- does not make `comparisonReady` true.

## Future upgrade gate

AppDriver must remain `presence_only` unless a separate reviewed change
establishes an official, permitted, non-user-specific evidence surface that can
bind current campaign identity, game, OS, reward unit, conditions, deadline,
freshness, and provider/publication fingerprints.

No such upgrade is part of this change.
