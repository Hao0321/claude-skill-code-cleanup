# Bounded context and continuous learning

Smaller context is not permission to forget. The runtime has three layers: a small invariant/router entrypoint; bounded, hash-addressed topic cards; and project-local raw `.rd/` evidence that contributes zero default prompt Tokens.

- `rd.context.typed-route`: routing input includes task intent, stage, artifact, claim/risk, open obligations, recent failure IDs, and a Token ceiling. Output records selected/omitted applicable topics, reasons, live hashes, exact/estimated cost, critical rule IDs, and fallback reason.
- `rd.context.critical-fallback`: unknown or ambiguous intent, stale hash, malformed index, or budget overflow cannot silently drop an applicable critical rule; block or use the declared legacy-compatible route.
- `rd.learning.local-first`: raw observations, project names/paths, private metrics, logs, and evidence remain in the target repo `.rd/`; retrieve them only by explicit record/evidence ID.
- `rd.learning.typed-record`: records state topic, scope, privacy, applicability/exclusions, environment/dataset, rule/fixture IDs, failure taxonomy, evidence state, expiry, next decision, and promotion state.
- `rd.learning.promote-with-proof`: one project may create `provisional`; shared `active` needs two independent projects or one project plus a general regression replay. Shared `core` is reserved for broadly applicable safety/truth invariants. Every promoted rule has one owner, live hash, positive/negative fixtures, and reciprocal experiment receipt.
- `rd.learning.no-delete`: demotion/supersession removes a rule from the active index, not from raw evidence. Old entrypoints and migration mappings remain hash-addressed for legacy fallback.
- `rd.context.quality-separate`: Token/latency improvement and task quality are separate claims. Report measured recall/verdict parity separately from likely but unmeasured real-world quality.

Default selection should remain bounded (normally at most five cards). Users may explicitly request the full route; privacy and critical-rule gates still apply.

