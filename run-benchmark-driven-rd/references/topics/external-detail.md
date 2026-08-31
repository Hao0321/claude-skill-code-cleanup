# External-change detail card

## Applicability

Use only when the authorized task may create, publish, rename, transfer, archive, delete, deploy, rotate, or otherwise mutate an external resource. Local design, URL review, and updater discovery do not select it. Load `../external-change-gates.md` for unusual provider-specific recovery or destructive deduplication; legacy fallback retains the full contract.

## Rules

- `rd.external.detail-target-resolution`: inventory the exact namespace and aliases before mutation; bind account, owner, service/region, stable resource ID, canonical survivor, mutation target, and rejected alternatives. A guessed-name 404 cannot prove absence.
- `rd.external.detail-authorization`: separate current user authorization from live technical scope, role, payment, sudo/2FA, and available interaction surface. Approval for one target or reversible write cannot authorize another target, persistence, publication, or deletion.
- `rd.external.detail-postconditions`: preview the smallest exact delta, recover or rollback when possible, then independently read authoritative remote state. For destructive deduplication prove target absent and canonical survivor present and unchanged except for the approved delta.

## Evidence and calibration

Retain request scope, namespace inventory, target IDs, permission preflight without secrets, recovery plan, proposed delta, gate decision, execution receipt, and post-readback. A route or local exit code is not mutation evidence.

False green: authentication succeeds, a local command exits zero, or one guessed lookup misses, so the workflow claims the correct resource changed.

Negative fixtures: plausible canonical alias omitted; final delete scope unavailable; user becomes mobile-only before a desktop-only confirmation; mutation response succeeds but survivor/postcondition readback is missing. Each must block or remain unmeasured.
