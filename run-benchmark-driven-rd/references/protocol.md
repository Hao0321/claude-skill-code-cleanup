# Benchmark-Driven R&D Protocol

## 1. Claim

Write a one-sentence statement that can be false. Name the competitor or baseline, product surface, users, and constrained environment.

Bad: “tracking is world-class.”

Good: “Candidate A improves planar-target recall over Baseline B on the frozen hard-case set while lowering false positives and staying below the mobile latency ceiling.”

## 2. Provenance lock

Every comparable result must share:

- dataset ID and cryptographic hash;
- scenario list and target/negative counts;
- device, OS, browser/runtime, and build identity;
- warm-up policy, run count, and camera/input settings;
- metric implementation version.

Reject comparisons with mismatched provenance.

Freeze dataset identity from a canonical manifest plus the cryptographic hash and byte size of every input and annotation asset. A human-readable version label alone is insufficient.

For perception systems, “same dataset” means every engine consumes the exact frozen input bytes. Re-recording the same physical scene changes motion, exposure, blur, timing, and pixels, so treat it as field telemetry rather than same-provenance benchmark evidence.

Long campaigns must use globally unique trial identities, resumable durable state, and payload-level deduplication when partial runs merge. Never concatenate evidence files by hand.

## 3. Benchmark shape

Use three layers:

1. Unit or synthetic checks for fast correctness feedback.
2. Frozen regression set for every change.
3. Blinded holdout set for promotion claims.

Include easy, normal, hard, adversarial, and negative-control scenarios. Measure both quality and cost.

## 4. Experiment loop

Before the first baseline, calibrate every evaluator used by the promotion gate. Run its self-test and a task-shaped positive/negative fixture; if it cannot observe a required failure class, improve the evaluator first and record that attempt as `measurement`. Freeze evaluator/config identity with the evidence. See `tooling-and-architecture-gates.md`.

For each hypothesis:

1. Predict the metric movement before coding.
2. Change one dominant variable.
3. Preserve the baseline and rollback path.
4. Measure with identical provenance.
5. Run the gate.
6. Log pass, fail, inconclusive, or blocked.
7. Decide: promote, iterate, branch by capability, or kill.

External engine adapters must emit observations separately from ground truth. Join the timelines only after inference has finished so an engine-specific runner cannot relabel its own output.

For proprietary engines, keep deterministic parsing, staging, and evidence verification outside the proprietary SDK boundary. Compile a thin ABI adapter only when the exact SDK/header/license/toolchain capability gate passes. Missing capabilities produce `blocked` evidence, never simulated competitor observations.

When a proprietary header is portal-gated but its interface is publicly documented, an interoperability declaration may be reconstructed to test code owned by the project. Treat compile-time layout assertions and standalone ABI/lifecycle tests as `integration` evidence only. Promotion still requires a diff against the licensed header, loading through the exact vendor runtime, a valid license, and the normal post-inference truth join. Never relabel interface compatibility as competitor accuracy.

Header availability is not build provenance. Emit a content-addressed build receipt that locks the exact header, owned source inputs, output artifact, test inputs, and test outcomes. The promotion gate must re-hash the live header and artifact and reject compatibility-header, stale, or receipt-less builds even when standalone ABI tests pass.

For multi-gigabyte SDK/toolchain downloads, lock the official URL, version, release identity or changeset, expected byte length, and vendor checksum or ETag before execution. Transport retries, resume, or range assembly may change; artifact identity may not.

When an installer is only a delivery envelope around a standard package, inspect the envelope before executing its code. Verify the inner package name and version, hash both layers, install through the underlying package manager when supported, and retain a receipt that binds source envelope, inner artifact, and project dependency.

If engines cannot share an in-memory decoder, hash both the identical frozen source bytes and a canonical decoded frame pack with explicit pixel format, timestamps, calibration, and decoder version. Require one observation per unique staged frame. The common target source belongs to dataset provenance; engine-specific compiled target artifacts may differ but must be hashed and locked within each engine.

When evidence crosses threads or processes, preserve record-level atomicity. An observation's frame identity, timestamp, pose, and cost must come from one coherent snapshot; independently atomic fields can still create torn benchmark records. Stress concurrent readers during adapter lifecycle tests.

For video replay, count unique decoded or presented input frames, not inference-loop callbacks. A tracker may process identical pixels multiple times while the video clock remains on one frame; those repeats cannot satisfy a consecutive-frame gate. Record a reproducible executable/build identity and the cryptographic identity of compiled model or target-database assets.

If experiment startup depends on permission, hardware, a service, model loading, or the network, add a deadline that restores a retryable state. A hung experiment is an integration failure and must be logged.

If execution changes an external system, freeze an external-change plan before the first write. The plan must prove namespace inventory, canonical target resolution, user authorization, technical authorization for the final action, interaction-surface compatibility, rollback/recovery, and authoritative postconditions. A successful create call is not evidence that creating was the correct action. A successful push is not evidence that the correct repository was selected.

## 5. Failure taxonomy

Classify failures so future projects can reuse them:

- `algorithm`: the method cannot meet the quality target;
- `data`: coverage, labels, or holdout design are weak;
- `runtime`: latency, memory, thermal, or compatibility failure;
- `integration`: correct component, broken product chain;
- `measurement`: benchmark or telemetry is invalid;
- `product`: metric win does not improve the real user task.
- `target-resolution`: the correct canonical resource was not discovered or uniquely selected before mutation;
- `authorization`: user intent, API scope, account role, sudo/2FA, payment, or interaction-surface capability was missing or checked too late.

## 6. Evidence hierarchy

Strongest to weakest:

1. Blinded, same-provenance benchmark on target devices.
2. Frozen regression benchmark.
3. Field telemetry with known sampling.
4. Reproducible local test.
5. Demo or anecdote.
6. Architecture-based inference.

Match the strength of the claim to the strength of the evidence.
