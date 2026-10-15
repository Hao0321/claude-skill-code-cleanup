# External-change detail card

## Applicability

Use for authorized external mutation: create, publish, rename, transfer, archive, delete, deploy or rotate. Local design, URL review and updater discovery omit it. Provider recovery or destructive deduplication additionally need `../external-change-gates.md`, available through legacy fallback.

## Rules

- `rd.external.detail-target-resolution`: inventory namespace/aliases; bind account, owner, service/region, stable ID, canonical survivor, target and rejected alternatives. A guessed 404 proves no absence.
- `rd.external.detail-authorization`: distinguish user authority from live scope, role, payment, sudo/2FA and interaction surface. One target or reversible write grants no other target, persistence, publication or deletion.
- `rd.external.detail-postconditions`: preview the smallest delta, recover/rollback where possible and independently read authoritative state. After destructive deduplication, prove target absent and survivor present with only the approved change.

## Evidence and calibration

Retain scope, inventory, IDs, secret-free permission preflight, recovery plan, delta, verdict, execution receipt and post-readback. Routing, authentication, exit 0 or guessed lookup failures prove no mutation.

Block or keep unmeasured: omitted canonical alias; unavailable delete scope; mobile-only user with required desktop confirmation; successful response without survivor/postcondition readback.
