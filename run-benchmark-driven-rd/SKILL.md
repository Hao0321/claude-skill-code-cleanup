---
name: run-benchmark-driven-rd
description: Turn ambitious or uncertain engineering goals into a falsifiable, benchmark-gated R&D system with calibrated evaluation tools, architecture gates, external-change safety, and reusable experiment memory. Use when the user says 做到最好, 全面重構, 架構最優, 超越競品, 自己研發, 研發系統, benchmark, R&D, improve recognition or performance, retain all learning, or asks to build a capability that must compound across future projects. Also use for public release, 開源, 發版, or creating, renaming, publishing, archiving, deleting, transferring, or changing permissions on external resources when canonical-target mistakes or duplicate projects must be prevented.
---

# Run Benchmark-Driven R&D

Build evidence before making superiority claims. Preserve every useful result as a reusable engineering asset.

## Start

Every invocation begins from the current active private Skill directories. Re-read this `SKILL.md` and the routed references from disk; do not rely on a prior turn summary, public mirror, copied prompt, or previously frozen evaluator hash. Do not wait for other projects or merge their worktree copies: bytes already landed in the canonical private trees are the current version.

At invocation start, run `python scripts/invocation_revision_gate.py capture --output <temporary-revision.json> --quiet`; it captures both R&D and Cleanup by default through Cleanup's two-pass provider. Before the final decision, run `python scripts/invocation_revision_gate.py verify <temporary-revision.json>`. `STALE` means re-read the now-current instructions and rerun affected gates; `UNSTABLE` is a measurement block, not permission to use a torn revision. Do not poll for global quiescence or wait for unrelated sessions to finish. `--cleanup-root` is accepted only when it resolves to that same active private provider, so an older worktree or public mirror cannot override the current version.

For a new or mixed project, read [modular-project-system.md](references/modular-project-system.md) and compose a frozen route with `python scripts/project_profile_gate.py --project <root> --contract <root>/.rd/project.json --output <root>/.rd/project-route.json --quiet`. Keep Cleanup as the independent read-only measurement kernel and R&D as the decision／learning orchestrator. Project types (`skill`, `web`, `database`, `game`, `software`) and cross-cutting modules (`public-release`, `security`, `media`, `commerce`) are composable; the route selects references and gates but does not count as evidence that they passed.

1. Read the repository truth: architecture, dependencies, existing tests, performance paths, and local instructions.
2. Read [protocol.md](references/protocol.md).
3. Read [tooling-and-architecture-gates.md](references/tooling-and-architecture-gates.md) and the [Cleanup R&D integration contract](../code-cleanup-helper/references/rd-integration.md) for architecture work, cleanup, refactors, release readiness, or when the evaluator may be incomplete.
4. Read [capability-obligations.md](references/capability-obligations.md) when the work spans multiple turns, platforms or release scopes, or when the user asks what remains, says prior requirements were forgotten, or requests a complete product.
5. Read [metrics.md](references/metrics.md) when the work involves computer vision, latency, reliability, or competitor comparison.
6. Read [delivery-artifact-gates.md](references/delivery-artifact-gates.md) when the project emits installers, app bundles, archives, generated asset packs, release binaries, or other user-delivered artifacts.
7. Read [security-hardening-gates.md](references/security-hardening-gates.md) when the user asks for 防拆包／資安, or the system includes desktop shells, updaters, local agents, Remote control, restricted resource packs, signing or public distribution.
8. Read [media-artifact-evidence.md](references/media-artifact-evidence.md) when the product records, renders, converts, or exports audio/video.
9. Read [completion-closure.md](references/completion-closure.md) when the user asks to finish everything, stop iterating, declare completion, or hand off a long-running product/release.
10. Read [mobile-product-engineering.md](references/mobile-product-engineering.md) when the work involves mobile UI, responsive web, PWA, touch, safe areas, mobile navigation, virtual keyboards, or mobile performance.
11. Read [web-commerce-acceptance.md](references/web-commerce-acceptance.md) for storefronts, product cards, carts, checkout, admin catalogues, overlays, generated product images, or commercial-readiness claims.
12. Read [external-change-gates.md](references/external-change-gates.md) before creating, renaming, publishing, archiving, deleting, transferring, or changing permissions on GitHub, cloud services, app stores, domains, databases, automations, or other external systems.
13. Read [cross-system-and-market-claims.md](references/cross-system-and-market-claims.md) when a claim spans a mutable Skill/Agent, MCP/API, runtime, installer, human review, publishing/outcome learning, or says best／parity／beats every product／lower Token cost.
14. Read [model-and-reasoning-gates.md](references/model-and-reasoning-gates.md) when the product routes Sol／Terra／Luna, changes reasoning effort, uses Markdown／prompt structure as an accuracy strategy, or claims model-dependent quality／Token／latency gains.
15. For professional media workstations, apply the Timeline, typography, color, director-console and decoded automatic-composition contracts across `metrics.md`, `media-artifact-evidence.md`, `delivery-artifact-gates.md`, `capability-obligations.md` and `cross-system-and-market-claims.md`; presence of a control, graph row, tracking point or planner benchmark is diagnostic only. Claim-critical overlays must be visibly stable in decoded output, semantic evidence ranges must survive the edit, and audio peak safety is measured after final encoding.
16. Run `python scripts/init_rd.py --project <project-root>` if the project has no `.rd/` system. Use `--dry-run` first when scope is unclear.
17. Read [tooling-and-architecture-gates.md](references/tooling-and-architecture-gates.md) for a product that onboards a user's existing Codex／Claude Code or other session-native AI through MCP, even when no repository refactor is requested.
18. State one falsifiable win condition before changing the implementation.

For external test/build tools, a parent shell exit 0 is insufficient evidence that the child started. Prefer `python scripts/command_execution_gate.py --expect-output <marker> --output <receipt.json> --quiet -- <executable> <args...>`; it resolves and hashes the executable, launches without a shell, records the child exit and output identities, and blocks missing commands or absent success markers. On PowerShell, do not trust `$LASTEXITCODE` after a command-not-found error. Windows `.cmd/.bat/.ps1` wrappers are rejected; invoke the exact interpreter plus script entry point and verify its version floor. Do not pass secrets in retained argv.

## Gate external changes before mutation

Treat an external namespace as a closed-world target-resolution problem. Never infer “missing” from one guessed name.

1. Inventory the owner/account/organization namespace and search normalized names, aliases, remotes, URLs, creation dates, releases, and archived resources.
2. Declare one canonical survivor and one exact mutation target. If they are ambiguous, stop before writing.
3. Separate user authorization from technical authorization. Preflight the exact API scope, role, sudo/2FA, login, payment, and interaction surface needed for the final action before starting the workflow.
4. When the user is remote or mobile-only, choose a mobile-completable device flow or defer; do not create a desktop-only handoff at the last step.
5. Run `python scripts/external_change_gate.py <plan.json>` and require `ALLOW` before the first external mutation.
6. After execution, verify authoritative postconditions: the intended target changed, the canonical survivor remains correct, and unrelated resources did not change.
7. Record the preflight, outcome, failure class, and reusable rule in `.rd/EXTERNAL_CHANGES.md` and the experiment/failure ledger.

For destructive cleanup after a duplicate was created, first merge or recover intended work into the canonical history, validate/release it there, archive the duplicate as a reversible intermediate state, then delete only after the deletion capability and final verification path are ready.

## Calibrate the evaluator first

Treat cleanup, benchmark, profiler, linter, test harness, and evidence collectors as measurement instruments.

1. List the failure classes the instrument must detect for this task.
2. Run its self-test and a task-shaped positive/negative fixture.
3. If coverage is missing, improve the instrument first with the smallest deterministic check and regression fixture.
4. Re-run the instrument on itself; it must satisfy its own applicable rules.
5. Freeze its version or SHA and evidence schema before collecting the project baseline.

For the bundled Cleanup and score gates, run `python scripts/regression_corpus.py` when the sibling `code-cleanup-helper` is installed. It exercises the real R&D skill as a positive corpus, a dependency cycle as a negative corpus, and matching versus mismatched benchmark provenance.

Do not tune the tool merely to make findings disappear. Preserve the raw before-report, distinguish a real project improvement from a measurement change, and log evaluator changes as experiments.

For code, skill, and repository evidence, use Cleanup only through the contract adapter:

```powershell
python scripts/run_cleanup_gate.py <project-root> --mode architecture --phase baseline --output <project-root>/.rd/benchmarks/cleanup-baseline.json --quiet
python scripts/run_cleanup_gate.py <project-root> --mode architecture --phase promotion --review-policy block --require-checked 10 --output <project-root>/.rd/benchmarks/cleanup-promotion.json --quiet
python scripts/verify_cleanup_evidence.py <project-root>/.rd/benchmarks/cleanup-promotion.json
```

Choose `a`, `b`, `architecture`, or `all` from the task. The adapter runs the provider self-test, validates one-document JSON, schema, counts, target and mode, freezes evaluator/config hashes, and applies baseline versus promotion semantics. For a repository target, prefer its own `audit.config.json`; the provider skill's config is only for auditing the provider tree. Before a full run, confirm the effective config excludes generated dependencies such as `node_modules`, `dist`, `target`, vendored runtimes and the evidence directory, or treat the resulting inventory explosion as measurement failure rather than product debt. Use `--quiet` only together with `--output` to avoid duplicating a large evidence envelope into an agent transcript; the CLI rejects quiet runs that would discard evidence. Cleanup remains read-only; R&D owns decisions and changes. An explicit original implementation request does not require a second confirmation merely because Cleanup was invoked, while an audit-only request never authorizes modification.

Use `--review-policy block` for explicit full-completion/release closure; ordinary audits retain the default visible REVIEW semantics. Promotion capture performs an immediate second audit when evidence is written inside the target, and rejects a self-referential output unless its directory is excluded by the target config. Re-run `verify_cleanup_evidence.py` after final documentation, packaging, or handoff edits; any changed, added, or removed audited file makes the saved promotion stale.

Source-security and architecture evaluators must follow responsibility ownership after refactors. A check anchored to one historical entry file is stale when the guarded logic moved to a registered module; enumerate the runtime composition or assert the registration edge and scan the complete owned module set. Re-run the evaluator's negative fixture after every such scope change.

Treat the [Cleanup R&D integration contract](../code-cleanup-helper/references/rd-integration.md) as the single source of truth for Cleanup statuses and machine fields. If the adapter returns `MEASUREMENT_BLOCK`, pause production changes, fix Cleanup with positive and negative fixtures, self-audit it, then capture a new baseline. Supplement dynamic imports, plugins, subprocesses, cross-language calls, and runtime dataflow manually because AST evidence cannot prove them absent.

For artifact-producing systems, architecture evaluation is closed-world.  It is not enough to validate packages, rows, or outputs that already exist.  Declare every completed canonical artifact as an obligation and verify that it reaches exactly one authoritative registry/package with matching identity, hash and lifecycle state.  Treat orphan outputs, stale packages, split-brain IDs, non-clickable human entry points and a success path that bypasses registration as correctness failures.  Lock the application edge (for example `Build → publishing control plane`) with a required-dependency fixture plus a runtime positive/negative fixture; static AST alone cannot prove the call completed.

For responsive commerce products, source tests and a DOM `visible` flag are diagnostic only. Normalize same-build browser geometry and dialog lifecycle evidence through `scripts/web_acceptance_gate.py <contract> --root <evidence-root>`. Schema v2 live-hashes the collector implementation, raw browser capture and each replayed negative-control report; a hand-authored list of control names cannot promote. A product dialog must be painted within the viewport above its backdrop, keyboard-contained, closable, scroll-safe and focus-restoring on both desktop and compact layouts. Pair every generated product image with its preserved source identity through Cleanup artifact-set assertions; image count, content quality, disclosure, shipment truth and commercial rights remain separate claims.

For installers and release bundles, the actual delivered envelope is authoritative, not the build-directory executable. Run the project-specific extraction evaluator, then normalize its raw evidence through `python scripts/delivery_contract_gate.py <contract.json> --root <evidence-root>`. Promotion requires closed-world payload comparison, current input/output receipt, raw-byte embedding plus semantic runtime readback, automatic canonical-build wiring, embedded SBOM/notices, a delivered-product journey, and calibrated negative controls. Build and delivered executable hashes may legitimately differ; do not force byte equality across those roles.

Delivered desktop journeys must distinguish product failure, controller failure and cache-state variance. On CDP／WebDriver timeout, invalidate the control connection before retrying; capture page URL, root DOM, `error`, `unhandledrejection` and lifecycle traces before classification. Treat a freshly extracted runtime as its own state: while OS scanning／runtime startup／first library indexing are pending, issue short independent UI heartbeats and require the root, Timeline and primary action to remain usable. Do not await unrelated media, library, model and updater work in one monolithic controller expression; split bounded stages and retain elapsed time plus controller misses so a timeout has stage attribution. Exercise domain-invalid boundary actions and require the editor root to remain mounted with state unchanged plus a visible error. Machine-assert the fixture precondition before classifying the result: a ruler padded to a minimum visual duration makes an arbitrary percentage different from the clip boundary, so seek from an explicit coordinate/time and verify the resulting playhead／state. Assert successful edits through durable project／Autosave／artifact postconditions, not transient shared status copy that another valid background job can overwrite. Cache promotion is a two-step claim: the first staging may be a miss, while an immediate second identical staging must be a hit; never require a cold first run to report `cacheHit=true`.

Give every desktop run isolated application state **and** an isolated browser／WebView user-data root; do not close, attach to, or inherit the operator's running app merely to obtain a debug target. Drive journeys by stable semantic selectors and bounded readiness predicates, not translated display copy or a fixed sleep. For beginner-density gates, count enabled choices and disabled signposts separately, cap both, and retain negative controls for too many active decisions and too much disabled clutter.

For public releases, separate managed-code ownership from user-workspace ownership.  Automatic compatible updates may replace only manifest-owned code through checksum, backup and rollback.  A versioned workspace migration may add missing structure and regenerate indexes, but must preserve media, profiles, credentials, analytics, unknown files and local modifications.  Promotion requires clean-install, compatible N-1 upgrade, second-run idempotency, protected-file, local-modification and rollback fixtures.  Unversioned legacy folders require one explicit adoption before automatic ownership begins.

## Define the claim

Translate “best” or “beat competitor” into a comparison contract:

- Freeze the product surface and target user scenario.
- Name the baseline, candidate, dataset version, devices, and environment.
- Choose primary metrics, guardrail metrics, minimum samples, and promotion thresholds.
- Include negative controls and hard cases.
- Mark unmeasured facts as `unmeasured`; never invent a baseline number.
- Separate system observations from independent ground truth; the candidate cannot label its own answer.
- Mark incomplete evidence as `diagnostic`, never `measured`.

Do not promote a candidate when its dataset differs from the baseline, its test is not blinded, its sample count is below the gate, or any required metric is missing.

For compound cross-system or market claims, keep instrument validity separate from claim closure. A gate may return instrument GREEN because `claimStatus=unmeasured` is honest while the product claim remains BLOCK. Use `scripts/claim_matrix_gate.py`; parity/completion must add `--require-claim-closed`. Component presence, an MCP tool listing, installer membership, architecture, synthetic fixtures or zero measured cells never close the stronger claim.

For model／reasoning routing, freeze every required provider × model version × effort × task-class cell. Markdown may carry a bounded semantic router, but JSON remains the typed execution truth and the receipt binds both hashes. Official positioning is hypothesis evidence only; missing same-provenance cells remain `unmeasured`, and no model identity may bypass schema, rights, truthfulness, security or semantic review.

When a current mutable Skill supplies decisions to a shipped product, prefer a bounded, versioned plan adapter over copying private Skill text or full memory into the installer. Bind the plan to the invocation revision/hash, selected rule IDs and budget counts; preserve private/public separation; then verify the same source identities across executor receipt and real journey.

When a user-selected content type or editorial template is meant to reduce cost, benchmark the full propagation path rather than the picker alone: persisted project schema and migration, resumed batch session, model/MCP handoff, bounded decision search, render fingerprint and delivered reopen. Treat the selection as a strong prior, never as replacement for source analysis. For multi-speaker directing, separate detection claims: two tracked regions plus visual activity are not voice diarization. Promotion requires frozen overlap/silence/lost/low-difference fixtures, uncertainty fallback, switch hysteresis, editable shot graph, preview/render crop parity and an honest same-source competitor holdout before any superiority claim.

When a feature adds a closed-world capability／flow／tool ID, update the machine consumer's fixed required set and replay its positive control plus missing-ID negative control before expensive packaging. Matching producer-side arrays are not sufficient because both can drift together. Treat type-only dependency cycles as architecture failures too: move the shared contract to the lowest owning layer, then replay typecheck, the native dependency graph and the delivered journey.

If the adapter supports legacy schemas, declare `adapterContract.currentSchema`, `legacySchemas` and `requiredCurrentFlowIds`; each current flow records `contractSchema`. Legacy execution is compatibility evidence only. Also enumerate the semantic plan families required by the user promise and add missing-family negative fixtures—a valid generic command list cannot close an editorial, safety, review, publish or outcome workflow by itself. Free/community distribution still requires per-item redistribution provenance.

## Draw the self-authored boundary

When a user says "build it ourselves" or asks to reproduce a public capability, define the ownership boundary before implementation:

- Self-author the product-specific application layer: schemas, timeline/state machines, components, orchestration, domain rules, templates, routing, evaluation gates, migration, QA and release contracts.
- Reuse mature low-level infrastructure when it is not the product differentiator: codecs and containers, image matrices, cryptography, database engines, browser standards, operating-system primitives and hardware drivers. Typical examples include FFmpeg/ffprobe, OpenCV, Pillow and a browser engine.
- Treat competitor frameworks as behavioral benchmarks and interoperability references, not source-code donors or hidden runtime dependencies. Never claim parity from a similar API or demo.
- Record every allowed external primitive and forbidden product-layer dependency in the architecture manifest. The dependency audit must fail when an unapproved framework enters the runtime graph.
- If the user explicitly requires a low-level component to be self-authored too, create a separate benchmark and security plan; do not silently expand "self-authored" into rebuilding an entire standards stack.

Promotion requires tests at both edges: the self-authored application contract must be deterministic, and the low-level engine adapter must prove compatible inputs, outputs, version identity and clean fallback behavior.

## Execute the smallest decisive experiment

1. Keep the current production path as the baseline.
2. Isolate the bottleneck behind a stable interface.
3. Implement the smallest change that can disprove or support the hypothesis.
4. Run correctness checks before performance checks.
5. Run the same benchmark for baseline and candidate.
6. Use `scripts/score_gate.py` to decide pass or fail.
7. Preserve raw evidence or a stable evidence path.
8. Put bounded timeouts around permission-, device-, model-, service-, and network-dependent experiment startup.

Prefer an ugly experiment with strong evidence over a polished system with unknown value.

## Retain learning

After every meaningful attempt, run `scripts/record_experiment.py` or append an equivalent JSON object to `.rd/experiments/ledger.jsonl`.

Record:

- hypothesis and exact change;
- environment and dataset identity;
- metrics and raw evidence path;
- result: `pass`, `fail`, `inconclusive`, or `blocked`;
- failure taxonomy and next decision;
- reusable principle that can transfer to other projects.

Update `.rd/DECISIONS.md` when architecture or defaults change. Update `.rd/FAILURES.md` when a failure pattern should not be repeated.

## Promotion rules

Promote a candidate only when all conditions are true:

- correctness tests pass;
- benchmark provenance matches;
- required gates pass;
- guardrails do not regress;
- rollback remains available;
- evaluation tooling passed self-tests and its task-shaped fixture;
- saved promotion evidence is fresh after the final in-scope mutation;
- the decision and evidence are logged.

If a candidate wins only on some devices or scenarios, ship it behind capability detection or a feature flag. Keep a safe fallback.

## Handoff

For explicit full completion, normalize the final live checks through `scripts/completion_closure_gate.py`. When multiple sessions maintain this Skill or Cleanup concurrently, include strict fresh Cleanup promotions for both canonical private Skill trees in the closure contract after their public mirrors are synchronized. The Cleanup promotion envelope freezes both full Skill revisions in addition to evaluator hashes. A concurrent Skill revision after product promotion invalidates the bundle and requires a latest-version replay; work that exists only in another project copy is outside the canonical revision until it lands.

Report:

- what is now operational;
- what the benchmark actually proves;
- what remains unmeasured;
- the next highest-information experiment;
- where the reusable learning was stored.

Never say “surpassed” from architecture, a demo, or a synthetic test alone.
