# Metric Patterns

## Generic engineering

- correctness rate and failure severity;
- median and p95 latency;
- throughput under sustained load;
- peak memory and binary/model size;
- compatibility coverage;
- crash/error rate;
- user-task completion rate.

Use a primary metric plus guardrails. A quality win that violates a hard latency or safety ceiling fails promotion.

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
