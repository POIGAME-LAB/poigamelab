# GF Rewards provider review contract

## Scope

GF Rewards is registered as the first reviewed offerwall provider identity for
POIGAME LAB. This registration enriches passive first-party presence observations
only. It does not authorize direct provider requests, offer parsing, reward
publication, source confirmation, or comparison readiness.

The reviewed provider ID is `gf_rewards`. The currently recognized presence
hostname is `ow-gf-rewards.com`.

## Official public evidence reviewed on 2026-09-03

GF Rewards' official public information site is:

- https://info.gf-rewards.com/
- https://info.gf-rewards.com/privacy.html

The official service description identifies GF Rewards as a performance-based
reward advertising network and explains that conversion points may include app
installs, registrations, purchases, event participation, and level completion.

The official privacy policy states that the service automatically acquires
CookieID to identify users who satisfy reward conditions. It also describes
sharing identifiers such as CookieID and advertising IDs with advertisers,
media operators, or measurement providers for reward-condition verification and
related purposes.

Because the offerwall can therefore operate in a user-tracking context,
POIGAME LAB does not treat an offerwall URL as an anonymous public evidence page.

## Retrieval contract

`config/offerwall_providers.json` fixes GF Rewards to:

- `retrievalMode: presence_only`;
- `followExternalLinks: false`;
- `persist: provider_domain_only`;
- `requiresUserTrackingContext: true`.

The direct refresh runner may map a passive observation of
`ow-gf-rewards.com` to provider ID `gf_rewards`, but it may not request that
hostname.

Review output may contain:

- provider ID: `gf_rewards`;
- provider name: `GF Rewards`;
- provider domain: `ow-gf-rewards.com`;
- retrieval mode: `presence_only`.

It must not contain the external path, query, fragment, CookieID, user ID,
tracking token, or a provider-side reward inferred from the link.

## Fail-closed registry validation

The provider registry rejects:

- duplicate provider IDs;
- duplicate presence domains;
- unsafe retrieval modes;
- `followExternalLinks: true`;
- persistence modes other than `provider_domain_only`;
- malformed provider/domain identities.

If the registry is malformed at runtime, provider enrichment is omitted. This
review-only metadata failure cannot promote or change publication data.

## Future upgrade gate

GF Rewards must remain `presence_only` unless a separate reviewed change
establishes an official, permitted evidence surface that is not dependent on a
user-specific tracking context, for example a documented public API or anonymous
static catalog.

Any future provider-specific parser must separately bind:

1. anonymous/current offer identity;
2. game title and OS;
3. reward unit and conversion;
4. all StepUp milestones and totals;
5. deadline origin;
6. complete conditions and exclusions;
7. source freshness;
8. provider/publication fingerprints;
9. explicit maintainer authorization.

No such upgrade is part of this change.
