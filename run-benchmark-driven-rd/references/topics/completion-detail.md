# Completion detail card

## Applicability

Use for an explicit completion, release-closure, parity, or final handoff claim. Do not load for ordinary discovery, implementation, or advisory audit. Load `../capability-obligations.md` and `../completion-closure.md` only for a special closed-world family not represented here, such as batch cardinality, platform signing, or multi-product closure; legacy fallback keeps both long contracts available.

## Rules

- `rd.complete.detail-status-isolation`: `completion.no-status-inheritance` — freeze the claimed scope and canonical obligation ledger. Tool health, source tests, screenshots, and zero Cleanup findings do not inherit product, artifact, parity, or external readiness.
- `rd.complete.detail-last-mutation`: `completion.last-mutation-barrier` — after the final source, configuration, documentation, package, or external mutation, replay every affected evaluator against current hashes and verify the captured Skill revisions.
- `rd.complete.detail-residue`: verify current delivered artifacts, live hashes, rollback/uninstall residue, and every required `REVIEW` or `NOT_CHECKED`; preserve optional or external gaps as explicit open obligations.

## Evidence and calibration

Retain the frozen scope, required obligation IDs, evaluator/config identities, final source and artifact hashes, strict-review result, replay timestamps, and authoritative readback. The route selects these requirements but never reports them passed.

False green: a green test count, stale promotion receipt, or source-only journey is presented as final closure.

Negative fixtures: remove one required obligation; mutate one in-scope byte after evidence; substitute a build-directory artifact for the delivered envelope; leave a required `REVIEW` or `NOT_CHECKED`. Each must keep closure blocked.
