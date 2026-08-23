# Completion closure

Use this contract when the user asks to finish everything, stop asking for iterative confirmation, declare a product done, or hand off a release after a long multi-turn campaign.

## Freeze the scope

1. Read the canonical capability ledger and add any newly promised workflow before implementation.
2. Name the completion scope: `internal`, `public`, `parity`, platform-specific, or another explicit boundary.
3. Separate product functions from human-preference, legal/rights, signing, external-account, physical-device and competitor claims. Unsupported stronger claims remain `unmeasured` or `blocked_external`.
4. Convert every applicable claim into replayable evidence. A count of green tests is not a closed-world requirement list.
5. For cross-system or market claims, persist `claim_matrix_gate.py` output after the final mutation. Instrument GREEN does not close the claim unless `claimClosure` is GREEN; completion/parity runs must use `--require-claim-closed`.

## Close findings, not just failures

For an ordinary audit, `REVIEW` remains advisory. For an explicit full-completion or release-closure claim, run Cleanup promotion with `--review-policy block`. Resolve each REVIEW semantically by refactoring, narrowing responsibility, or changing the claim; do not hide it with thresholds or ignores. If a justified long-lived exception is necessary, the task is not zero-REVIEW closure and the handoff must name that exception.

Required `NOT_CHECKED` dimensions block. Optional NOT_CHECKED dimensions remain visible with the reason they are outside the declared scope.

When the frozen scope includes batch or mass production, completion also needs closed-world cardinality evidence: N sources/groups yield N isolated jobs, editable projects, renders and receipts. Prove partial-failure continuation, job-local retry, restart recovery, source byte preservation and normal-editor re-entry on the delivered artifact. Do not close the scope from a multi-import control or a loop around a single-item unit test.

## Last-mutation barrier

Promotion evidence must be captured after the final source, test, configuration, documentation and packaging mutation. If anything inside the frozen target changes afterward, rerun the affected gates.

When saving Cleanup evidence inside the audited target, place it in a directory excluded by `audit.config.json`; otherwise the report becomes self-referential and must measurement-block. Capture and verify with:

```powershell
python scripts/run_cleanup_gate.py <target> --mode all --phase promotion --review-policy block --output <target>/.rd/benchmarks/cleanup-promotion.json --quiet
python scripts/verify_cleanup_evidence.py <target>/.rd/benchmarks/cleanup-promotion.json
```

The capture adapter performs an immediate second audit. The verifier replays the provider later and rejects evaluator/config/adapter drift, changed bytes, added files and removed files. Run it after final documentation and release-note edits, not before them.

When several products or Skills are being edited by concurrent sessions, the active private Skill directories are the sole canonical source. At every invocation, capture both canonical trees with `scripts/invocation_revision_gate.py`, read the current `SKILL.md` and routed references, then verify that capture before the final decision. Never execute from a public mirror, conversation summary, cached copy or another project's worktree. Do not wait for unfinished sessions; work becomes current only when it lands in the canonical private tree. Before editing, re-read the exact current files and merge onto them. Public sync is private-to-public only.

Concurrent evaluator or instruction-tree changes invalidate downstream evidence even when product bytes did not change. Cleanup contract `1.2` freezes full provider and adapter revisions, and rejects old envelopes without them. After current Skill edits and public syncs, replay every saved Cleanup promotion and then run the single completion bundle gate. If any evaluator/config/adapter/revision identity changed, re-read the latest Skill, rerun its self-test, recapture promotion, and retry. Do not weaken this into a warning.

For web products, persist the executable web decision with `web_acceptance_gate.py <input-report> --root <project-root> --output <gate-report.json> --quiet`, then bind that exact gate report as hash-locked `json-evidence` in the completion contract. Do not assert `GREEN` directly on the collector input, because input evidence and evaluator output are different artifacts.

```powershell
$env:PYTHONUTF8='1'
python scripts/completion_closure_gate.py <closure-contract.json> --root <evidence-root> --output <closure-report.json> --quiet
```

The contract has a closed-world `requiredCheckIds` list. Supported checks are strict fresh Cleanup promotions, delivery contracts, capability ledgers, live build receipts, exact file identities and hash-bound JSON evidence assertions. Use separate Cleanup promotion checks for the product and for every concurrently maintained Skill, so final closure proves all parties used the latest canonical bytes.

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
