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


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "profiles" / "project-modules.json"
MODE_ORDER = {"a": 0, "b": 1, "architecture": 2, "all": 3}
TASK_FIELDS = ("taskIntent", "stage", "artifact", "risk", "contextBudgetTokens")
SECURITY_CAPABILITY_IDS = (
    "security.scan-scope",
    "security.scan-coverage",
    "security.scanner-provenance",
    "security.finding-normalization",
    "security.engine-admission",
    "security.adapter-integrity",
)


class ProfileError(ValueError):
    """Raised when a project composition contract is invalid."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProfileError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProfileError(f"JSON root must be an object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_string_list(value: Any, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ProfileError(f"{label} must be a string list")
    if not allow_empty and not value:
        raise ProfileError(f"{label} must not be empty")
    if len(value) != len(set(value)):
        raise ProfileError(f"{label} must not contain duplicates")
    if len(value) != len({item.casefold() for item in value}):
        raise ProfileError(f"{label} must not contain case-folding collisions")
    return value


def validate_security_assessment_policy(
    routing: dict[str, Any], intents: list[str]
) -> None:
    policy = routing.get("defaultSecurityAssessmentObligation")
    expected = {
        "excludedIntents", "requiredCapabilityObligationIds",
        "requiredSecurityControlIds",
    }
    if not isinstance(policy, dict) or set(policy) != expected:
        raise ProfileError(
            "routing.defaultSecurityAssessmentObligation must declare its closed-world policy"
        )
    exclusions = validate_string_list(
        policy.get("excludedIntents"),
        "routing.defaultSecurityAssessmentObligation.excludedIntents",
        allow_empty=False,
    )
    unknown = sorted(set(exclusions) - set(intents))
    if unknown:
        raise ProfileError(
            "unknown routing.defaultSecurityAssessmentObligation.excludedIntents: "
            + ", ".join(unknown)
        )
    capability_ids = validate_string_list(
        policy.get("requiredCapabilityObligationIds"),
        "routing.defaultSecurityAssessmentObligation.requiredCapabilityObligationIds",
        allow_empty=False,
    )
    if tuple(capability_ids) != SECURITY_CAPABILITY_IDS:
        raise ProfileError(
            "routing.defaultSecurityAssessmentObligation.requiredCapabilityObligationIds "
            "must equal the canonical six security capability IDs in canonical order"
        )
    control_ids = validate_string_list(
        policy.get("requiredSecurityControlIds"),
        "routing.defaultSecurityAssessmentObligation.requiredSecurityControlIds",
        allow_empty=False,
    )
    if tuple(control_ids) != SECURITY_CAPABILITY_IDS:
        raise ProfileError(
            "routing.defaultSecurityAssessmentObligation.requiredSecurityControlIds "
            "must equal the canonical six security control IDs in canonical order"
        )


def validate_profile(profile: dict[str, Any]) -> None:
    if profile.get("schemaVersion") != 2:
        raise ProfileError("unsupported project module schema")
    project_types = validate_string_list(
        profile.get("projectTypes"), "projectTypes", allow_empty=False
    )
    overlays = validate_string_list(
        profile.get("overlayModules"), "overlayModules", allow_empty=False
    )
    modules = profile.get("modules")
    if not isinstance(modules, dict) or "core" not in modules or "cleanup" not in modules:
        raise ProfileError("modules must contain core and cleanup")
    allowed = {"core", "cleanup", *project_types, *overlays}
    if set(modules) != allowed:
        raise ProfileError("module registry and declared project/overlay names must match exactly")
    for name, module in modules.items():
        if not isinstance(module, dict):
            raise ProfileError(f"module {name} must be an object")
        if module.get("cleanupMode") not in MODE_ORDER:
            raise ProfileError(f"module {name} has invalid cleanupMode")
        for field in ("references", "gates"):
            validate_string_list(module.get(field), f"module {name}.{field}", allow_empty=False)

    dimensions = profile.get("taskDimensions")
    if not isinstance(dimensions, dict):
        raise ProfileError("taskDimensions must be an object")
    dimension_lists: dict[str, list[str]] = {}
    for field in ("intents", "stages", "artifacts", "risks"):
        dimension_lists[field] = validate_string_list(
            dimensions.get(field), f"taskDimensions.{field}", allow_empty=False
        )
    fallback_intents = validate_string_list(
        dimensions.get("fallbackIntents"), "taskDimensions.fallbackIntents"
    )
    if not set(fallback_intents).issubset(dimension_lists["intents"]):
        raise ProfileError("fallbackIntents must be declared intents")
    for field, vocabulary in (
        ("defaultStage", dimension_lists["stages"]),
        ("defaultArtifact", dimension_lists["artifacts"]),
        ("defaultRisk", dimension_lists["risks"]),
    ):
        if dimensions.get(field) not in vocabulary:
            raise ProfileError(f"taskDimensions.{field} is not in its vocabulary")
    for field in (
        "defaultContextBudgetTokens",
        "minContextBudgetTokens",
        "maxContextBudgetTokens",
    ):
        value = dimensions.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ProfileError(f"taskDimensions.{field} must be a positive integer")
    minimum = dimensions["minContextBudgetTokens"]
    default = dimensions["defaultContextBudgetTokens"]
    maximum = dimensions["maxContextBudgetTokens"]
    if not minimum <= default <= maximum:
        raise ProfileError("default context budget must be within the declared range")

    legacy = profile.get("legacy")
    if not isinstance(legacy, dict):
        raise ProfileError("legacy must be an object")
    always_modules = validate_string_list(
        legacy.get("alwaysModules"), "legacy.alwaysModules", allow_empty=False
    )
    if set(always_modules) != {"core", "cleanup"}:
        raise ProfileError("legacy.alwaysModules must contain core and cleanup")
    if not isinstance(legacy.get("topicId"), str) or not legacy["topicId"]:
        raise ProfileError("legacy.topicId must be a non-empty string")
    validate_string_list(
        legacy.get("criticalRuleIds"), "legacy.criticalRuleIds", allow_empty=False
    )

    topics = profile.get("topics")
    if not isinstance(topics, dict) or not topics:
        raise ProfileError("topics must be a non-empty object")
    validate_string_list(list(topics), "topics", allow_empty=False)
    for topic_id, topic in topics.items():
        if not isinstance(topic_id, str) or not topic_id or not isinstance(topic, dict):
            raise ProfileError("topic IDs must map to objects")
        if topic.get("cleanupMode") not in MODE_ORDER:
            raise ProfileError(f"topic {topic_id} has invalid cleanupMode")
        validate_string_list(topic.get("references"), f"topic {topic_id}.references")
        validate_string_list(topic.get("gates"), f"topic {topic_id}.gates", allow_empty=False)
        validate_string_list(
            topic.get("criticalRuleIds"),
            f"topic {topic_id}.criticalRuleIds",
            allow_empty=False,
        )

    routing = profile.get("routing")
    if not isinstance(routing, dict):
        raise ProfileError("routing must be an object")

    def validate_topic_ids(value: Any, label: str) -> list[str]:
        topic_ids = validate_string_list(value, label)
        unknown = sorted(set(topic_ids) - set(topics))
        if unknown:
            raise ProfileError(f"unknown topics in {label}: {', '.join(unknown)}")
        return topic_ids

    validate_topic_ids(routing.get("baseTopicIds"), "routing.baseTopicIds")
    mapping_specs = (
        ("intentTopics", dimension_lists["intents"]),
        ("stageTopics", dimension_lists["stages"]),
        ("artifactTopics", dimension_lists["artifacts"]),
        ("riskTopics", dimension_lists["risks"]),
        ("secureUpdaterRiskTopics", dimension_lists["risks"]),
        ("moduleTopics", list(allowed)),
    )
    for field, expected_keys in mapping_specs:
        mapping = routing.get(field)
        if not isinstance(mapping, dict) or set(mapping) != set(expected_keys):
            raise ProfileError(f"routing.{field} keys must match their closed-world vocabulary")
        for key, topic_ids in mapping.items():
            validate_topic_ids(topic_ids, f"routing.{field}.{key}")
    for risk in ("high", "critical"):
        if "security-assessment" not in routing["secureUpdaterRiskTopics"][risk]:
            raise ProfileError(
                f"routing.secureUpdaterRiskTopics.{risk} must include security-assessment"
            )

    update_policy = routing.get("defaultUpdateObligation")
    expected_update_fields = {
        "stages", "artifacts", "excludedIntents", "requiredCapabilityObligationIds"
    }
    if not isinstance(update_policy, dict) or set(update_policy) != expected_update_fields:
        raise ProfileError(
            "routing.defaultUpdateObligation must declare its closed-world policy"
        )
    for field, vocabulary in (
        ("stages", dimension_lists["stages"]),
        ("artifacts", dimension_lists["artifacts"]),
        ("excludedIntents", dimension_lists["intents"]),
    ):
        values = validate_string_list(
            update_policy.get(field),
            f"routing.defaultUpdateObligation.{field}",
            allow_empty=False,
        )
        unknown = sorted(set(values) - set(vocabulary))
        if unknown:
            raise ProfileError(
                f"unknown routing.defaultUpdateObligation.{field}: {', '.join(unknown)}"
            )
    validate_string_list(
        update_policy.get("requiredCapabilityObligationIds"),
        "routing.defaultUpdateObligation.requiredCapabilityObligationIds",
        allow_empty=False,
    )

    validate_security_assessment_policy(routing, dimension_lists["intents"])


def package_dependencies(root: Path) -> set[str]:
    path = root / "package.json"
    if not path.is_file():
        return set()
    try:
        package = load_json(path)
    except ProfileError:
        return set()
    names: set[str] = set()
    for field in ("dependencies", "devDependencies"):
        values = package.get(field, {})
        if isinstance(values, dict):
            names.update(str(name).lower() for name in values)
    return names


def detect_project_types(root: Path) -> tuple[list[str], dict[str, list[str]]]:
    evidence: dict[str, list[str]] = {}

    def mark(kind: str, markers: list[str]) -> None:
        present = [marker for marker in markers if (root / marker).exists()]
        if present:
            evidence[kind] = present

    mark("skill", ["SKILL.md"])
    mark("game", ["project.godot", "ProjectSettings", "Config/DefaultEngine.ini"])
    mark("database", ["prisma/schema.prisma", "migrations", "schema.sql", "alembic.ini"])
    mark("software", ["pyproject.toml", "setup.py", "Cargo.toml", "CMakeLists.txt"])
    web_markers = ["index.html", "vite.config.js", "vite.config.ts", "next.config.js", "next.config.mjs"]
    web_deps = {"next", "react", "vue", "svelte", "@angular/core", "vite"}
    present_web = [marker for marker in web_markers if (root / marker).exists()]
    dependencies = package_dependencies(root)
    if present_web or dependencies.intersection(web_deps):
        evidence["web"] = present_web + sorted(dependencies.intersection(web_deps))
    if not evidence:
        evidence["software"] = ["fallback:no-specialized-marker"]
    ordered = [kind for kind in ("skill", "web", "database", "game", "software") if kind in evidence]
    return ordered, evidence


def validate_contract(contract: dict[str, Any], profile: dict[str, Any]) -> None:
    schema_version = contract.get("schemaVersion")
    if schema_version not in (1, 2):
        raise ProfileError("unsupported project contract schema")
    if not isinstance(contract.get("autoDetect", True), bool):
        raise ProfileError("autoDetect must be boolean")
    allowed_types = set(profile["projectTypes"])
    allowed_overlays = set(profile["overlayModules"])
    for field, allowed in (("projectTypes", allowed_types), ("modules", allowed_overlays)):
        values = contract.get(field, [])
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ProfileError(f"{field} must be a string list")
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ProfileError(f"unknown {field}: {', '.join(unknown)}")
    project_gates = contract.get("projectGates", [])
    if not isinstance(project_gates, list) or not all(
        isinstance(item, str) and item.strip() for item in project_gates
    ):
        raise ProfileError("projectGates must be a non-empty string list when present")
    if len(project_gates) != len(set(project_gates)):
        raise ProfileError("projectGates must not contain duplicates")
    evidence = contract.get("evidenceBindings", {})
    if not isinstance(evidence, dict) or not all(
        isinstance(key, str) and key.strip()
        and isinstance(value, str) and value.strip()
        for key, value in evidence.items()
    ):
        raise ProfileError("evidenceBindings must map non-empty strings to non-empty strings")

    present_task_fields = [field for field in TASK_FIELDS if field in contract]
    if schema_version == 1 and present_task_fields:
        raise ProfileError(
            "schema-1 contracts cannot declare task routing fields; use schemaVersion 2"
        )
    if schema_version == 2:
        dimensions = profile["taskDimensions"]
        vocabulary = {
            "taskIntent": dimensions["intents"],
            "stage": dimensions["stages"],
            "artifact": dimensions["artifacts"],
            "risk": dimensions["risks"],
        }
        for field, allowed in vocabulary.items():
            if field not in contract:
                continue
            value = contract[field]
            if not isinstance(value, str) or not value:
                raise ProfileError(f"{field} must be a non-empty string")
            if value not in allowed:
                raise ProfileError(f"unknown {field}: {value}")
        if "contextBudgetTokens" in contract:
            validate_context_budget(contract["contextBudgetTokens"], dimensions)


def validate_context_budget(value: Any, dimensions: dict[str, Any]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProfileError("contextBudgetTokens must be an integer")
    minimum = dimensions["minContextBudgetTokens"]
    maximum = dimensions["maxContextBudgetTokens"]
    if not minimum <= value <= maximum:
        raise ProfileError(
            f"contextBudgetTokens must be between {minimum} and {maximum}"
        )
    return value


def validate_task_value(field: str, value: str | None, dimensions: dict[str, Any]) -> None:
    if value is None:
        return
    vocabulary = {
        "taskIntent": dimensions["intents"],
        "stage": dimensions["stages"],
        "artifact": dimensions["artifacts"],
        "risk": dimensions["risks"],
    }
    if not isinstance(value, str) or not value:
        raise ProfileError(f"{field} must be a non-empty string")
    if value not in vocabulary[field]:
        raise ProfileError(f"unknown {field}: {value}")


def unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def infer_artifact(project_types: list[str], dimensions: dict[str, Any]) -> tuple[str, str]:
    if len(project_types) == 1 and project_types[0] in dimensions["artifacts"]:
        return project_types[0], "project-type-inference"
    return dimensions["defaultArtifact"], "profile-default"


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
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
