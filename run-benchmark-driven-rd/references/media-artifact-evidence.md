# Media artifact evidence

## Table of contents

[Authority](#authority) · [Scenarios](#user-task-scenarios) · [Negatives](#calibrated-negatives) · [Evidence envelope](#evidence-envelope) · [Tracking](#motion-tracking-and-attached-graphics) · [Music](#automatic-music-and-ducking) · [Previews](#visual-preset-and-catalogue-previews) · [Automatic composition](#native-automatic-composition) · [Decoded visibility](#decoded-overlay-visibility-and-semantic-evidence-ranges) · [Promotion](#promotion-boundary)

Use this contract when the product records, renders, converts, or exports audio/video. It is conditional: image-only, document-only, and ordinary code tasks do not need these gates.

## Authority

The retained, decoded user-delivered artifact is authoritative. UI labels, encoder options, file extensions, render-loop counters, and a successful API return are diagnostic only.

Record the envelope hash and bytes, then decode it with a mature independent parser such as FFmpeg/ffprobe. Verify the actual container streams, codec identities, dimensions, duration, cadence, channel/rate contract, and audio levels. A `.mp4` filename is not proof of H.264/AAC; a 4K dropdown is not proof of decoded 4K frames.

Canonicalize decoded content when identities matter:

- video motion: sample decoded frame hashes near the final tail, not application state alone;
- audio identity: decode to a declared channel count, sample rate and PCM format before hashing;
- multi-instrument or multi-voice claims: require distinct canonical decoded hashes plus audible, peak-safe levels;
- source identity: retain the exact input hash and renderer/evaluator version.

## User-task scenarios

The scenario matrix must cover the strongest shipped claim, not only the cheapest smoke test. Select applicable cases such as:

- source/runtime smoke and the final packaged or installed product;
- short clip and full-duration completion;
- foreground and independently verified background/minimized execution;
- each promised aspect ratio, including the maximum resolution profile;
- every output mode whose visual or audio identity is user-visible;
- clean shutdown, retry/failure cleanup and bounded temporary storage.

For background/minimized claims, collect window/process state from the operating system or another independent surface. Renderer self-report cannot prove that its own window was minimized.

For long recordings, verify final-tail motion and audio, not merely the first seconds. Recording duration should cover the declared user workflow plus encoder finalization tolerance.

## Calibrated negatives

Before promotion, the evaluator must reject task-shaped fixtures for every applicable failure class:

- wrong resolution, aspect ratio, encoded cadence or decoded cadence;
- wrong/missing codec or malformed probe output;
- silence, missing audio, clipping, or an absent canonical audio hash;
- frozen final frames while audio continues;
- identical decoded audio across modes that claim different instruments/voices;
- truncated full-duration output;
- stale artifact, wrong executable/build identity, or evidence from source mode substituted for packaged mode;
- orphan temporary/session files after success, failure, retry, or shutdown.

Keep the positive and negative fixtures independent of the production renderer. A candidate cannot generate its own ground truth or declare itself valid.

## Evidence envelope

Retain at least:

- product/build/executable identity and SHA-256;
- scenario, input identity, requested profile and independently observed runtime/window state;
- output path or retained proof reference, bytes and SHA-256;
- decoded stream codecs, dimensions, duration, encoded and decoded cadence;
- decoded frame count and final-tail sample/unique counts;
- mean and peak audio levels plus canonical decoded-audio hash when audio is required;
- evaluator/config identity, timeout, timestamp and temporary-file delta;
- explicit status: `measured`, `diagnostic`, `unmeasured`, or `blocked`.

Performance numbers collected under competing encode/render workloads remain diagnostic unless contention is the declared scenario. Serialize GPU/CPU/disk-heavy promotion runs on the same host.

## Motion tracking and attached graphics

Treat tracking pipeline availability and professional-quality tracking as separate obligations. A deterministic translated rectangle can verify transport, caching and coordinate conventions, but it cannot close a claim comparable to After Effects, CapCut, roto/mask tracking or 3D camera tracking.

For the shipped tracking mode, retain:

- initial region and per-sample normalized ground-truth boxes from an independent annotation source;
- per-frame predicted box, confidence and explicit tracked／held／lost／manual status;
- IoU distribution, center drift, scale error, lost ratio, occlusion recovery latency and boundary failures;
- real footage spanning people, products, low texture, fast motion, scale, rotation, partial／full occlusion and scene cuts;
- elapsed analysis time, cache identity, analysis cadence and memory on each claimed device class;
- number and seconds of manual corrections needed to reach an acceptance threshold;
- decoded frame evidence proving the attached label／graphic follows the stored track in the final render.

Lost-state honesty is part of correctness: an evaluator must fail a tracker that invents high-confidence boxes through unsupported frames. Manual correction is a valid workflow outcome only when its time and resulting accuracy are measured, not when it hides systematic drift. Keep 2D region, planar/perspective, mask/roto and 3D camera tracking as distinct capability obligations.

## Automatic music and ducking

Verify the actual packaged library, not its card count. Independently decode every declared track or a closed-world hash-bound inventory, validate duration／sample rate／channels and retain licensing scope. For automatic selection, test deterministic metadata inputs, recent-repeat handling, full timeline coverage and crossfade boundaries. Render speech plus music, then measure decoded band-limited or stem-aware levels during and outside voice regions; require the declared ducking delta without clipping, truncation or a missing tail. Internal owner-only library success must not promote public redistribution rights.

## Visual preset and catalogue previews

Keep four obligations separate: a pack exists, the delivered UI exposes it, its preview represents the selected media／preset, and applying it persists into the editable graph and final render. Card counts, text labels, gradients, screenshots, or hidden `<select>` options prove none of the later edges.

Require a delivered journey that lazy-loads every claim-critical browser: real B-roll image/video thumbnails, playable or waveform-backed music, the selected source frame under each Look/effect, an animated transition loop, and rendered caption／title／tag／text-animation previews. Then apply one member of every promised family, save/reopen, Undo/Redo, render, and independently decode the result. Record lazy chunk identity, load failure state, media decode failure state, activation latency, and bundle bytes; moving code out of the main chunk cannot close a regression if total claim-critical bytes balloon or the chunk is absent from the installer.

## Native automatic composition

Module availability and isolated recognizer/tracker/effect tests do not prove one-click automatic editing. Freeze a closed-world creative plan covering applicable semantic cuts, editable captions and caption design, rhythm receipt, music selection/coverage/ducking, look, effect, transition, motion graphic/title/card/tag, and tracking. Every family must record `selected`, `skipped` or `blocked` with a reason; silent omission is failure.

The accepted journey must enter through the shipped automatic-edit control, create one atomic editable graph mutation with one Undo boundary, preserve user source bytes, save/reopen, allow a normal manual edit, and render. Bind plan/schema/engine/model provenance and chosen asset IDs to the receipt. Independently decode the result and verify both structural state and audiovisual differences. Tracking quality remains its own calibrated obligation; a low-confidence tracker may honestly skip attachment, but cannot invent a successful track merely to make the composition matrix full.

When one long source is repurposed into several publishable clips, validate editorial-unit cardinality separately from batch source count. Retain the independent unit map, expected N, source hash, per-unit source ranges, editable project identity, output hash and receipt identity. Decode every retained output and verify its own promise/payoff evidence. A single compilation containing all units, N manifests pointing to the same project/output, or a new encode with the old editorial fingerprint is a calibrated negative—not a successful batch.

## Decoded overlay visibility and semantic evidence ranges

An editable motion-graphic object is not proof that the audience can see it. For each claim-critical title, result card, counter, tag or tracked HUD, retain decoded samples at entrance, middle and exit; tracked elements additionally sample left/center/right or other boundary positions. Verify that glyphs or graphic pixels are present, readable against the composed background, inside the declared safe area and stable across adjacent tracking samples. A render that applies fade-in/out independently to every short tracking sample can report perfect tracking while keeping the label permanently translucent; an anchor placed beyond the subject's right edge can remain valid numerically while leaving the frame. Both are calibrated negative fixtures.

Editorial removal needs a semantic exception contract. Freeze evidence-backed preserve ranges before generic silence, repetition or low-motion cleanup, carry their IDs into the plan and applied-project receipt, then compare source-to-project and source-to-decoded timing. Waiting can be story proof rather than dead air—for example, continued spin establishes an endurance result. A duration-only check cannot prove that the meaningful interval survived.

Measure audio on the final encoded artifact. Retain integrated loudness, loudness range and true peak after AAC／delivery encoding; source gain, PCM peak or a configured limiter is insufficient because inter-sample overs may appear after encoding. Promotion requires a codec-shaped over-ceiling negative and the declared delivery ceiling.

## Promotion boundary

Promote only when the final delivered product passes the strongest required scenario and the evaluator's negatives. A source-mode pass cannot close a packaged-product obligation. A synthetic clip cannot prove full-song or long-form completion. Architecture, screenshots, and UI polish cannot substitute for decoded artifact evidence.
