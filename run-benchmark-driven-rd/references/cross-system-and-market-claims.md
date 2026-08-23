# Cross-system and market claims

Use this contract when a capability spans a mutable Skill or planner, an Agent/MCP boundary, a product runtime, a delivered artifact, human review, publishing, or outcome learning. It also applies to “best”, “beats every product”, competitor parity, lower Token cost, and similar compound claims.

## Presence is not integration

A directory, module, Skill, installer payload, tool name, or passing unit test proves only that one component exists. A cross-system flow is verified only when one frozen journey proves every required stage using the same source identities:

1. current planner/Skill revision and SHA-256;
2. bounded handoff contract and negative controls;
3. executor receipt and atomic state change;
4. real output or delivered-product evidence;
5. review/publish/outcome state when those stages are part of the claim.

Keep required flow IDs and required stage IDs closed-world. Split functional execution from human quality acceptance. A machine gate may honestly validate `unmeasured`; that is instrument GREEN with claim closure BLOCK, not product parity.

## Mutable instruction sources

Do not freeze a private Skill or its full memory into a public installer merely to claim integration. Prefer a versioned, bounded adapter:

- load the canonical current Skill at invocation time;
- carry source revision/hash in the plan receipt;
- carry selected rule IDs and budget counts, not the whole private memory;
- let the product validate a stable schema and execute deterministic commands;
- verify the invocation revision again before the final decision.

If product execution depends on the Skill bytes but no receipt identifies those bytes, the integration is `unmeasured`. If the Skill changes after evidence capture, rerun the affected journey.

### Current schema is an obligation

Backward compatibility and current-workflow closure are different claims. When a product accepts both current and legacy handoffs, declare an optional `adapterContract` in the claim matrix:

```json
{
  "adapterContract": {
    "currentSchema": "product.plan/v2",
    "legacySchemas": ["product.plan/v1"],
    "requiredCurrentFlowIds": ["longform", "shorts"]
  }
}
```

Each required current flow carries `contractSchema`. A legacy schema may remain executable, but it cannot close a current integration flow; `claim_matrix_gate.py` rejects this as `adapter-legacy-flow`. Also require semantic fields needed by the user promise—not only a generic command array. For an editorial system that normally includes source/knowledge receipt, brief, promise/stakes/payoff, ordered beats, packaging hypotheses, caption/graphics separation, motivated transitions, layered audio, review state, artifact lifecycle and outcomes. Exact fields are product-defined, but missing required semantics must fail before execution.

Research-derived policy must label direct source observation separately from inference. One interview, competitor video, UI card or course title can create a hypothesis, not a permanent preference or measured parity result.

### Model and context provenance

Model identity and reasoning effort are runtime provenance, not a trust level. If a flow adapts across Sol／Terra／Luna or effort settings, every receipt must preserve provider, model/version, effort, task class, route policy, bounded context hash and evaluation state. Markdown may provide a readable semantic router, but the executable handoff remains a versioned JSON schema and typed command list.

Treat each model × effort cell as `unmeasured` until the same frozen content, Skill revision, context packet, evaluator, environment and cost window are replayed. Official positioning and anecdotal success can select initial candidates but cannot close quality, latency, Token, cost or parity claims. A model name or high effort must never bypass current schema, redistribution rights, truthfulness, security or semantic audit. Use [model-and-reasoning-gates](model-and-reasoning-gates.md) for promotion requirements.

## Market matrix

Translate a market claim into baseline × surface cells. Freeze competitor/product versions, source media, brief, devices, dataset, evaluator and cost window. Each measured cell needs independent ground truth, minimum samples and replayable evidence. Diagnostic or synthetic results remain open. Required surfaces normally include beginner completion, editorial quality, caption quality, tracking, programmable composition, render performance, cross-device workflow, reliability/recovery and Agent Token/API cost.

Do not average away a missing must-pass cell. “Wins overall” remains `unmeasured` until every required cell is measured and all guardrails pass.

Free or community distribution still crosses a redistribution boundary. Do not treat zero price as rights evidence for music, SFX, fonts, stock, models, codecs or generated/source assets; preserve a separate blocked-external obligation until per-item provenance permits redistribution.

## Professional media workstation flows

Keep five closed-world flow IDs instead of one broad “professional editor” checkbox:

1. Timeline: current-schema project → indexed/virtualized viewport → real pointer/keyboard edits → visible state → Undo/Redo → save/reopen in the extracted product.
2. Typography: licensed font source/hash → build receipt/SBOM/notices → extracted payload → runtime resolver → actual renderer selection → decoded output.
3. Color: source metadata → explicit input transform/rejection → primary grade → exactly one look → graphics/output transform → decoded-frame/scopes evidence.
4. Director review: persisted timecode markers/notes/status → save/reopen/Undo → authenticated human action where approval is claimed.
5. Native automatic composition: evidence-backed preserve ranges and creative-family decisions → atomic editable graph → decoded visible overlays/tracked safe-area behavior → final encoded loudness/true-peak evidence → human review state.

Planner latency, installer membership, source-preview scopes and automated `ready_for_review` states cannot close those end-to-end flows. Multi-user live collaboration, HDR/reference-monitor fidelity and market parity remain separate cells even after the local delivered workflows pass.

## Gate

```powershell
python scripts/claim_matrix_gate.py <contract.json> --root <project-root>
python scripts/claim_matrix_gate.py <contract.json> --root <project-root> --require-claim-closed
python scripts/claim_matrix_gate.py --self-test
```

The default command validates that the instrument and the declared claim state agree. Add `--require-claim-closed` for parity promotion or completion closure. Persist the output and bind its hash into the completion contract after the final mutation.
