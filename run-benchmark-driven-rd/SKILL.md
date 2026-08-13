---
name: run-benchmark-driven-rd
description: Turn ambitious or uncertain engineering goals into a falsifiable, benchmark-gated R&D system with calibrated evaluation tools, architecture gates, external-change safety, and reusable experiment memory. Use when the user says 做到最好, 全面重構, 架構最優, 超越競品, 自己研發, 研發系統, benchmark, R&D, improve recognition or performance, retain all learning, or asks to build a capability that must compound across future projects. Also use for public release, 開源, 發版, or creating, renaming, publishing, archiving, deleting, transferring, or changing permissions on external resources when canonical-target mistakes or duplicate projects must be prevented.
---

# Run Benchmark-Driven R&D

Build evidence before making superiority claims. Preserve every useful result as a reusable engineering asset.

## Start

1. Read the repository truth: architecture, dependencies, existing tests, performance paths, and local instructions.
2. Read [protocol.md](references/protocol.md).
3. Read [tooling-and-architecture-gates.md](references/tooling-and-architecture-gates.md) and the [Cleanup R&D integration contract](../code-cleanup-helper/references/rd-integration.md) for architecture work, cleanup, refactors, release readiness, or when the evaluator may be incomplete.
4. Read [metrics.md](references/metrics.md) when the work involves computer vision, latency, reliability, or competitor comparison.
5. Read [mobile-product-engineering.md](references/mobile-product-engineering.md) when the work involves mobile UI, responsive web, PWA, touch, safe areas, mobile navigation, virtual keyboards, or mobile performance.
6. Read [external-change-gates.md](references/external-change-gates.md) before creating, renaming, publishing, archiving, deleting, transferring, or changing permissions on GitHub, cloud services, app stores, domains, databases, automations, or other external systems.
7. Run `python scripts/init_rd.py --project <project-root>` if the project has no `.rd/` system. Use `--dry-run` first when scope is unclear.
8. State one falsifiable win condition before changing the implementation.

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
python scripts/run_cleanup_gate.py <project-root> --mode architecture --phase baseline --output <project-root>/.rd/benchmarks/cleanup-baseline.json
python scripts/run_cleanup_gate.py <project-root> --mode architecture --phase promotion --require-checked 10 --output <project-root>/.rd/benchmarks/cleanup-promotion.json
```

Choose `a`, `b`, `architecture`, or `all` from the task. The adapter runs the provider self-test, validates one-document JSON, schema, counts, target and mode, freezes evaluator/config hashes, and applies baseline versus promotion semantics. Cleanup remains read-only; R&D owns decisions and changes. An explicit original implementation request does not require a second confirmation merely because Cleanup was invoked, while an audit-only request never authorizes modification.

Treat the [Cleanup R&D integration contract](../code-cleanup-helper/references/rd-integration.md) as the single source of truth for Cleanup statuses and machine fields. If the adapter returns `MEASUREMENT_BLOCK`, pause production changes, fix Cleanup with positive and negative fixtures, self-audit it, then capture a new baseline. Supplement dynamic imports, plugins, subprocesses, cross-language calls, and runtime dataflow manually because AST evidence cannot prove them absent.

For artifact-producing systems, architecture evaluation is closed-world.  It is not enough to validate packages, rows, or outputs that already exist.  Declare every completed canonical artifact as an obligation and verify that it reaches exactly one authoritative registry/package with matching identity, hash and lifecycle state.  Treat orphan outputs, stale packages, split-brain IDs, non-clickable human entry points and a success path that bypasses registration as correctness failures.  Lock the application edge (for example `Build → publishing control plane`) with a required-dependency fixture plus a runtime positive/negative fixture; static AST alone cannot prove the call completed.

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
- the decision and evidence are logged.

If a candidate wins only on some devices or scenarios, ship it behind capability detection or a feature flag. Keep a safe fallback.

## Handoff

Report:

- what is now operational;
- what the benchmark actually proves;
- what remains unmeasured;
- the next highest-information experiment;
- where the reusable learning was stored.

Never say “surpassed” from architecture, a demo, or a synthetic test alone.
