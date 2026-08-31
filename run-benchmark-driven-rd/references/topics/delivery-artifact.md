# Delivery artifact card

## Applicability

Use for installers, app bundles, archives, release assets, model/media packs, or any claim about shipped bytes. Exclude source-only discovery and pre-packaging development acceptance. Load `../delivery-artifact-gates.md` only for a specialized delivery family such as batch recovery, desktop IPC responsiveness, direct manipulation, Timeline semantics, fonts, or first-run UX; legacy routes retain the long contract.

## Rules

- `rd.delivery.envelope-authority`: `delivery.extracted-envelope-is-authority` — hash the live user-delivered envelope, extract it safely, and treat the extracted payload as authority; build-directory output is diagnostic.
- `rd.delivery.closed-world-payload`: reject traversal, symlinks, case-insensitive duplicates, missing, unexpected, or mismatched files. Bind SBOM, notices, redistribution scope, and claim-critical lazy assets inside the payload.
- `rd.delivery.canonical-build-chain`: prove current inputs rebuilt canonical outputs before packaging; bind executable/runtime identity and embedded build receipt to live bytes.
- `rd.delivery.delivered-journey`: `delivery.source-tests-do-not-prove-shipped-bytes` — execute or load the extracted product, activate the claimed surface, and read durable state plus embedded receipt back.
- `rd.delivery.isolated-state`: use a per-run state root, bounded child timeouts, retained primary stderr/stdout, cleanup as secondary evidence, and at least one replay without inherited state.

## Evidence and calibration

Retain envelope size/SHA-256, safe extraction report, closed-world payload diff, build/receipt identities, rights inventory, delivered journey, evaluator revision, and final readback.

False green: source tests, initial shell launch, filename/extension, or packaging exit zero substitutes for extracted-product evidence.

Negative fixtures: stale envelope; traversal or duplicate path; missing lazy chunk/SBOM; wrong embedded receipt; source journey substituted for packaged journey; second run inherits queued state. Each must block promotion.
