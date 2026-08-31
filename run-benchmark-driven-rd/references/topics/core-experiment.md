# Core experiment contract

- `rd.core.claim-first`: state the claim, baseline, surface, frozen input, success threshold, serious-error threshold, cost/latency budget, evidence path, and decision before implementation. Missing cells stay `unmeasured`.
- `rd.core.calibrated-evaluator`: prove the evaluator rejects a task-shaped defect and accepts a known-good control. A regex, exit 0, or self-authored label without calibration cannot block or promote work.
- `rd.core.same-provenance`: compare baseline and candidate with the same input, environment, model/effort, evaluator revision, sample policy, and artifact identity. Otherwise report the confound.
- `rd.core.smallest-decisive`: execute the smallest experiment that can change the decision; preserve stdout/stderr, executable identity, exit, timings, artifacts, and failure taxonomy.
- `rd.core.truthful-verdict`: distinguish instrument health, product readiness, parity, and leadership. GREEN tooling with zero measured claim cells proves honest reporting only.
- `rd.core.fresh-decision`: after the final relevant change, rerun the same claim/evaluator/closure gates and bind the decision to current source and artifact hashes.

Use `../protocol.md` and `../metrics.md` as legacy/full-detail references only when the task needs a protocol family or metric not represented by the selected topic cards.

