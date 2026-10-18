# External agent workflow audit

For external skills/plugins. Cleanup is read-only; [R&D](../../../run-benchmark-driven-rd/references/topics/agent-workflow-adoption.md) owns adoption.

- `cleanup.workflow.origin`: separate author, port maintainer, installed version and local policy; pin source/license. Upstream reputation does not authenticate a port.
- `cleanup.workflow.effective-authority`: inspect instructions, hooks, helpers and dependencies together: external writes, model calls, credentials and persistent routing. Markdown can widen authority without executable code.
- `cleanup.workflow.transitive-scope`: test approved helpers with omitted arguments and home defaults; an allowlist may approve cross-project transcript reads. Use synthetic homes/fixtures, never actual private history.
- `cleanup.workflow.driver-proof`: audit launch/health/drive/evidence/teardown and the feature map against a real user entry. Proof must survive teardown; changed/missing proof must fail. Naming a driver/map is not execution.
- `cleanup.workflow.error-enforcement`: identify ownership and type/schema, lint or behavior-test enforcement; replay the recurring mistake. New prose does not prove prevention. Document judgment-only rules.

Design input: MIT [pstack](https://github.com/cursor/plugins/tree/4382e687a50b8d2c5ce4d141d001186589cff8d5/pstack) verification/correct. Original provisional rules; no upstream runtime; independent replay required.
