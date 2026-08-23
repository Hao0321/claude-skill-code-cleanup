# Tooling calibration and architecture gates

## Table of contents

1. Evaluator contract
2. Calibration loop
3. Architecture baseline
4. Refactor promotion gate
5. Knowledge-system gates
6. Durable learning

## 1. Evaluator contract

Before changing production, state what the evaluator must observe, what it cannot observe, its evidence schema, and the fixture that proves each required detector works. Treat an untested detector as `unmeasured`.

When `code-cleanup-helper` supplies repository evidence, its `references/rd-integration.md` contract is the sole source of truth for schema and status semantics. Consume it through R&D's `scripts/run_cleanup_gate.py`; do not restate or override provider thresholds in this file.

The evaluator's own aggregation and serialization are part of that contract. Score denominators must be derived from the current checks rather than a historical constant, critical failures must remain independent of the numeric score, and a JSON mode must emit exactly one parseable JSON document. A false perfect score or machine-unreadable report is a measurement failure, not a cosmetic bug.

For cleanup and architecture work, required detector families commonly include:

- exact duplicate and duplicate implementation;
- module dependency edges and strongly connected components;
- repository-defined layer or forbidden-edge violations;
- fan-in／fan-out hotspots and oversized functions;
- public/private drift, broken links, release metadata, and privacy leakage;
- dynamic registration, plugin loading, subprocess, file protocol, and cross-language edges when present.

Static AST can measure only syntactic imports and code shape. It cannot prove runtime call direction, ownership, correctness, or the absence of dynamic edges.

An empty or implausibly sparse dependency graph is not automatically clean. When the task has a known internal import, declare it as a required edge. For Python tools that run files directly, calibrate bare sibling imports separately from package imports: the positive fixture must resolve the sibling, while negative controls must preserve a real root module and must not turn standard-library／external imports into the package facade.

## 2. Calibration loop

1. Run the evaluator self-test.
2. Create or reuse one task-shaped fixture containing at least one known positive and one negative control.
3. Confirm the raw report identifies the positive and leaves the negative clean.
4. If a required failure is invisible, improve the evaluator before the product.
5. Add a regression fixture for every evaluator bug fixed.
6. Run the evaluator on its own code and resolve applicable severe findings.
7. Hash or version the evaluator and save the schema with the baseline. For Skill-backed evaluators, also freeze the complete canonical private Skill-tree revision through Cleanup's revision provider; a script-only hash cannot prove that current instructions and routed references were used.
8. Mutate the fixture count or add one failing check and verify the normalized score decreases; pipe JSON output into a real parser and require zero trailing data.

Record the interpreter launch mode as part of evaluator provenance. On Windows or any non-UTF-8 locale, use `python -X utf8` (or an equivalent explicit UTF-8 mode) for validators that read UTF-8 skill／report files. A locale decoding traceback is a tooling-launch measurement failure, not evidence that the product passed or failed; fix the launch environment, rerun the identical validator, and retain the successful command.

Treat process launch as a measured gate of its own. A parent shell exit code is not proof that the requested executable started: PowerShell command-not-found can be non-terminating and leave a stale `$LASTEXITCODE`. For promotion commands, either run `scripts/command_execution_gate.py` or resolve the executable explicitly, use shell-free process creation, retain its invocation path, physical target/hash, child exit code and an expected success marker. Preserve the invocation path for alias-sensitive proxy executables such as Rustup's `cargo` symlink; following the link and launching its physical target can change behavior. Missing executables, timeouts, absent markers and non-zero child exits are `measurement` failures. Never accept a wrapper's zero exit after a launch error, and never place secrets in a retained command argv.

Interpreter identity is part of launch identity. On Windows, `.cmd`, `.bat` and `.ps1` are shell wrappers even when a subprocess API reports `shell=False`; invoke the exact `node.exe`, `python.exe` or other interpreter plus its script entry point instead. Verify the interpreter version against the repository floor before accepting downstream tests. Hashing `npm.cmd` while it silently selects an older sibling `node.exe` is not valid runtime provenance.

Runtime-gated built-ins belong to the same contract. If a harness uses a global API introduced at the declared runtime floor (for example Node's global `WebSocket`), a failure under an older launcher is a measurement-launch failure, not a product regression and not a pass. Preserve that failed attempt, replay the identical harness through the exact compliant interpreter, and bind the successful child-level receipt. This does not establish compatibility with the older runtime; it establishes that promotion evidence came from the supported one.

Never relax a threshold or add an ignore rule without a written semantic reason. A quieter report is not automatically a better instrument.

Desktop controller fixtures need two independent isolation layers: product state such as recovery／batch／credentials, and browser-engine state such as a WebView2 user-data folder. Reusing the operator profile can attach to a pre-existing browser process, silently ignore the requested debug port, or force the harness to kill a user-owned session. Treat that as a measurement bug. Readiness must be an observable predicate (for example, onboarding action completed and lazy panels interactive) with a wall-clock deadline; localized button text and fixed millisecond sleeps are diagnostics only. Probes must tolerate a missing initial `document.body`, then wait for the route-specific lazy landmark before measuring first-run onboarding or density; a toolbar mount is not evidence that the lazy welcome/editor surface is ready. UI-density evaluators should retain the full visible-control inventory but score enabled decisions and disabled workflow signposts independently, with calibrated over-budget fixtures for each.

Repository cleanup runs use the repository's `audit.config.json`; provider configs are not portable project configs. Sanity-check the effective inventory size and generated-directory exclusions before accepting a full-scan result. After extracting a security-sensitive responsibility from an entry file, update the evaluator's source inventory in the same change, scan the composed runtime ownership set, and keep a negative fixture that fails when the extracted module is omitted.

If the evaluator itself is insufficient, use this stop-the-line sequence: record the missed failure class, preserve the misleading report, improve the evaluator, add positive and negative fixtures, self-audit the tool, freeze the new SHA/schema, then restart the product baseline. Do not continue a refactor with a known-blind instrument.

Consume Cleanup's `FAIL`, `REVIEW`, and `NOT_CHECKED` exactly as its provider contract defines them. Treat a contract mismatch as a measurement failure rather than translating statuses locally.

Ordinary REVIEW findings remain advisory. An explicit full-completion or release-closure claim uses the adapter's strict review policy and cannot promote with unresolved REVIEW. After the last mutation, replay the saved Cleanup envelope with `verify_cleanup_evidence.py`; stale bytes or file-set changes invalidate the earlier decision.

## 3. Architecture baseline

Freeze:

- module inventory and internal dependency edges;
- cycle and layer-violation counts;
- public CLI／API compatibility surface;
- correctness and health-test results;
- public/private sync status;
- evaluator SHA, config SHA, and raw report path.

Define layers from actual responsibilities, not folder names alone. A useful direction is domain/policy → application/orchestration → adapters/infrastructure → interfaces, but repository evidence decides the final contract.

## 4. Refactor promotion gate

Promote only if:

- correctness, health, packaging, install, and upgrade tests remain green;
- no new dependency cycle or forbidden edge appears;
- the targeted cycle, duplicate responsibility, or hotspot improves by the declared threshold;
- compatibility façades preserve public imports and CLI behavior where required;
- rollback exists and raw before/after evidence uses the same evaluator version and config.

When the evaluator changes during the work, rerun both the original and new evaluator when possible. Do not compare counts across different measurement semantics as if they were the same metric.

### Artifact-lifecycle closure

For systems that render media, export documents, build releases, generate datasets or emit publishable artifacts, add a closed-world lifecycle gate:

- enumerate canonical completed artifacts independently of the registry;
- require exactly one authoritative package/row for each artifact;
- compare content hash, canonical source identity and lifecycle status;
- fail on orphan outputs, stale packages, duplicate IDs and packages pointing to superseded sources;
- require a human-facing entry point whose links resolve to the actual artifact and its release metadata;
- keep published packages immutable; status changes on unpublished artifacts relocate one package instead of cloning it.

The task-shaped fixture needs an orphan positive, a correctly registered control, a stale-package positive and an unrelated-working-file negative.  A package-only validator is explicitly not sufficient evidence.

For a distributable envelope, additionally apply [delivery-artifact-gates.md](delivery-artifact-gates.md). Keep raw-byte embedding claims separate from semantic JSON identity: exact bytes prove an embedded receipt, while field comparison tolerates harmless key ordering during cross-language runtime readback. The actual extracted executable is authoritative even when a packager has legitimately changed its bytes from the build-directory executable.

### Public upgrade closure

Treat a public updater and workspace migrator as separate transactions.  The updater owns only release-manifest files; the migrator may create missing generated structure but cannot overwrite protected or unknown user data.  Require:

- archive and per-file checksum verification;
- explicit compatibility and idempotent migration declaration;
- managed-file local-modification detection;
- backup plus executable rollback;
- clean install, compatible old-version upgrade, second-run no-op and incompatible/legacy confirmation fixtures;
- independent post-install architecture, privacy and health audits.

Never claim that existing users auto-upgrade merely because a release archive exists.  Prove that a normal entrypoint checks the channel at a bounded interval and that the migration result is surfaced without silently continuing under stale loaded code.

## 5. Knowledge-system gates

### Session-native AI + local tool gate

For products controlled from a user's existing AI session, benchmark the structured path before Computer Use. Freeze source media, project revision, host CLI versions, MCP server version, Skill／knowledge hashes and material-analysis options. The minimum positive journey is local SHA-256／scene analysis → MCP image keyframes → bounded transcript window → evidence-cited semantic receipt → current structured plan → audit → atomic editable apply. Negative controls must reject a changed source, unknown frame/cue ID, tampered semantic receipt, missing current-plan material evidence and a command that would alter original source identity.

Track local analysis latency/cache hit, model-visible frames, transcript/context bytes or tokens, MCP round trips, schema rejection/repair count, apply latency and post-apply editability. Do not compare this with Computer Use unless both operate on the same frozen task and include end-state correctness; fewer clicks alone is not quality, while a correct structured journey normally has the stronger latency/Token prior.

Onboarding is a separate delivery and UX gate. Start from a fresh profile: the connection entry must be visible without opening a generic overflow menu, explain that login／billing stays with the host session, and never ask for provider API keys. Run the actual Codex／Claude CLI against isolated temporary config roots and inspect written user-level STDIO command／args／env. Include Windows paths with spaces, npm shim resolution, an absent CLI, an exact existing configuration and a stale configuration under the same canonical server ID. Never delete or rewrite a differently named server.

Do not promote from the setup command's exit code. After every no-op or write, call the provider's official `get`／`list` surface and compare the read-back executable, MCP entry, args and environment with the candidate. Preserve provider semantics: a client that only exposes configuration inspection may be `configured`; report `connected` only when a real MCP initialize／tools handshake or authoritative client health signal succeeds. Fail if the adapter silently accepts a rejected argument shape, stale path, unhealthy server, copied fallback command or unverified configuration as connected.

The positive journey continues after technical setup: show whether a restart or new session is required, provide one copyable bounded starter task, and prove the next session can discover and invoke the expected Editkin-style tool flow. The manual fallback must identify the missing stage in plain language, copy only a deterministic secret-free command, give a read-back verification step, and allow retry without duplicate registrations. Record fresh-profile findability, setup completion rate, p50／p95 time, retries, CLI/provider versions, health state and first-tool success separately; fewer clicks without a working first task is a product failure.

Skills, prompt systems, analytics ledgers, and other knowledge-heavy repositories need gates beyond code shape:

- **Canonical facts**: mutable outcomes live in one structured ledger. Prose may explain or link; it must not become a second current-value database.
- **Generated views**: indexes, summaries, and registries are reproducible from canonical sources. Lifecycle status must be explicit metadata, never inferred from nearby prose or emoji.
- **Context budget**: measure the required lines／tokens for the common route before and after. A refactor that keeps every archive in the default read path has not improved operational efficiency.
- **Versioned learning**: experiments append revisions instead of overwriting history; identifiers must remain unique under same-tick／concurrent writes; rule promotion has reciprocal experiment↔rule links and an explicit evidence state.
- **Write safety**: any read-modify-write ledger path has a concurrent-writer fixture. Silent lost updates are a correctness failure even when single-process tests pass.
- **Public export**: use a config-driven allowlist, dry-run it, and audit the exported artifact independently. A green private copy does not prove the public package installs or tests cleanly.
- **Canonical external target**: inventory the namespace before create/update/delete; pin owner, resource ID, URL, remote, creation time, release history, and survivor/target roles. One guessed 404 is not an inventory.
- **External authorization**: prove the exact final operation is technically authorized before starting. Write/update scope does not imply delete/transfer/admin/sudo scope.
- **Remote interaction**: record whether the user is at the desktop, remote, or mobile-only. A required confirmation flow must be completable on that surface before mutation begins.
- **External postconditions**: query an authoritative API after the action. For deduplication, require target absence plus canonical survivor presence, correct visibility/default branch/latest release, and no unintended resource mutation.

For this class of system, declare a promotion gate such as: no duplicated live metrics in prose, common-route context reduced by a stated threshold, revision and concurrency tests green, generated indexes reproducible, private/public audits clean, and rollback evidence retained.

## 6. Durable learning

Record evaluator changes in the experiment ledger with `failureType=measurement`. Put stable architecture boundaries and rollback rules in `.rd/DECISIONS.md`; put misleading metrics, missed dependency types, and ineffective abstractions in `.rd/FAILURES.md`.
