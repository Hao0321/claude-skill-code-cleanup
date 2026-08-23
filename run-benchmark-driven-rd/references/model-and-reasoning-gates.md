# Model、reasoning effort 與 context gate

Use this contract when a product routes work across Sol／Terra／Luna, varies reasoning effort, claims Markdown improves accuracy, or claims lower Token cost／higher quality across model settings.

## Separate positioning from evidence

Official model positioning can choose a starting candidate; it is not product evidence. Treat every provider × model version × reasoning effort × task class as a separate benchmark cell. Keep it `unmeasured` until the same frozen dataset, Skill revision, context packet, evaluator, environment and cost window are replayed.

Do not infer that a higher effort always wins. Measure schema adherence, semantic rejection, blind editorial score, repair count, input/output/reasoning tokens, latency and cost. A cell may win on latency and lose on editorial quality; preserve the vector instead of averaging away a must-pass guardrail.

## Markdown plus typed execution

Markdown improves hierarchy and human/model readability but does not intrinsically guarantee correctness. Use a bounded Markdown semantic router for goals, selected rules and decision order. Hash it and bind it to a versioned JSON execution contract containing source identity, timecodes, commands, model／effort provenance, safeguards and receipt state.

Calibration must reject:

- a Markdown-only plan that has no typed execution contract;
- a model identity or high effort bypassing current schema, rights, truthfulness, security or semantic audit;
- a `measured` cell without suite ID, raw evidence, evaluator SHA and promotion receipt;
- comparison across different content, Skill/context revisions or cost windows;
- direct apply from an unmeasured model on editorial／quality／audit／publish-adjacent work.

## Safe initial routing

When no product benchmark exists, record the route as `official_positioning_only_quality_unmeasured`. A reasonable hypothesis is Luna medium for bulk low-risk work, Terra medium for balanced assembly, Sol medium for editorial planning and Sol high for critical audit. These remain defaults to test, not claims to ship. Escalate to xhigh／max only after measured marginal gain justifies latency and cost.

Require a second semantic pass for critical editorial work. Permit one bounded repair against explicit rejection evidence; a second failure escalates to human review instead of consuming unbounded Token.

## Promotion

Freeze the full matrix and closed-world required cells. Promotion requires correctness, raw evidence, same-provenance replay, cost accounting, evaluator self-tests and a fresh receipt after the final relevant mutation. A truthful zero-measured-cell matrix can make the instrument GREEN while the model-quality claim remains BLOCK.
