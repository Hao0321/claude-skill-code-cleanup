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


def _validate_profile_dimensions(profile):
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
    return dimension_lists


def _validate_profile_routing(allowed, dimension_lists, profile, topics):
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

    dimension_lists = _validate_profile_dimensions(profile)
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

    _validate_profile_routing(allowed, dimension_lists, profile, topics)


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
