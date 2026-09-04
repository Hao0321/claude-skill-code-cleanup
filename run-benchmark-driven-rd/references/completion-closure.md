# Completion closure

Use this contract for an explicit done／release handoff after a long-running scope.

## Freeze the scope

1. Freeze the canonical capability ledger, including every promised workflow.
2. Declare `internal`／`public`／`parity` and any platform boundary.
3. Split product functions from preference, rights/signing, external-account/device and competitor claims; unsupported claims stay `unmeasured`／`blocked_external`.
4. Bind each applicable claim to replayable evidence; green-test counts are not closed-world coverage.
5. After the last mutation, persist `claim_matrix_gate.py`; cross-system／market completion needs `claimClosure=GREEN` and `--require-claim-closed`.

## Close findings, not just failures

Ordinary audit `REVIEW` is advisory; completion runs Cleanup promotion with `--review-policy block`. Resolve REVIEW by code or claim changes, not ignores/thresholds. A retained exception must be named and is not zero-REVIEW closure. Required `NOT_CHECKED` blocks; optional gaps stay visible.

Batch scope also needs N-source → N isolated job/project/render/receipt evidence, partial-failure continuation, local retry, restart recovery, source-byte preservation and editor re-entry. A loop around one unit fixture is insufficient.

## Last-mutation barrier

Capture promotion after the final source/test/config/docs/package mutation; later target changes invalidate affected gates. Store Cleanup evidence only in an `audit.config.json`-excluded directory:

```powershell
python scripts/run_cleanup_gate.py <target> --mode all --phase promotion --review-policy block --output <target>/.rd/benchmarks/cleanup-promotion.json --quiet
python scripts/verify_cleanup_evidence.py <target>/.rd/benchmarks/cleanup-promotion.json
```

Capture immediately re-audits; verification rejects evaluator/config/adapter drift and added/removed/changed bytes. With concurrent sessions, canonical private Skills are the sole authority: capture both trees with `invocation_revision_gate.py`, read current routed files, merge only landed edits, then verify before deciding. Never execute a public mirror/cache/summary/worktree copy; sync is private→public only. Evaluator/instruction drift invalidates evidence even when product bytes are unchanged, so rerun self-tests, promotion and the final bundle.

For web products, persist `web_acceptance_gate.py` output and bind that exact report as hash-locked `json-evidence`; collector input is not an executable GREEN decision.

```powershell
$env:PYTHONUTF8='1'
python scripts/completion_closure_gate.py <closure-contract.json> --root <evidence-root> --output <closure-report.json> --quiet
```

V2 has closed-world `requiredCheckIds`; v1 always returns `legacy-unbound-completion-contract`. Checks cover strict Cleanup promotion, delivery/capability, live build/security receipts, file identity, hash-bound JSON, and exactly one required `route-receipt`. Route replay binds project/optional contract, current profile/references/routing hash and typed update/security obligations.

Paths stay lexically under root and reject escape, ADS, controls, trailing dot/space, device names and symlink/reparse components. JSON is ≤5 MiB with unique keys, integer-only signed-64 numbers and depth/node bounds. Identities stream from one stable handle.

One capability ledger must hold the route's full exact-case floor; partial-ledger unions fail. Typed route decides security, but `public/parity` additionally requires both distributable-update and security floors—`audit/source` cannot downgrade it. Required routes need exactly one ≤24h v2 assessment with verified snapshot/plan. Completion hashes bounded NFC product/version under `cleanup-security-target-identity/v1` and compares only identity profile/digest; reports omit plaintext. External contact also needs closure-owned `expectedGrantSha256`; local checks carry no grant. Excluded internal routes cannot smuggle a scan.

For `public/parity`, closure requires exactly one route receipt, capability ledger, security assessment, Cleanup promotion, delivery contract and build receipt, plus exactly one routed `release-artifact` file identity. All subject-bearing checks must resolve to the route `projectRoot`; the release artifact must equal the delivery envelope identity and occur in the verified build outputs. A sibling decoy, same-root alternate artifact or three-check route/security/capability bundle cannot close release. In parity scope, obligations marked internal or public are both required.

This proves local byte/route/evidence consistency, not scanner truth. Independent release claims need an outer trusted CI signer/attestation binding completion, route and security-receipt digests; local adapter/calibration claims are not that anchor.

## Product residue and canonical artifacts

Where applicable, independently verify:

- only the intended current delivery artifacts remain;
- their live hashes match the handoff;
- no product processes, sessions, temporary exports, registry/install entries or superseded packages remain after the tested lifecycle;
- clean install, restart persistence, upgrade/uninstall and rollback paths match the release claim;
- retained proof is readable and points to the actual delivered build.

Do not delete broad paths merely to make residue checks green. Resolve exact targets and preserve unrelated user data.

## Handoff

Lead with the operational artifact and measured scope. Report exact gate results, strongest real scenario, hashes/evidence paths and open external/unmeasured obligations. Do not say “perfect”, “market best”, “all done” or “surpassed” beyond the scope whose closed-world gate and freshness verification passed.
