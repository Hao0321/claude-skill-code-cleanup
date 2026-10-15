# Completion detail card

## Applicability

Use for explicit completion, release closure, parity or final handoff. Ordinary discovery, implementation and advisory audits omit this card. Batch cardinality, platform signing or multi-product closure additionally need `../capability-obligations.md` and `../completion-closure.md`; both remain available through legacy fallback.

## Rules

- `rd.complete.detail-status-isolation`: `completion.no-status-inheritance` — freeze scope and the canonical obligation ledger. Tool health, source tests, screenshots and zero Cleanup findings do not establish product, artifact, parity or external readiness.
- `rd.complete.detail-last-mutation`: `completion.last-mutation-barrier` — after the last source/config/document/package/external change, replay each affected evaluator on current hashes and verify captured Skill revisions.
- `rd.complete.detail-residue`: verify delivered artifacts, live hashes, rollback/uninstall residue and required `REVIEW`/`NOT_CHECKED`; keep optional or external gaps as open obligations.

## Evidence and calibration

Retain scope, obligation IDs, evaluator/config identities, final source/artifact hashes, strict review, replay times and authoritative readback. Selection proves no execution. Test counts, stale receipts and source journeys cannot establish closure.

Block negative controls: missing required obligation; changed in-scope byte; build-directory artifact substituted for delivery; unresolved required `REVIEW`/`NOT_CHECKED`.
