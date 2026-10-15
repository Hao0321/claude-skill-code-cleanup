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

def resolve_task_inputs(
    contract: dict[str, Any],
    profile: dict[str, Any],
    project_types: list[str],
    *,
    task_intent: str | None,
    stage: str | None,
    artifact: str | None,
    risk: str | None,
    context_budget_tokens: int | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    dimensions = profile["taskDimensions"]
    for field, value in (
        ("taskIntent", task_intent),
        ("stage", stage),
        ("artifact", artifact),
        ("risk", risk),
    ):
        validate_task_value(field, value, dimensions)
    if context_budget_tokens is not None:
        validate_context_budget(context_budget_tokens, dimensions)

    contract_is_v2 = contract["schemaVersion"] == 2

    def choose(field: str, cli_value: str | None, default: str) -> tuple[str, str]:
        if cli_value is not None:
            return cli_value, "cli"
        if contract_is_v2 and field in contract:
            return contract[field], "contract"
        return default, "profile-default"

    if task_intent is not None:
        effective_intent: str | None = task_intent
        intent_source = "cli"
    elif contract_is_v2 and "taskIntent" in contract:
        effective_intent = contract["taskIntent"]
        intent_source = "contract"
    else:
        effective_intent = None
        intent_source = "missing"

    effective_stage, stage_source = choose(
        "stage", stage, dimensions["defaultStage"]
    )
    if artifact is not None:
        effective_artifact = artifact
        artifact_source = "cli"
    elif contract_is_v2 and "artifact" in contract:
        effective_artifact = contract["artifact"]
        artifact_source = "contract"
    else:
        effective_artifact, artifact_source = infer_artifact(project_types, dimensions)
    effective_risk, risk_source = choose("risk", risk, dimensions["defaultRisk"])

    if context_budget_tokens is not None:
        effective_budget = context_budget_tokens
        budget_source = "cli"
    elif contract_is_v2 and "contextBudgetTokens" in contract:
        effective_budget = contract["contextBudgetTokens"]
        budget_source = "contract"
    else:
        effective_budget = dimensions["defaultContextBudgetTokens"]
        budget_source = "profile-default"

    task = {
        "intent": effective_intent,
        "stage": effective_stage,
        "artifact": effective_artifact,
        "risk": effective_risk,
        "contextBudgetTokens": effective_budget,
    }
    sources = {
        "intent": intent_source,
        "stage": stage_source,
        "artifact": artifact_source,
        "risk": risk_source,
        "contextBudgetTokens": budget_source,
    }
    return task, sources


def build_update_obligation(task: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Return a typed route obligation without granting any mutation authority."""
    policy = profile["routing"]["defaultUpdateObligation"]
    intent = task["intent"]
    artifact = task["artifact"]
    stage = task["stage"]
    explicit = intent == "secure-self-update" or artifact == "updater"

    if explicit:
        status = "REQUIRED_EXPLICIT"
        reason = "explicit-updater-task"
    elif intent is None or intent in profile["taskDimensions"]["fallbackIntents"]:
        status = "EXCLUDED"
        reason = "intent-not-authorized-or-ambiguous"
    elif intent in policy["excludedIntents"]:
        status = "EXCLUDED"
        reason = f"excluded-intent:{intent}"
    elif artifact not in policy["artifacts"]:
        status = "EXCLUDED"
        reason = "source-only-or-nondistributable-artifact"
    elif stage not in policy["stages"]:
        status = "EXCLUDED"
        reason = f"non-iteration-stage:{stage}"
    else:
        status = "REQUIRED_DEFAULT"
        reason = "distributable-target-iteration"

    required = status.startswith("REQUIRED_")
    return {
        "schemaVersion": 1,
        "scope": "target-project-capability",
        "status": status,
        "required": required,
        "reason": reason,
        "requiredCapabilityObligationIds": (
            list(policy["requiredCapabilityObligationIds"]) if required else []
        ),
        "authorityEffect": "selection-only-no-additional-authority",
    }


def build_security_assessment_obligation(
    task: dict[str, Any], selected_topic_ids: list[str], profile: dict[str, Any]
) -> dict[str, Any]:
    """Select security evidence obligations without granting scan authority."""
    policy = profile["routing"]["defaultSecurityAssessmentObligation"]
    intent = task["intent"]
    selected = "security-assessment" in selected_topic_ids
    if intent is None or intent in profile["taskDimensions"]["fallbackIntents"]:
        status, reason = "EXCLUDED", "intent-not-authorized-or-ambiguous"
    elif intent in policy["excludedIntents"]:
        status, reason = "EXCLUDED", f"excluded-intent:{intent}"
    elif not selected:
        status, reason = "EXCLUDED", "security-assessment-topic-not-selected"
    elif intent == "security-assessment":
        status, reason = "REQUIRED_EXPLICIT", "explicit-security-assessment-task"
    else:
        status, reason = "REQUIRED_ROUTE", "security-sensitive-development-route"
    required = status.startswith("REQUIRED_")
    return {
        "schemaVersion": 1,
        "scope": "target-project-security-assessment",
        "status": status,
        "required": required,
        "reason": reason,
        "requiredCapabilityObligationIds": (
            list(policy["requiredCapabilityObligationIds"]) if required else []
        ),
        "requiredSecurityControlIds": (
            list(policy["requiredSecurityControlIds"]) if required else []
        ),
        "authorityEffect": "selection-only-no-scan-or-contact-authority",
    }


def reference_bundle(references: list[str]) -> dict[str, Any]:
    identities: list[dict[str, Any]] = []
    estimated_tokens = 0
    for reference in references:
        path = (ROOT / reference).resolve()
        if not path.is_file():
            raise ProfileError(f"routed reference does not exist: {reference}")
        data = path.read_bytes()
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError as exc:
            raise ProfileError(f"routed reference is not UTF-8: {reference}") from exc
        ascii_nonspace = sum(1 for char in text if ord(char) < 128 and not char.isspace())
        non_ascii_nonspace = sum(1 for char in text if ord(char) >= 128 and not char.isspace())
        estimated_tokens += math.ceil(ascii_nonspace / 3) + non_ascii_nonspace
        identities.append({
            "reference": reference,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    return {
        "sha256": sha256_json(identities),
        "identities": identities,
        "referenceCount": len(identities),
        "exactBytes": sum(identity["bytes"] for identity in identities),
        "estimatedTokens": estimated_tokens,
        "estimator": "unicode-conservative-v1",
    }


def aggregate_topics(
    topic_ids: list[str], topics: dict[str, dict[str, Any]]
) -> tuple[list[str], list[str], list[str], str]:
    references = unique([
        reference
        for topic_id in topic_ids
        for reference in topics[topic_id]["references"]
    ])
    gates = unique([
        gate
        for topic_id in topic_ids
        for gate in topics[topic_id]["gates"]
    ])
    critical_rule_ids = unique([
        rule_id
        for topic_id in topic_ids
        for rule_id in topics[topic_id]["criticalRuleIds"]
    ])
    cleanup_mode = max(
        (topics[topic_id]["cleanupMode"] for topic_id in topic_ids),
        key=MODE_ORDER.get,
    )
    return references, gates, critical_rule_ids, cleanup_mode


def resolve_project_composition(
    root: Path, contract: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    detected, detection_evidence = detect_project_types(root)
    project_types = list(contract.get("projectTypes", []))
    if contract.get("autoDetect", True):
        project_types = unique(project_types + detected)
    if not project_types:
        project_types = ["software"]
    selected_modules = unique([
        *profile["legacy"]["alwaysModules"],
        *project_types,
        *contract.get("modules", []),
    ])
    modules = profile["modules"]
    legacy_references = unique([
        item for name in selected_modules for item in modules[name]["references"]
    ])
    legacy_gates = unique([
        *[item for name in selected_modules for item in modules[name]["gates"]],
        *contract.get("projectGates", []),
    ])
    legacy_cleanup_mode = max(
        (modules[name]["cleanupMode"] for name in selected_modules),
        key=MODE_ORDER.get,
    )
    return {
        "projectTypes": project_types,
        "selectedModuleIds": selected_modules,
        "detectionEvidence": detection_evidence,
        "legacyReferences": legacy_references,
        "legacyGates": legacy_gates,
        "legacyCleanupMode": legacy_cleanup_mode,
    }


def select_route_topics(
    profile: dict[str, Any],
    contract: dict[str, Any],
    composition: dict[str, Any],
    task: dict[str, Any],
    fallback_reason: str | None,
) -> dict[str, Any]:
    topics = profile["topics"]
    routing = profile["routing"]
    selected_modules = composition["selectedModuleIds"]
    intent = task["intent"]
    topic_selection_reasons: dict[str, list[str]] = {}

    def select_topics(topic_ids: list[str], reason: str) -> None:
        for topic_id in topic_ids:
            reasons = topic_selection_reasons.setdefault(topic_id, [])
            if reason not in reasons:
                reasons.append(reason)

    if fallback_reason:
        select_topics([profile["legacy"]["topicId"]], fallback_reason)
        for module_id in selected_modules:
            select_topics(
                routing["moduleTopics"][module_id], f"legacy-module:{module_id}"
            )
        selected_topic_ids = list(topic_selection_reasons)
        critical_rule_ids = list(profile["legacy"]["criticalRuleIds"])
        for topic_id in selected_topic_ids:
            if topic_id in topics:
                critical_rule_ids.extend(topics[topic_id]["criticalRuleIds"])
        return {
            "routingMode": "legacy-compatible-fallback",
            "selectedTopicIds": selected_topic_ids,
            "topicSelectionReasons": topic_selection_reasons,
            "references": composition["legacyReferences"],
            "gates": composition["legacyGates"],
            "cleanupMode": composition["legacyCleanupMode"],
            "criticalRuleIds": unique(critical_rule_ids),
            "selectedTaskIds": ["routing.legacy-compatible-fallback"],
        }

    select_topics(routing["baseTopicIds"], "base-invariant")
    select_topics(routing["intentTopics"][intent], f"intent:{intent}")
    select_topics(routing["stageTopics"][task["stage"]], f"stage:{task['stage']}")
    select_topics(
        routing["artifactTopics"][task["artifact"]], f"artifact:{task['artifact']}"
    )
    select_topics(routing["riskTopics"][task["risk"]], f"risk:{task['risk']}")
    if task["updateObligation"]["required"]:
        select_topics(
            ["secure-self-update"],
            f"update-obligation:{task['updateObligation']['reason']}",
        )
        select_topics(
            routing["secureUpdaterRiskTopics"][task["risk"]],
            f"secure-updater-risk:{task['risk']}",
        )
    for module_id in selected_modules:
        select_topics(routing["moduleTopics"][module_id], f"module:{module_id}")
    selected_topic_ids = list(topic_selection_reasons)
    references, gates, critical_rule_ids, cleanup_mode = aggregate_topics(
        selected_topic_ids, topics
    )
    return {
        "routingMode": "task-aware-v2",
        "selectedTopicIds": selected_topic_ids,
        "topicSelectionReasons": topic_selection_reasons,
        "references": references,
        "gates": unique([*gates, *contract.get("projectGates", [])]),
        "cleanupMode": cleanup_mode,
        "criticalRuleIds": critical_rule_ids,
        "selectedTaskIds": [
            f"intent.{intent}",
            f"stage.{task['stage']}",
            f"artifact.{task['artifact']}",
            f"risk.{task['risk']}",
            f"update-obligation.{task['updateObligation']['status'].lower()}",
        ],
    }


def build_context_budget_receipt(
    selected_bundle: dict[str, Any],
    task: dict[str, Any],
    task_sources: dict[str, str],
    routing_mode: str,
) -> dict[str, Any]:
    estimated_tokens = selected_bundle["estimatedTokens"]
    declared_budget = task["contextBudgetTokens"]
    if estimated_tokens <= declared_budget:
        status = "WITHIN_BUDGET"
    elif routing_mode == "legacy-compatible-fallback":
        status = "SAFE_FALLBACK_EXCEEDS_BUDGET"
    else:
        raise ProfileError(
            "required task-aware route estimate "
            f"{estimated_tokens} exceeds declared context budget {declared_budget}; "
            "refusing to prune required safety topics"
        )
    return {
        "declaredTokens": declared_budget,
        "source": task_sources["contextBudgetTokens"],
        "exactReferenceBytes": selected_bundle["exactBytes"],
        "estimatedReferenceTokens": estimated_tokens,
        "estimator": selected_bundle["estimator"],
        "selectedReferenceCount": selected_bundle["referenceCount"],
        "enforced": routing_mode == "task-aware-v2",
        "status": status,
        "policy": "block-task-aware-overflow-never-prune-required-safety",
    }


def apply_task_safety_floors(
    task: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    effective = dict(task)
    effective["declaredRisk"] = task["risk"]
    effective["safetyAdjustments"] = []
    is_updater = task["updateObligation"]["required"]
    floor = None
    if is_updater and task["stage"] in ("implementation", "promotion"):
        floor = "high"
    elif is_updater and task["stage"] == "completion":
        floor = "critical"
    if floor is None:
        return effective
    risks = profile["taskDimensions"]["risks"]
    if risks.index(task["risk"]) >= risks.index(floor):
        return effective
    effective["risk"] = floor
    effective["safetyAdjustments"].append({
        "ruleId": "rd.updater.safe-client",
        "reason": f"updater {task['stage']} cannot omit delivery/security safety",
        "fromRisk": task["risk"],
        "toRisk": floor,
    })
    return effective
