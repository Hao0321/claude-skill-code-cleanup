#!/usr/bin/env python3
"""Compose a project-specific R&D route from reusable product modules."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "profiles" / "project-modules.json"
MODE_ORDER = {"a": 0, "b": 1, "architecture": 2, "all": 3}
TASK_FIELDS = ("taskIntent", "stage", "artifact", "risk", "contextBudgetTokens")


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
    return value


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
    selected_bundle = reference_bundle(selection["references"])
    legacy_bundle = reference_bundle(composition["legacyReferences"])
    routing_mode = selection["routingMode"]
    selected_topic_ids = selection["selectedTopicIds"]
    selected_task_ids = selection["selectedTaskIds"]
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
        "requiredCapabilityObligationIds": list(
            task["updateObligation"]["requiredCapabilityObligationIds"]
        ),
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


def assert_selection_only(route: dict[str, Any]) -> None:
    assert route["decision"] == "ROUTED"
    assert route["evidenceStatus"] == "NOT_EVALUATED"
    assert route["selectionOnly"] is True
    assert route["gateEvidence"]["status"] == "NOT_EVALUATED"
    assert route["gateEvidence"]["routeOnly"] is True
    assert "PASS" not in json.dumps(route["gateEvidence"])
    assert all(len(value) == 64 for value in route["hashes"].values() if value)


def write_contract(root: Path, name: str, payload: dict[str, Any]) -> Path:
    path = root / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def expect_contract_error(root: Path, name: str, payload: dict[str, Any]) -> None:
    path = write_contract(root, name, payload)
    try:
        compose_route(root, contract_path=path)
    except ProfileError:
        return
    raise AssertionError(f"malformed fixture was accepted: {name}")


def test_legacy_compatibility(base: Path) -> tuple[Path, Path]:
    fixtures = {
        "skill": ("SKILL.md", "---\nname: fixture\n---\n"),
        "web": ("package.json", '{"dependencies":{"next":"1"}}'),
        "database": ("schema.sql", "create table t(id int);"),
        "game": ("project.godot", "[application]"),
        "software": ("pyproject.toml", "[project]\nname='fixture'\n")}
    for kind, (relative, content) in fixtures.items():
        root = base / kind
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        route = compose_route(root)
        assert kind in route["projectTypes"] and kind in route["selectedModules"]
        assert route["cleanup"]["provider"] == "code-cleanup-helper"
        assert route["routingMode"] == "legacy-compatible-fallback"
        assert route["references"] == route["legacyReferences"]
        assert route["fallbackReason"] == "task-intent-missing"
        assert_selection_only(route)

    combined = base / "combined"
    combined.mkdir()
    contract = write_contract(combined, "project.json", {"schemaVersion": 1,
        "autoDetect": False,
        "projectTypes": ["web", "database"],
        "modules": ["public-release", "security"],
        "projectGates": ["native-project-gate"],
        "evidenceBindings": {"native-project-gate":
                             ".rd/receipts/native-project-gate.json"}})
    route = compose_route(combined, contract_path=contract)
    assert route["cleanup"]["mode"] == "all"
    assert route["selectedModules"] == ["core", "cleanup", "web", "database",
                                         "public-release", "security"]
    assert route["selectedModuleIds"] == route["selectedModules"]
    assert route["routingMode"] == "legacy-compatible-fallback"
    assert route["fallbackReason"] == "task-intent-missing"
    assert route["references"] == ["references/protocol.md", "references/metrics.md",
        "references/tooling-and-architecture-gates.md", "references/capability-obligations.md",
        "../code-cleanup-helper/references/rd-integration.md",
        "references/web-commerce-acceptance.md", "references/security-hardening-gates.md",
        "references/external-change-gates.md", "references/completion-closure.md"]
    assert route["gates"] == [
        "evaluator-calibration", "capability-ledger", "completion-closure",
        "cleanup-baseline", "cleanup-promotion", "cleanup-evidence-freshness",
        "browser-geometry", "keyboard-dialog-lifecycle", "responsive-journey",
        "schema-migration", "transaction-integrity", "backup-restore",
        "least-privilege", "privacy-preflight", "canonical-target",
        "tag-release-remote-hash", "threat-model", "negative-security-fixtures",
        "delivered-security-audit", "native-project-gate"]
    assert route["projectEvidence"] == {"native-project-gate":
                                        ".rd/receipts/native-project-gate.json"}
    assert len(route["contract"]["sha256"]) == 64
    assert_selection_only(route)
    return combined, contract


def test_default_update_obligation_routes(routed: Any) -> None:
    for target_artifact, target_stage, expected_risk in (
        ("skill", "implementation", "high"),
        ("software", "promotion", "high"),
        ("game", "implementation", "high"),
        ("installer", "implementation", "high"),
        ("release", "completion", "critical"),
    ):
        distributable = routed(
            f"default-update-{target_artifact}",
            projectType="skill" if target_artifact == "skill" else "software",
            taskIntent="implementation" if target_stage != "completion" else "completion",
            stage=target_stage, artifact=target_artifact, risk="low",
            contextBudgetTokens=50000,
        )
        assert distributable["task"]["updateObligation"]["status"] == "REQUIRED_DEFAULT"
        assert distributable["task"]["risk"] == expected_risk
        assert "secure-self-update" in distributable["selectedTopicIds"]
        assert distributable["task"]["updateObligation"]["authorityEffect"] \
            == "selection-only-no-additional-authority"

    audit_skill = routed("audit-skill-update-excluded", projectType="skill",
        taskIntent="audit", stage="implementation", artifact="skill", risk="low",
        contextBudgetTokens=10000)
    assert audit_skill["task"]["updateObligation"]["status"] == "EXCLUDED"
    assert audit_skill["task"]["risk"] == "low"
    assert "secure-self-update" not in audit_skill["selectedTopicIds"]
    source_iteration = routed("source-update-excluded", taskIntent="implementation",
        stage="implementation", artifact="source", risk="low",
        contextBudgetTokens=10000)
    assert source_iteration["task"]["updateObligation"]["reason"] \
        == "source-only-or-nondistributable-artifact"
    assert source_iteration["requiredCapabilityObligationIds"] == []


def run_self_test() -> None:
    profile = load_json(DEFAULT_PROFILE)
    validate_profile(profile)
    with tempfile.TemporaryDirectory(prefix="project-profile-gate-") as raw:
        base = Path(raw)
        combined, contract = test_legacy_compatibility(base)

        common = {"schemaVersion": 2, "autoDetect": False, "modules": []}
        def routed(name: str, **values: Any) -> dict[str, Any]:
            payload = {**common, "projectTypes": [values.pop("projectType", "software")],
                       **values}
            return compose_route(combined, contract_path=write_contract(
                combined, f"{name}.json", payload))

        focused_route = routed("focused", taskIntent="audit", stage="baseline",
            artifact="source", risk="low", contextBudgetTokens=6000)
        assert focused_route["selectedTopicIds"] == ["core-experiment",
            "context-and-learning", "focused-audit", "baseline-evidence"]
        assert len(focused_route["selectedTopicIds"]) <= 5
        assert not set(focused_route["references"]) & {"references/metrics.md",
            "references/tooling-and-architecture-gates.md",
            "references/capability-obligations.md", "references/media-artifact-evidence.md"}
        assert focused_route["contextBudget"]["status"] == "WITHIN_BUDGET"
        assert_selection_only(focused_route)

        model_route = routed("model", projectType="skill", taskIntent="model-context",
            stage="implementation", artifact="skill", risk="standard",
            contextBudgetTokens=16000)
        assert {"references/model-and-reasoning-gates.md",
            "../code-cleanup-helper/references/model-context-contract-audit.md"}.issubset(
                model_route["references"])
        assert "references/metrics.md" not in model_route["references"]
        assert model_route["task"]["updateObligation"]["status"] == "REQUIRED_DEFAULT"
        assert model_route["task"]["risk"] == "high"
        assert {"secure-self-update", "delivery-artifact", "security-hardening"}.issubset(
            model_route["selectedTopicIds"])
        assert model_route["requiredCapabilityObligationIds"] == [
            "update.client-check", "update.release-channel"]
        assert_selection_only(model_route)

        test_default_update_obligation_routes(routed)

        completion_route = routed("completion", modules=["public-release"],
            taskIntent="completion", stage="completion", artifact="release",
            risk="critical", contextBudgetTokens=50000)
        assert {"references/capability-obligations.md", "references/completion-closure.md",
            "references/external-change-gates.md", "references/delivery-artifact-gates.md",
            "references/security-hardening-gates.md"}.issubset(completion_route["references"])
        assert {"rd.external.current-authority", "completion.last-mutation-barrier"}.issubset(
            completion_route["criticalRuleIds"])
        assert_selection_only(completion_route)

        updater_contract = write_contract(combined, "updater.json", {**common,
            "projectTypes": ["software"], "taskIntent": "secure-self-update",
            "stage": "discovery", "artifact": "updater", "risk": "low",
            "contextBudgetTokens": 6000})
        updater_route = compose_route(combined, contract_path=updater_contract)
        assert updater_route["selectedTopicIds"] == ["core-experiment",
            "context-and-learning", "secure-self-update"]
        assert updater_route["task"]["updateObligation"]["status"] == "REQUIRED_EXPLICIT"
        assert updater_route["requiredCapabilityObligationIds"] == [
            "update.client-check", "update.release-channel"]
        assert updater_route["task"]["safetyAdjustments"] == []
        assert not set(updater_route["references"]) & {"references/delivery-artifact-gates.md",
            "references/security-hardening-gates.md", "references/external-change-gates.md"}
        assert {"rd.updater.safe-client", "rd.updater.side-by-side",
            "rd.updater.workspace-ownership", "rd.updater.upgrade-matrix",
            "rd.updater.runtime-entrypoint",
            "rd.updater.health-rollback", "rd.updater.retirement",
            "rd.updater.user-control", "rd.updater.receipt"}.issubset(
                updater_route["criticalRuleIds"])
        assert_selection_only(updater_route)

        for updater_stage, effective_risk in (("implementation", "high"),
                                               ("promotion", "high"),
                                               ("completion", "critical")):
            staged = compose_route(combined, contract_path=updater_contract,
                stage=updater_stage, risk="standard", context_budget_tokens=50000)
            assert staged["task"]["declaredRisk"] == "standard"
            assert staged["task"]["risk"] == effective_risk
            assert staged["task"]["safetyAdjustments"][0]["ruleId"] == "rd.updater.safe-client"
            assert {"delivery-artifact", "security-hardening"}.issubset(
                staged["selectedTopicIds"])
            if updater_stage == "completion":
                assert {"completion-core", "completion-detail"}.issubset(
                    staged["selectedTopicIds"])
            assert_selection_only(staged)

        for label, intent_value, reason, budget in (
            ("missing", None, "task-intent-missing", 512),
            ("mixed", "mixed", "task-intent-ambiguous:mixed", 12000)):
            payload = {**common, "projectTypes": ["software"],
                "contextBudgetTokens": budget, **({"taskIntent": intent_value}
                if intent_value else {})}
            fallback = compose_route(combined, contract_path=write_contract(
                combined, f"{label}-intent.json", payload))
            assert fallback["routingMode"] == "legacy-compatible-fallback"
            assert fallback["fallbackReason"] == reason
            assert fallback["references"] == fallback["legacyReferences"]
            assert_selection_only(fallback)
        assert fallback["references"]

        cli_route = compose_route(combined, contract_path=contract,
            task_intent="audit", stage="baseline", artifact="source", risk="low",
            context_budget_tokens=50000)
        assert cli_route["routingMode"] == "task-aware-v2"
        assert all(cli_route["task"]["sources"][field] == "cli" for field in
            ("intent", "stage", "artifact", "risk", "contextBudgetTokens"))
        assert_selection_only(cli_route)
        parsed = build_parser().parse_args(["--task-intent", "audit", "--stage",
            "baseline", "--artifact", "source", "--risk", "low",
            "--context-budget-tokens", "6000"])
        assert (parsed.task_intent, parsed.context_budget_tokens) == ("audit", 6000)

        valid = {**common, "projectTypes": ["software"], "taskIntent": "audit",
            "stage": "baseline", "artifact": "source", "risk": "low",
            "contextBudgetTokens": 6000}
        for field, value in (("taskIntent", "unknown-intent"),
                             ("stage", "unknown-stage"),
                             ("artifact", "unknown-artifact"),
                             ("risk", "unknown-risk")):
            payload = dict(valid)
            payload[field] = value
            expect_contract_error(combined, f"invalid-{field}.json", payload)
        malformed = (
            ("project-type", {"schemaVersion": 1, "projectTypes": ["unknown"]}),
            ("gate", {"schemaVersion": 1, "projectGates": ["x", "x"]}),
            ("schema1-task", {"schemaVersion": 1, "taskIntent": "audit"}),
            ("budget-type", {"schemaVersion": 2, "taskIntent": "audit",
                             "contextBudgetTokens": True}),
            ("budget-range", {"schemaVersion": 2, "taskIntent": "audit",
                              "contextBudgetTokens": 1}),
            ("budget-overflow", {**valid, "contextBudgetTokens": 512}),
        )
        for name, payload in malformed:
            expect_contract_error(combined, f"invalid-{name}.json", payload)
        try:
            compose_route(combined, task_intent="unknown-intent")
        except ProfileError:
            pass
        else:
            raise AssertionError("unknown CLI task intent was accepted")


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
