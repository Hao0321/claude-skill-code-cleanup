# Media evidence card

## Applicability

Use when the delivered product records, renders, converts, edits, or exports audio/video. Exclude image-only, document-only, and ordinary code tasks. Pair with the bounded delivery card for shipped artifacts. Load `../media-artifact-evidence.md` for specialized tracking, automatic composition, catalog previews, loudness, semantic preserve ranges, or editorial-cardinality claims; legacy fallback retains the full contract.

## Rules

- `rd.media.decoded-authority`: `media.decoded-user-output-is-authority` — hash the retained user-facing artifact, then independently decode it; UI labels, extensions, encoder settings, and render counters are diagnostic.
- `rd.media.strongest-scenario`: exercise the strongest shipped profile, packaged runtime, full duration and final tail, promised aspect/resolution/mode, retry/shutdown, and independently observed background state when claimed.
- `rd.media.calibrated-negatives`: evaluator controls independently inject wrong container/codec/geometry/cadence, silence/clipping, frozen tail, truncation, stale build, and orphan temporary state.
- `rd.media.evidence-envelope`: bind input/build/output SHA-256, codecs, dimensions, duration, encoded/decoded cadence, frame/tail uniqueness, decoded audio levels/hash, evaluator/config identity, timeout, and residue delta.
- `rd.media.editable-render-journey`: where editing is claimed, apply through the delivered UI/API, persist and reopen editable state, make a normal edit, render, and independently verify the decoded result; architecture or screenshots cannot substitute.

## Evidence and calibration

Retain source and output identities, independent probe/decode report, strongest-scenario receipt, final-tail/audio samples, runtime state, delivered journey, and negative-control decisions.

False green: a synthetic clip, first-frame sample, source-mode pass, file extension, or card count is promoted as full delivered media quality.

Negative fixtures: wrong codec/resolution; silent or clipped audio; frozen/truncated tail; identical audio across distinct modes; stale packaged identity; orphan temp files; editable state that does not survive reopen/render. Each applicable case must block.
