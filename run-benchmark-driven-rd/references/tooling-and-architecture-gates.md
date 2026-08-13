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
7. Hash or version the evaluator and save the schema with the baseline.
8. Mutate the fixture count or add one failing check and verify the normalized score decreases; pipe JSON output into a real parser and require zero trailing data.

Never relax a threshold or add an ignore rule without a written semantic reason. A quieter report is not automatically a better instrument.

If the evaluator itself is insufficient, use this stop-the-line sequence: record the missed failure class, preserve the misleading report, improve the evaluator, add positive and negative fixtures, self-audit the tool, freeze the new SHA/schema, then restart the product baseline. Do not continue a refactor with a known-blind instrument.

Consume Cleanup's `FAIL`, `REVIEW`, and `NOT_CHECKED` exactly as its provider contract defines them. Treat a contract mismatch as a measurement failure rather than translating statuses locally.

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
