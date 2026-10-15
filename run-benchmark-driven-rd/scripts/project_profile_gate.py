#!/usr/bin/env python3
"""Compose a project-specific R&D route from reusable product modules."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any
from project_profile_contract import (
    ROOT,
    DEFAULT_PROFILE,
    MODE_ORDER,
    TASK_FIELDS,
    SECURITY_CAPABILITY_IDS,
    ProfileError,
    load_json,
    sha256,
    sha256_json,
    validate_string_list,
    validate_security_assessment_policy,
    validate_profile,
    package_dependencies,
    detect_project_types,
    validate_contract,
    validate_context_budget,
    validate_task_value,
    unique,
    infer_artifact,
)

from project_profile_routing import (
    resolve_task_inputs,
    build_update_obligation,
    build_security_assessment_obligation,
    reference_bundle,
    aggregate_topics,
    resolve_project_composition,
    select_route_topics,
    build_context_budget_receipt,
    apply_task_safety_floors,
)

def _build_route_receipt(cleanup_mode, composition, context_budget, contract, contract_path, critical_rule_ids, declared_budget, fallback_reason, gates, legacy_bundle, legacy_gates, legacy_references, profile, profile_path, project_types, references, required_capability_ids, root, routing_mode, selected, selected_bundle, selected_task_ids, selected_topic_ids, task, task_sources, topic_selection_reasons):
    profile_hash = sha256(profile_path)
    contract_hash = sha256(contract_path) if contract_path else None
    routing_input = {
        "profileSha256": profile_hash,
        "contractSha256": contract_hash,
        "projectRoot": str(root),
        "projectTypes": project_types,
        "selectedModuleIds": selected,
        "task": task,
        "taskSources": task_sources,
        "routingMode": routing_mode,
        "fallbackReason": fallback_reason,
        "selectedTaskIds": selected_task_ids,
        "selectedTopicIds": selected_topic_ids,
        "topicSelectionReasons": topic_selection_reasons,
    }
    route = {
        "schemaVersion": 2,
        "routerVersion": "2.0",
        "decision": "ROUTED",
        "routingMode": routing_mode,
        "fallbackReason": fallback_reason,
        "evidenceStatus": "NOT_EVALUATED",
        "selectionOnly": True,
        "projectRoot": str(root),
        "projectTypes": project_types,
        "selectedTaskIds": selected_task_ids,
        "selectedModuleIds": selected,
        "selectedModules": selected,
        "selectedTopicIds": selected_topic_ids,
        "topicSelectionReasons": topic_selection_reasons,
        "unselectedTopicIds": [topic_id for topic_id in profile["topics"]
                               if topic_id not in selected_topic_ids],
        "task": {**task, "sources": task_sources},
        "detectionEvidence": composition["detectionEvidence"],
        "cleanup": {"provider": "code-cleanup-helper",
                    "adapter": "scripts/run_cleanup_gate.py", "mode": cleanup_mode,
                    "promotionReviewPolicy": "block"},
        "references": references,
        "selectedReferenceHashes": {item["reference"]: item["sha256"]
                                    for item in selected_bundle["identities"]},
        "legacyReferences": legacy_references,
        "legacyReferenceHashes": {item["reference"]: item["sha256"]
                                  for item in legacy_bundle["identities"]},
        "excludedLegacyReferences": [item for item in legacy_references
                                     if item not in references],
        "gates": gates,
        "legacyGates": legacy_gates,
        "criticalRuleIds": critical_rule_ids,
        "requiredCapabilityObligationIds": required_capability_ids,
        "declaredContextBudgetTokens": declared_budget,
        "contextBudget": context_budget,
        "gateEvidence": {"status": "NOT_EVALUATED", "routeOnly": True,
            "statement": "This route selects obligations; it does not claim any gate passed."},
        "memory": {"projectLocal": ".rd/experiments/ledger.jsonl",
            "sharedPromotionRule": "Only anonymized, replayable, cross-project learning may change the shared Skills."},
        "profile": {"schemaVersion": profile["schemaVersion"], "sha256": profile_hash},
        "hashes": {
            "profileSha256": profile_hash,
            "contractSha256": contract_hash,
            "routingInputSha256": sha256_json(routing_input),
            "selectedTopicsSha256": sha256_json(selected_topic_ids),
            "selectedReferencesSha256": selected_bundle["sha256"],
            "legacyReferencesSha256": legacy_bundle["sha256"]
        },
    }
    if contract_path:
        route["contract"] = {"schemaVersion": contract["schemaVersion"],
                             "sha256": sha256(contract_path)}
    if contract.get("evidenceBindings"):
        route["projectEvidence"] = dict(sorted(contract["evidenceBindings"].items()))
    return route


def compose_route(
    root: Path,
    profile_path: Path = DEFAULT_PROFILE,
    contract_path: Path | None = None,
    *,
    task_intent: str | None = None,
    stage: str | None = None,
    artifact: str | None = None,
    risk: str | None = None,
    context_budget_tokens: int | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ProfileError(f"project root is not a directory: {root}")
    profile = load_json(profile_path)
    validate_profile(profile)
    contract = {"schemaVersion": 1, "autoDetect": True, "projectTypes": [], "modules": []}
    if contract_path:
        contract = load_json(contract_path)
    validate_contract(contract, profile)
    composition = resolve_project_composition(root, contract, profile)
    task, task_sources = resolve_task_inputs(
        contract,
        profile,
        composition["projectTypes"],
        task_intent=task_intent,
        stage=stage,
        artifact=artifact,
        risk=risk,
        context_budget_tokens=context_budget_tokens,
    )
    task["updateObligation"] = build_update_obligation(task, profile)
    task = apply_task_safety_floors(task, profile)
    intent = task["intent"]
    fallback_reason: str | None = None
    if intent is None:
        fallback_reason = "task-intent-missing"
    elif intent in profile["taskDimensions"]["fallbackIntents"]:
        fallback_reason = f"task-intent-ambiguous:{intent}"
    selection = select_route_topics(profile, contract, composition, task, fallback_reason)
    task["securityAssessmentObligation"] = build_security_assessment_obligation(
        task, selection["selectedTopicIds"], profile
    )
    required_capability_ids = unique([
        *task["updateObligation"]["requiredCapabilityObligationIds"],
        *task["securityAssessmentObligation"]["requiredCapabilityObligationIds"],
    ])
    selected_bundle = reference_bundle(selection["references"])
    legacy_bundle = reference_bundle(composition["legacyReferences"])
    routing_mode = selection["routingMode"]
    selected_topic_ids = selection["selectedTopicIds"]
    selected_task_ids = unique([
        *selection["selectedTaskIds"],
        "security-assessment-obligation."
        + task["securityAssessmentObligation"]["status"].lower(),
    ])
    topic_selection_reasons = selection["topicSelectionReasons"]
    references = selection["references"]
    gates = selection["gates"]
    cleanup_mode = selection["cleanupMode"]
    critical_rule_ids = selection["criticalRuleIds"]
    project_types = composition["projectTypes"]
    selected = composition["selectedModuleIds"]
    legacy_references = composition["legacyReferences"]
    legacy_gates = composition["legacyGates"]
    context_budget = build_context_budget_receipt(selected_bundle, task,
                                                   task_sources, routing_mode)
    declared_budget = context_budget["declaredTokens"]

    return _build_route_receipt(cleanup_mode, composition, context_budget, contract, contract_path, critical_rule_ids, declared_budget, fallback_reason, gates, legacy_bundle, legacy_gates, legacy_references, profile, profile_path, project_types, references, required_capability_ids, root, routing_mode, selected, selected_bundle, selected_task_ids, selected_topic_ids, task, task_sources, topic_selection_reasons)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--task-intent")
    parser.add_argument("--stage")
    parser.add_argument("--artifact")
    parser.add_argument("--risk")
    parser.add_argument("--context-budget-tokens", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def run_self_test() -> None:
    from project_profile_gate_selftest import run_self_test as run_split_self_test

    run_split_self_test(sys.modules[__name__])


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        print("project profile gate self-test passed")
        return 0
    if args.quiet and not args.output:
        raise SystemExit("--quiet requires --output")
    try:
        route = compose_route(
            args.project,
            args.profile,
            args.contract,
            task_intent=args.task_intent,
            stage=args.stage,
            artifact=args.artifact,
            risk=args.risk,
            context_budget_tokens=args.context_budget_tokens,
        )
    except ProfileError as exc:
        parser.error(str(exc))
    payload = json.dumps(route, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    if not args.quiet:
        sys.stdout.buffer.write(payload.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
