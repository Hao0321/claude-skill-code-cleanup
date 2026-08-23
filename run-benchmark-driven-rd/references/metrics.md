# Metric Patterns

## Table of contents

[Generic engineering](#generic-engineering) · [Professional Timeline](#professional-timeline-interaction) · [Professional color](#professional-color-evidence) · [Tracking](#computer-vision-recognition-and-tracking) · [Thresholds](#threshold-guidance)

## Generic engineering

- correctness rate and failure severity;
- median and p95 latency;
- throughput under sustained load;
- peak memory and binary/model size;
- compatibility coverage;
- crash/error rate;
- user-task completion rate.

Use a primary metric plus guardrails. A quality win that violates a hard latency or safety ceiling fails promotion.

Performance promotion runs on the same physical host must not execute competing CPU, GPU, disk, model-loading, packaging, or benchmark workloads concurrently unless contention is the declared scenario. Record host identity and warmup/sample policy; if an isolated rerun changes a threshold decision, retain the contended result as diagnostic evidence and use only the isolated protocol for promotion. Parallelize correctness gates freely, but serialize measurements that share the constrained resource.

## Professional Timeline interaction

Measure editor interaction independently from render throughput and domain-planner speed. Freeze the project topology (track count, clip count, duration distribution, effects/markers, zoom and viewport), host/display scale, runtime build, warmup and sample policy.

Required families:

- viewport/index query p50/p95;
- materialized timeline clip/node count at each viewport and zoom;
- pointer/keyboard input-to-visible-state p50/p95 for select, move, trim, split, zoom, scroll and playhead scrub;
- command mutation and Undo/Redo p50/p95;
- dropped frames or long tasks during continuous scrub/scroll;
- peak memory and recovery/reopen behavior on the same large project.

For direct manipulation, inject one real press, multiple distinct pointer positions and one release. Every sampled move must reach a visible transient state within budget; release must create exactly one canonical history entry, one Undo must restore the origin, Redo must restore the result, and Autosave/reopen must retain it. Record the number of requested and observed moves, p50/p95 input-to-visible latency, long-task count and materialized node count. A journey where only the first move changes or release never commits is failed event continuity, not a slow-but-working editor.

For edge trim, freeze the opposite edge as an explicit semantic invariant: a start-edge trim moves Timeline start and source start by the same frame-aligned delta while preserving the original Timeline end; an end-edge trim preserves Timeline start. Enforce a one-frame minimum, reject outward extension when discarded source state cannot be reconstructed, and require the whole release to remain one Undo entry.

Keep compositor work and canonical mutation separate: use frame-coalesced transient transforms/scroll during movement, then commit once at release. Do not prescribe C++／Rust／GPU for a gesture defect until the delivered event stream is correct and profiling shows the UI compositor or command boundary misses its frozen budget.

A headless command loop or interval-index microbenchmark may close only its named layer. It cannot close UI fluidity unless a same-build delivered journey injects real inputs, observes visible state, proves offscreen virtualization and verifies selection/playhead/marker/edit semantics. Do not combine planner, DOM and render measurements into one averaged “Timeline latency”.

Add semantic correctness guardrails to latency runs. Invalid drop regions must produce zero canonical movement after release; ripple delete must shift the declared synchronized downstream set by the removed duration within frame-alignment tolerance and one Undo must restore the exact graph. A fast interaction that changes the wrong lane, leaves a gap or needs multiple recovery commands fails regardless of p95 latency.

Bundle size guardrails are exact and multi-dimensional. Evaluate raw main bytes, compressed bytes, CSS and lazy chunks independently; a candidate exceeding any configured hard ceiling by even one byte fails. Promotion removes the regression or changes the product contract with explicit justification—never silently widens the budget because the overage is small.

For beginner workflows, measure findability separately from task execution: fresh-profile time／clicks to import, select a content type, start automatic editing, find library previews, reopen guidance and locate manual fine-tuning. The evaluator must not preload the route or name a hidden control before the discovery trial. A control that works after a scripted selector targets it can still fail human discoverability.

Treat whole-window file drop as its own beginner input path. Measure visible drag-over feedback, supported／rejected format messaging and whether desktop path drops converge on the same durable probe／cache／canvas／Timeline pipeline as the file picker; a browser object URL or decorative drop overlay alone is not durable desktop import evidence.

Professional comparison needs frozen competitor versions, identical media/project topology, device receipt and a user-task protocol. Synthetic 50K-clip telemetry is valuable scale evidence but remains diagnostic for real creator projects until representative media, effects and interaction sequences are replayed.

## Professional color evidence

Treat color implementation, decoded-output correctness, HDR delivery and calibrated-reference-display parity as separate metric cells. Required implementation telemetry normally includes source metadata recognition, unsupported/unknown transform rejection, actual decoded frame deltas, pipeline-order identity, export codec/pixel-format/color-tag readback and real-pixel waveform/vectorscope behavior. HLG/PQ transforms tested only on generated fixtures do not close real-camera or calibrated-display quality.

Scopes computed from a source preview are not ground truth for the exported frame. For output claims, decode the retained render and compute metrics from those pixels. Preserve one-look-only and unknown-Log negative controls so a visually dramatic change cannot pass by applying the look twice or guessing an input curve.

## Rendered overlay visibility and editorial preservation

Measure the decoded artifact, not only the project graph. Freeze claim-critical graphic IDs, active ranges, expected anchor/safe area, representative background classes and the encoded output hash. For each title/card/tag/HUD family, sample entrance, middle and exit plus subject-boundary positions and record:

- visible-sample ratio and consecutive invisible samples;
- safe-area violation rate and clipped-pixel／off-screen placement;
- foreground/background contrast or an equivalent calibrated readability score;
- position jitter and per-sample alpha/flicker discontinuity for tracked graphics;
- timing error against the declared active range.

Include decoded negative fixtures where every tracking sample restarts a fade, a right-edge subject pushes the label outside the frame, and style values are valid but the composed pixels are unreadable. A zero tracker-lost ratio cannot substitute for these metrics.

For domain-significant waiting, silence or low-motion intervals, freeze semantic preserve ranges with evidence IDs before editing. Measure retained frame coverage and boundary error in the applied project and decoded output. Generic dead-air／low-flow removal fails if it shortens a required proof range, even when overall duration or retention improves.

Audio promotion uses final encoded integrated loudness, loudness range and true peak. Mix-bus gain, PCM sample peak and limiter settings are diagnostic because AAC／platform encoding can create inter-sample overs. Calibrate a too-hot encoded negative and set the product ceiling from delivery requirements.

## Computer vision recognition and tracking

Recommended aggregate metrics:

- `detectionRecall`: targets acquired within the allowed window / visible target trials;
- `poseSuccessRate`: frames whose pose error stays within the declared tolerance;
- `falsePositiveRate`: negative trials that produce a target lock;
- `medianAcquireMs`: first-visible-frame to stable lock;
- `p95ReacquireMs`: reacquisition after occlusion or frame exit;
- `medianJitterPx`: stationary projected-anchor jitter;
- `medianFrameMs`: sustained processing time;
- `peakMemoryMb`: peak working set during the run.

Minimum scenario families:

- frontal and 30/60-degree viewpoint;
- near/far scale;
- low light and exposure change;
- motion blur;
- partial occlusion;
- glare or print/display differences;
- repeated-pattern distractors;
- unrelated negative controls.

Do not use target-image design quality as a substitute for runtime recall. It is an upstream predictor and authoring gate, not proof that the tracker wins.

### Evidence-state rule

Use three explicit states:

- `unmeasured`: no valid run exists;
- `diagnostic`: useful engineering telemetry exists, but one or more promotion evidence families are missing;
- `measured`: positive targets, negative controls, loss/reacquisition, stationary jitter, performance cost, and declared pose ground truth are complete under frozen provenance.

Tracker detections are observations, never ground truth. Target visibility, occlusion, stationary intervals, and pose error must come from an independent annotation or controlled protocol.

When comparing engines, replay identical frozen frames or video bytes. “Same target under similar camera motion” is not identical input and cannot support a direct superiority gate.

For external-camera or file-driver benchmarks, record source-video hash, decoded-frame-pack hash, decoder version, pixel format, per-frame timestamp identity, and camera calibration. Reject a completed run when any staged frame lacks exactly one observation or when the engine runner has access to truth during inference.

`stableFrames` means unique input frames. Deduplicate asynchronous inference completions by decoder/presentation frame identity before calculating acquisition, reacquisition, or false locks. Verify that media element pixel dimensions—not only CSS layout—match the decoded input contract before inference.

## Threshold guidance

Define both relative and absolute gates. Example:

- recall must improve by at least 2% relative and remain at or above 90%;
- false positives must drop by 20% and remain at or below 0.5%;
- latency must improve by 10% and stay below the product ceiling;
- no required hard-case scenario may regress beyond its tolerance.

Set actual values from product needs and baseline variance. Do not copy the example without justification.
