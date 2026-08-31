# Modular project system

Cleanup and R&D are integrated but intentionally remain separate products:

- **Cleanup is the read-only measurement kernel.** It inventories code, prompts, Skills, repositories, releases, configuration, generated assets, dependencies, privacy and evidence freshness.
- **R&D is the decision and learning orchestrator.** It defines falsifiable claims, calibrates evaluators, captures baselines, changes the product, records experiments, closes capabilities and controls release mutations.
- **Project modules are the composition layer.** They route only the gates needed by a Skill, website, database, game, software product or mixed system.

Do not merge Cleanup into the mutating orchestrator. Independent measurement is a useful fault boundary: an audit-only request stays read-only, evaluator defects remain distinguishable from product defects, and a project cannot silently rewrite its own judge.

## Project contract

Place an optional `.rd/project.json` in the project:

```json
{
  "schemaVersion": 1,
  "autoDetect": true,
  "projectTypes": ["web", "database"],
  "modules": ["public-release", "security"],
  "projectGates": ["native-js-architecture-gate"],
  "evidenceBindings": {
    "native-js-architecture-gate": "scripts/native_js_gate.mjs",
    "native-js-architecture-receipt": ".rd/receipts/native-js-architecture.json"
  }
}
```

`projectTypes` accepts `skill`, `web`, `database`, `game`, and `software`. `modules` adds cross-cutting overlays: `public-release`, `security`, `media`, or `commerce`. Mixed products compose several types; they do not invent a giant catch-all profile.

`projectGates` is a unique list of project-native gates that the shared profile cannot infer. `evidenceBindings` is a string-only map to the evaluator or receipt that closes each native gate. Keep evaluator limitations explicit—for example, a native JavaScript graph may supplement Cleanup while Cleanup's own cross-language result remains `NOT_CHECKED`. Neither field is evidence by itself.

Run:

```bash
python scripts/project_profile_gate.py --project <root> --contract <root>/.rd/project.json --output <root>/.rd/project-route.json --quiet
```

The frozen route identifies selected modules, Cleanup mode, references, gates, detection evidence, profile hash, contract hash and project evidence bindings. An unknown module, duplicate project gate, malformed evidence binding or unsupported schema blocks routing. The route is a reproducible plan, not proof that its gates passed.

## Continuous learning boundary

Every project keeps raw observations, experiments, failures and decisions in its own `.rd/` workspace. Only a learning that is anonymized, replayable, useful across project types and supported by positive plus negative fixtures may modify the shared Cleanup or R&D Skills. Personal data, customer data, credentials, proprietary source and project-specific conclusions never become shared memory or public examples.

The loop is:

1. compose a project route;
2. calibrate only the selected evaluators;
3. capture a Cleanup baseline through the R&D adapter;
4. implement and benchmark one candidate;
5. append project-local evidence and failure memory;
6. promote generic detector or protocol improvements to the shared Skills with regression fixtures;
7. recapture the active Skill revisions and rerun affected promotion gates;
8. publish only after privacy, capability, canonical-target and remote-hash closure.

This makes learning cumulative without letting one project silently contaminate another project's truth.
