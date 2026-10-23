# Bounded context and continuous learning

Layers: invariant/router entrypoint; bounded hash-addressed cards; explicit-only project-local `.rd/` raw evidence (zero default prompt Tokens). Smaller cannot mean forgotten.

- `rd.context.typed-route`: input: intent, stage, artifact, claim/risk, open obligations, recent failure IDs, Token ceiling. Output: selected/omitted applicable topics, reasons, live hashes, exact/estimated cost, critical rule IDs, fallback reason.
- `rd.context.critical-fallback`: unknown or ambiguous intent, stale hash, malformed index, or budget overflow cannot silently drop an applicable critical rule; block or use the declared legacy-compatible route.
- `rd.learning.local-first`: raw observations, names/paths, private metrics, logs and evidence stay in the target repo `.rd/`; retrieve only by explicit record/evidence ID.
- `rd.learning.typed-record`: records state topic, scope, privacy, applicability/exclusions, environment/dataset, rule/fixture IDs, failure taxonomy, evidence state, expiry, next decision, and promotion state.
- `rd.learning.promote-with-proof`: one project permits `provisional`; shared `active` needs two independent projects or one plus a general regression replay. `core`: broad safety/truth invariants only. Each promotion needs one owner, live hash, positive/negative fixtures and reciprocal experiment receipt.
- `rd.learning.no-delete`: demotion/supersession removes a rule from the active index, not from raw evidence. Old entrypoints and migration mappings remain hash-addressed for legacy fallback.
- `rd.context.quality-separate`: separate Token/latency gains from task quality, and measured recall/verdict parity from unmeasured real-world quality.
- `rd.context.intake`: separate host mandates, startup catalog and selected detail; [Cleanup intake](../../../code-cleanup-helper/references/context-intake.md) uses this Skill's manifest. Never skip mandatory reads or equate disk receipts with resident context.

Default: at most five cards normally. Explicit full-route requests still obey privacy and critical-rule gates.

