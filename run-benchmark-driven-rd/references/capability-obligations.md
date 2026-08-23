# Capability obligation closure

Use this contract when a product spans multiple turns, agents, platforms or release scopes. Its purpose is to prevent a green subsystem test from being reported as a finished product.

## Closed-world ledger

Keep one machine-readable capability ledger in the product repository. It must include a closed-world `requiredObligationIds` list and one record per obligation. Stable IDs cover user-promised workflows, platforms, release/legal gates, device acceptance and quality claims—not just modules that already exist.

Each record declares:

- status: `verified`, `blocked_external`, `planned`, or `unmeasured`;
- completion scopes such as `internal`, `public`, and `parity`;
- for `verified`: the exact product version and replayable file/command evidence;
- for `blocked_external`: owner, blocking condition and concrete closing action;
- for `planned` or `unmeasured`: the next falsifiable experiment.

Changing product version invalidates stale `verifiedVersion` values until their evidence is rerun. Internal readiness never implies public release or competitor parity.

Split functional integration from quality acceptance. For example, “speech-to-text executes, is cached and writes Undoable captions” may be verified while “real Traditional Chinese creator footage meets CER/WER and human acceptance thresholds” remains unmeasured. Never let one obligation inherit another obligation's stronger claim.

For a professional media workstation, keep at least these boundaries distinct:

- Timeline command/index performance versus delivered UI interaction fluidity versus competitor parity;
- font-pack presence/licensing versus actual exporter font selection;
- primary-grade controls and real-pixel scopes versus decoded-output correctness versus HDR/calibrated-display parity;
- persisted director notes/review readiness versus authenticated human approval, live multi-user collaboration or control-room switching.

For workflow UX, declare the user-visible state matrix before using a single screenshot or DOM gate as acceptance evidence. At minimum separate empty/first-run, fixture or demo, real-user-input, processing, editable-result and recovery/error states when they exist. A demo asset, placeholder record or seeded project must not satisfy a real-input precondition, advance the workflow, enable delivery actions or appear in user-owned counts. Gate shared derived concepts such as `hasRealInput`, current step and `canDeliver` across every surface that renders or acts on them; a green populated-state test cannot close first-run UX.

Each stronger cell stays `unmeasured` or `blocked_external` until its own evidence exists. A verified component must not lend its status upward.

Also split component presence from cross-system closure. If a promise spans a mutable Skill/Agent, MCP/API, product runtime, installer, human review, publish state or outcome learning, verified evidence must include a versioned handoff and a single journey binding the same source revision/hash across every required stage. A Skill and product module existing independently is not integration. Use [cross-system and market claims](cross-system-and-market-claims.md) and `scripts/claim_matrix_gate.py` for the closed-world flow/stage contract.

For session-native AI control, keep at least these obligations distinct: host-session subscription boundary with no editor API key; one-click Codex／Claude configuration; local material analysis; MCP image delivery; bounded transcript windows; evidence-backed semantic receipt; current-plan binding; atomic editable apply. A listed MCP tool, generated install command, transcript module or keyframe cache does not close the combined promise. Promotion requires an isolated real CLI configuration fixture plus one source-hash-bound material→semantics→plan→editable-project journey and stale-source／forged-evidence negatives. Measure model-visible frame count and transcript/context size separately from local decoded-frame analysis so “the local engine processed every frame” is not mislabeled “the model saw every frame.”

## Gate calibration

Use `scripts/capability_gate.py` or a project-native stricter equivalent. Its self-test must detect at least:

- a required obligation deleted from the ledger;
- duplicate ID;
- product/version drift;
- stale verified evidence;
- missing evidence file or command;
- incomplete external blocker;
- private absolute path or secret-shaped text.

The product root is the evidence authority, not the ledger directory. When the ledger lives under `.rd/`, the CLI discovers the nearest ancestor `package.json`; `--package-json` uses that file's parent as the default root, and `--root` may make the boundary explicit. File evidence remains repo-relative POSIX paths such as `.rd/benchmarks/report.json`. Electron packages may declare their display name at `build.productName`; ordinary packages may use top-level `productName` or `name`.

```powershell
python scripts/capability_gate.py <project>/.rd/capability-ledger.json --scope internal --root <project>
```

The gate is additive to correctness, architecture, performance and release gates. Do not replace subsystem benchmarks with ledger checks; the ledger points to those benchmarks.

## Turn protocol

1. At the start of a continuation, read the ledger before choosing work.
2. Add or update obligations when the user changes scope, before implementation.
3. Work the highest-value in-scope open obligation that can be closed on the current host.
4. Promote to `verified` only after current-version evidence passes.
5. Keep certificate purchases, rights-owner license choices, cloud credentials and physical-device evidence blocked until the named owner or environment supplies them.
6. End with the exact open obligations grouped by status and scope; never say “complete” without naming the scope whose gate passed.
7. For market claims, keep the evaluator/contract obligation separate from the leadership-evidence obligation. The former may be verified while the latter remains unmeasured until every required baseline×surface cell has independent evidence.
8. For batch claims, distinguish multi-import/concatenation from fan-out. Add a closed-world source-or-group → stable job → editable project → render → receipt matrix, plus isolated failure, per-job retry, durable restart recovery, read-only source hashing and open-in-editor evidence. One successful repeated call cannot close an N-job product workflow.
