# Remaining comparison-source retrieval

## Scope

This change addresses the unattended retrieval entry points for MIKOSHI and
Gendama. It does not add or alter any published offer row, reward, OS, deadline,
approval, or comparison-ready decision.

## MIKOSHI

The public WEB MIKOSHI entry point currently exposes only a JavaScript-required
shell to direct HTML retrieval. The offer content needed for reliable unattended
listing/detail evidence is not present in that response.

Rather than add browser automation, proxying, or other access workarounds,
`scheduled_fetch_enabled` is set to `false` for MIKOSHI. Scheduled comparison
runs therefore make no MIKOSHI listing/detail request and leave existing
publication data untouched while recording the source as review-required.

Re-enabling scheduled MIKOSHI retrieval requires a separately reviewed, stable
and permitted evidence path.

## Gendama

The prior configured URL `/sp/service/object?i=free_now` no longer provides a
safe HTTPS listing path for the current fetch guard and can redirect toward an
HTTP welcome route.

The current public HTTPS welcome page is readable at:

`https://www.gendama.jp/welcome`

That page contains the current app/game area, and individual public offer links
use the stable detail form:

`/service/item/<numeric id>`

The source configuration therefore now:

- uses `https://www.gendama.jp/welcome` for both start and direct listing URL;
- recognizes `/service/item/` as a detail-link hint;
- keeps scheduled direct retrieval enabled;
- relies on the existing stable identity extraction for
  `/service/item/<numeric id>`.

This only repairs secure discovery. No current target-game offer identity was
established by this change, so no Gendama row is created or updated.

## Validation contract

Regression tests require exactly Chobirich and MIKOSHI to be explicitly disabled
among the six comparison sources. They also require Gendama's listing URL to be
HTTPS, the `/service/item/` hint to remain configured, the URL to pass the
first-party guard, and the numeric path ID to produce a stable offer identity.

No production collector/AI API call or live publication workflow dispatch is
part of this change.
