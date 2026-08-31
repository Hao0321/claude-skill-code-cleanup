# Architecture and evaluator R&D

- `rd.arch.measured-boundary`: distinguish static inventory, parsed dependency graph, runtime service lookup, cross-language calls, data ownership, and delivered journey. One layer cannot silently stand in for another.
- `rd.arch.required-edge`: declare architecture invariants in project-native config with positive and missing-edge negative fixtures. If an expected edge is absent, fix/calibrate the evaluator before restructuring the product.
- `rd.arch.end-to-end-state`: for a mechanic/capability, trace config/input → state mutation → consumer/UI → persistence/output → reset/migration/reopen. Presence of files or controls is not a closed flow.
- `rd.arch.one-owner`: each state, command, rule, artifact, and learning has one canonical owner; adapters translate versioned contracts rather than duplicate semantics.
- `rd.arch.cleanup-provider`: Cleanup remains read-only and owns its PASS/FAIL/REVIEW/NOT_CHECKED semantics. R&D may apply strict promotion policy but may not rewrite provider `NOT_CHECKED` as PASS.
- `rd.arch.fresh-artifact`: bind generated/packaged artifacts to current input hashes and rebuild receipts; build-directory bytes are not delivered-product authority.

Select `../tooling-and-architecture-gates.md` only for the full legacy architecture/toolchain contract or a rare edge omitted here.

