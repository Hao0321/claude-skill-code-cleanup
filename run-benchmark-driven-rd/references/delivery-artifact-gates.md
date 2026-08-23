# Delivery artifact gates

Use this gate for installers, app bundles, package archives, generated media packs, release ZIPs, model bundles, or any product where source tests can pass while the user receives stale or incomplete bytes.

## Authority chain

The user-delivered envelope is the release authority. A build-directory executable is diagnostic and may legitimately differ after a bundler patches metadata or signing data. Inspect the envelope, extract the delivered payload, and validate product identity on the extracted artifact.

Artifact authority does not grant packaging authority. When the user explicitly says to test new behavior in a development build before packaging, stop the delivery gate before envelope construction: retain source／development UI evidence, mark installer obligations planned or stale, and wait for the named acceptance signal. Do not spend packaging time or present an older installer as if it contained the candidate changes.

Promotion needs all of these independent claims:

1. The canonical build rebuilt and hash-promoted native outputs before packaging.
2. The actual delivery envelope's live size and SHA-256 match the evidence.
3. Extraction rejects unsafe paths and case-insensitive duplicates.
4. Payload comparison is closed-world: missing, unexpected, and mismatched files all fail.
5. Current source inputs and generated outputs match a build receipt.
6. The exact receipt bytes are embedded when raw embedding is claimed; runtime readback compares schema fields semantically, not serialized key order.
7. SBOM and third-party notices are inside the delivered payload, not merely beside it.
8. The canonical build invokes the delivery gate automatically after packaging.
9. A delivered-product journey executes or loads the payload and reads the embedded receipt back.
10. The product evaluator has task-shaped negative controls for every required failure class.
11. Claim-critical lazy-loaded chunks are present in the extracted payload and are activated by the delivered-product journey; initial-shell success does not prove optional editor, QR, tracking or export surfaces.
12. Restricted resource packs are compared closed-world and their extracted manifest preserves redistribution scope; an internal-delivery pass is reported separately from public-release readiness.
13. Asset rights survive the runtime handoff: the delivered journey selects a real licensed asset, verifies its bytes, imports it through the same UI/API adapter users receive, persists its license/provenance/redistribution fields, and renders or reopens the resulting project. Pack enumeration alone cannot close this gate.
14. A delivered batch workflow fans N sources or explicit groups into N isolated durable jobs, editable current-schema projects, renders and receipts. The journey injects one failure without blocking siblings, retries only that job, restarts with an interrupted job recovering to queued, reopens one result for an undoable edit, and proves every source hash is unchanged. Multi-select import or repeated unit calls alone do not satisfy this claim.
15. Bundled fonts are closed-world delivery inputs: every font and license is inventoried in receipts/SBOM/notices, survives extracted-payload comparison, and is selected by the actual export renderer in a retained font-selection trace. Exercise a missing-font/fallback negative and the renderer's real directory behavior; do not assume recursive discovery or accept silent system-font fallback.
16. Long native operations exposed through desktop IPC acknowledge immediately with a job state, run off the UI/main thread, and settle through a bounded event or polling contract. The delivered journey delays the backend while independently exercising editor input, rejects duplicate/stale job results, and proves timeout/error paths settle without freezing the WebView.
17. Freshly extracted desktop payloads are tested before warm-cache promotion. Keep the first packaged runtime／library job pending, collect independent short UI heartbeats, then poll that job and each subsequent media／update stage separately. Retain controller misses and reconnects; a single giant awaited automation expression cannot prove UI responsiveness or attribute failure. Verify edits through durable state and artifact readback rather than transient shared status text.
18. Nested journey timeouts preserve the primary child failure and bounded stdout/stderr, terminate and await only the owned process tree, then retry extracted-workspace cleanup. Cleanup failure is appended as secondary evidence and never replaces the journey result. Each retry loop has a true wall-clock deadline plus per-stage markers; an attempt count with a long inner timeout is not a bounded contract.
19. Direct-manipulation delivery evidence uses real press／multi-move／release input against the extracted product, observes every sampled visual update, and proves a single release-time history commit through Undo, Redo and durable Autosave/reopen. Start-edge trim preserves the original Timeline end, end-edge trim preserves Timeline start and every range retains at least one frame. A first-frame-only movement, opposite-edge drift or missing pointer-up remains delivery `BLOCK` even when the underlying calculator and build artifact are green.
20. Delivered journeys use a per-run isolated state root for recovery, batch, updater, cache and trusted-device data, then replay at least twice. The second run must not inherit an Autosave prompt, modal, queued job or device credential from the first. Automation controllers bind pending commands to the socket/session that issued them; closing a failed connection cannot reject replacement-session work. Classify controller loss and product unresponsiveness with independent probes instead of treating either as the other.
21. Timeline drop boundaries are exercised with real pointer input against track labels／headers, locked or incompatible lanes and outside-lane space. Invalid targets stay visibly invalid, cannot overlap the forbidden UI, and release preserves canonical track and time; source-lane fallback may not commit a horizontal move.
22. Ripple delete removes a middle primary-story clip, closes the exact gap across the declared synchronized set and creates one history entry whose single Undo restores every affected clip／caption／graphic／marker. Non-ripple delete and cleanup-as-a-second-command are different product contracts.
23. First-source auto-canvas uses delivered portrait, landscape and near-square fixtures through the actual file input／drop adapter. Native desktop drops and picker selection must converge on the same durable path-based probe／cache／canvas／Timeline pipeline; browser-only object URLs are development evidence. Evidence binds decoded dimensions, starter-placeholder replacement, time-zero placement, persisted project resolution, preview fit and output geometry; a pure ratio helper is diagnostic only.
24. Beginner discoverability starts from a clean profile. Exercise first-run guidance completion and skip, permanent help re-entry, visible automatic-edit prerequisites, whole-window drag-over feedback plus rejected-format messaging, a direct route to named B-roll／music／image preview families, and a selected clip／caption route to named Look／effect／transition／typography previews. Hidden DOM cards, decorative drop zones or instructions supplied by the evaluator do not count as user discovery.

For dirty-project close protection, separate the deterministic guard policy from the native lifecycle journey. A synthetic `beforeunload` dispatched inside CDP is not equivalent to user close/navigation and may itself clear an embedded WebView. Unit-test dirty versus clean guard behavior; verify Autosave independently; close the remaining native prompt claim only with a real navigation/window-close action and owned dialog handling.

Deterministic archives must be generated twice and compared by exact bytes and SHA-256. Performance promotion runs must remain isolated from packaging and other shared-resource workloads.

When the delivered artifact is audio/video, also apply [media-artifact-evidence.md](media-artifact-evidence.md). Decode the retained user-facing file and verify actual streams, cadence, final-tail motion, audio levels and canonical decoded identity; encoder settings, extensions and renderer counters are not delivery evidence.

## Evidence envelope

The project-specific evaluator still performs extraction and semantic inspection. It emits a normalized contract consumed by:

```powershell
$env:PYTHONUTF8='1'
python scripts/delivery_contract_gate.py <contract.json> --root <evidence-root>
python scripts/delivery_contract_gate.py --self-test
```

The gate independently re-hashes the live evaluator report, delivery envelope, and build artifact. The extracted delivered artifact is identified through the product evaluator report and must declare `source: delivery-envelope-extraction` plus `authority: true`; the build artifact must declare `authority: false`.

The gate is a contract validator, not an installer parser. A hand-authored contract cannot replace product-specific raw evidence. Freeze the evaluator identity and retain its raw report beside the normalized contract.

## Failure classification

- stale inputs, outputs, envelope, report, or receipt: `measurement` until rebuilt and remeasured;
- unsafe, duplicate, missing, unexpected, or identity-mismatched payload: `integration`;
- native output not rebuilt or gate not wired into canonical build: `integration`;
- missing SBOM/notices or unresolved redistribution rights: `product` or external obligation;
- signing, notarization, owned update channel, legal license selection, and physical-device acceptance remain explicit external obligations.
