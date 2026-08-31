#!/usr/bin/env python3
"""Run deterministic task-routing quality fixtures against Router v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import project_profile_gate as router


ROOT = Path(__file__).resolve().parents[1]
ROUTER_PATH = ROOT / "scripts" / "project_profile_gate.py"
PROFILE_PATH = ROOT / "profiles" / "project-modules.json"
BASE_TOPICS = ("core-experiment", "context-and-learning")
BASE_RULES = ("rd.core.truthful-verdict", "rd.context.critical-fallback")
VARIANTS = ("direct-positive", "near-miss-negative", "stale-or-distractor")


@dataclass(frozen=True)
class ClassSpec:
    task_class: str
    intent: str | None
    stage: str
    artifact: str
    risk: str
    expected_topics: tuple[str, ...]
    required_rules: tuple[str, ...]
    forbidden_topics: tuple[str, ...] = ()
    project_types: tuple[str, ...] = ("software",)
    max_selected_topics: int | None = 5
    cap_policy: str = "default-five-card-cap"
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    task_class: str
    variant: str
    contract: dict[str, Any]
    expected_mode: str
    expected_fallback_reason: str | None
    expected_topics: tuple[str, ...]
    required_rules: tuple[str, ...]
    forbidden_topics: tuple[str, ...]
    expected_effective_risk: str
    expected_adjustment_rules: tuple[str, ...] = ()
    max_selected_topics: int | None = 5
    cap_policy: str = "default-five-card-cap"
    flags: tuple[str, ...] = ()


CLASS_SPECS = (
    ClassSpec(
        "mixed-ts-rust-audit",
        "audit",
        "discovery",
        "source",
        "low",
        (*BASE_TOPICS, "focused-audit"),
        (*BASE_RULES, "audit.read-only-unless-implementation-authorized"),
        ("benchmark-metrics", "media-evidence", "model-context", "completion-detail"),
        flags=("audit-authorization", "mixed-language-not-checked"),
    ),
    ClassSpec(
        "architecture",
        "architecture",
        "discovery",
        "source",
        "standard",
        (*BASE_TOPICS, "architecture-evaluation"),
        (*BASE_RULES, "rd.arch.one-owner", "rd.arch.cleanup-provider"),
        ("benchmark-metrics", "media-evidence", "completion-detail"),
    ),
    ClassSpec(
        "implementation",
        "implementation",
        "implementation",
        "source",
        "low",
        (*BASE_TOPICS, "implementation-discipline"),
        (*BASE_RULES, "rd.core.smallest-decisive"),
        ("benchmark-metrics", "media-evidence", "completion-detail"),
    ),
    ClassSpec(
        "benchmark",
        "benchmark",
        "baseline",
        "source",
        "standard",
        (*BASE_TOPICS, "benchmark-metrics", "baseline-evidence"),
        (*BASE_RULES, "benchmark.same-provenance-only", "baseline.existing-failures-remain-evidence"),
        ("implementation-discipline", "media-evidence", "completion-detail"),
    ),
    ClassSpec(
        "model-context",
        "model-context",
        "discovery",
        "source",
        "standard",
        (*BASE_TOPICS, "model-context"),
        (*BASE_RULES, "context.typed-contract-binds-semantic-router"),
        ("benchmark-metrics", "media-evidence", "completion-detail"),
    ),
    ClassSpec(
        "completion",
        "completion",
        "completion",
        "source",
        "standard",
        (*BASE_TOPICS, "completion-detail"),
        (*BASE_RULES, "rd.complete.fresh-close", "completion.last-mutation-barrier"),
        ("benchmark-metrics", "media-evidence", "model-context"),
    ),
    ClassSpec(
        "external-release",
        "external-change",
        "completion",
        "release",
        "standard",
        (*BASE_TOPICS, "external-detail", "completion-detail", "delivery-artifact",
         "security-hardening", "architecture-evaluation", "completion-core",
         "secure-self-update"),
        (*BASE_RULES, "rd.external.current-authority", "rd.external.postverify",
         "delivery.source-tests-do-not-prove-shipped-bytes",
         "rd.updater.default-obligation", "rd.updater.user-control"),
        ("media-evidence", "model-context", "benchmark-metrics"),
        max_selected_topics=9,
        cap_policy="documented-external-release-update-closure-route",
        flags=("external-release", "default-updater"),
    ),
    ClassSpec(
        "mcp-session-ai-skill",
        "model-context",
        "discovery",
        "skill",
        "standard",
        (*BASE_TOPICS, "model-context", "skill-artifact"),
        (*BASE_RULES, "context.typed-contract-binds-semantic-router", "skill.current-private-bytes-are-authoritative"),
        ("benchmark-metrics", "media-evidence", "delivery-artifact", "completion-detail"),
        project_types=("skill",),
        flags=("session-ai",),
    ),
    ClassSpec(
        "web-product",
        "implementation",
        "implementation",
        "web",
        "low",
        (*BASE_TOPICS, "implementation-discipline", "web-product"),
        (*BASE_RULES, "rd.core.smallest-decisive", "web.live-geometry-not-dom-presence"),
        ("benchmark-metrics", "media-evidence", "completion-detail", "security-hardening"),
    ),
    ClassSpec(
        "database-integrity",
        "architecture",
        "discovery",
        "database",
        "standard",
        (*BASE_TOPICS, "architecture-evaluation", "database-integrity"),
        (*BASE_RULES, "rd.arch.one-owner", "database.migration-and-rollback-evidence-required"),
        ("web-product", "media-evidence", "benchmark-metrics", "completion-detail"),
    ),
    ClassSpec(
        "game-delivery-media",
        "implementation",
        "implementation",
        "game",
        "standard",
        (*BASE_TOPICS, "implementation-discipline", "delivery-artifact", "media-evidence",
         "architecture-evaluation", "secure-self-update", "security-hardening"),
        (*BASE_RULES, "rd.core.smallest-decisive",
         "delivery.extracted-envelope-is-authority", "media.decoded-user-output-is-authority",
         "rd.updater.default-obligation", "rd.updater.safe-client",
         "rd.updater.user-control"),
        ("benchmark-metrics", "model-context", "completion-detail"),
        max_selected_topics=8,
        cap_policy="documented-game-delivery-update-route",
        flags=("specialized-media", "default-updater"),
    ),
    ClassSpec(
        "skill-iteration-update-default",
        "implementation",
        "implementation",
        "skill",
        "low",
        (*BASE_TOPICS, "implementation-discipline", "skill-artifact",
         "architecture-evaluation", "secure-self-update", "delivery-artifact",
         "security-hardening"),
        (*BASE_RULES, "skill.current-private-bytes-are-authoritative",
         "rd.updater.default-obligation", "rd.updater.safe-client",
         "rd.updater.user-control"),
        ("benchmark-metrics", "media-evidence", "completion-detail"),
        project_types=("skill",),
        max_selected_topics=8,
        cap_policy="documented-skill-update-safety-route",
        flags=("default-updater",),
    ),
    ClassSpec(
        "software-promotion-update-default",
        "implementation",
        "promotion",
        "software",
        "low",
        (*BASE_TOPICS, "implementation-discipline", "promotion-evidence",
         "delivery-artifact", "architecture-evaluation", "secure-self-update",
         "security-hardening"),
        (*BASE_RULES, "promotion.final-evidence-must-be-fresh",
         "rd.updater.default-obligation", "rd.updater.safe-client",
         "rd.updater.user-control"),
        ("benchmark-metrics", "media-evidence", "completion-detail"),
        max_selected_topics=8,
        cap_policy="documented-software-update-promotion-route",
        flags=("default-updater",),
    ),
    ClassSpec(
        "installer-implementation-update-default",
        "implementation",
        "implementation",
        "installer",
        "low",
        (*BASE_TOPICS, "implementation-discipline", "delivery-artifact",
         "security-hardening", "architecture-evaluation", "secure-self-update"),
        (*BASE_RULES, "delivery.source-tests-do-not-prove-shipped-bytes",
         "rd.updater.default-obligation", "rd.updater.safe-client",
         "rd.updater.user-control"),
        ("benchmark-metrics", "media-evidence", "completion-detail"),
        max_selected_topics=7,
        cap_policy="documented-installer-update-safety-route",
        flags=("default-updater",),
    ),
    ClassSpec(
        "skill-audit-update-excluded",
        "audit",
        "baseline",
        "skill",
        "low",
        (*BASE_TOPICS, "focused-audit", "baseline-evidence", "skill-artifact"),
        (*BASE_RULES, "audit.read-only-unless-implementation-authorized",
         "skill.current-private-bytes-are-authoritative"),
        ("secure-self-update", "delivery-artifact", "security-hardening"),
        project_types=("skill",),
        flags=("audit-authorization", "update-excluded"),
    ),
    ClassSpec(
        "ambiguous-legacy-fallback",
        "mixed",
        "discovery",
        "software",
        "standard",
        ("legacy-full-module-route",),
        ("rd.context.critical-fallback", "rd.core.truthful-verdict", "cleanup.adapter-only", "learning.project-local-by-default"),
        (),
        max_selected_topics=None,
        cap_policy="documented-legacy-fallback-exception",
        flags=("fallback",),
    ),
)


UPDATER_SPECS = (
    CaseSpec(
        "updater.discovery-low",
        "secure-self-update",
        "updater-special",
        {},
        "task-aware-v2",
        None,
        (*BASE_TOPICS, "secure-self-update"),
        (*BASE_RULES, "rd.updater.source-policy", "rd.updater.safe-client", "rd.updater.user-control"),
        ("benchmark-metrics", "media-evidence", "completion-detail", "security-hardening"),
        "low",
        max_selected_topics=5,
        flags=("updater",),
    ),
    CaseSpec(
        "updater.implementation-promotion-risk-floor",
        "secure-self-update",
        "updater-special",
        {},
        "task-aware-v2",
        None,
        (*BASE_TOPICS, "secure-self-update", "promotion-evidence", "architecture-evaluation", "delivery-artifact", "security-hardening"),
        (*BASE_RULES, "rd.updater.safe-client", "promotion.final-evidence-must-be-fresh", "security.fail-closed-on-identity-drift"),
        ("benchmark-metrics", "media-evidence", "model-context", "completion-detail"),
        "high",
        ("rd.updater.safe-client",),
        7,
        "documented-updater-safety-floor",
        ("updater",),
    ),
    CaseSpec(
        "updater.completion-destructive",
        "secure-self-update",
        "updater-special",
        {},
        "task-aware-v2",
        None,
        (*BASE_TOPICS, "secure-self-update", "completion-detail", "architecture-evaluation", "completion-core", "delivery-artifact", "security-hardening"),
        (*BASE_RULES, "rd.updater.safe-client", "rd.updater.retirement", "rd.updater.user-control", "rd.complete.closed-obligations", "completion.last-mutation-barrier"),
        ("benchmark-metrics", "media-evidence", "model-context"),
        "critical",
        ("rd.updater.safe-client",),
        8,
        "documented-updater-completion-safety-floor",
        ("updater", "destructive-boundary"),
    ),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def unique(items: list[str] | tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(items))

def make_contract(spec: ClassSpec, variant: str) -> dict[str, Any]:
    intent = spec.intent
    if spec.task_class == "ambiguous-legacy-fallback" and variant == "near-miss-negative":
        intent = None
    contract: dict[str, Any] = {
        "schemaVersion": 2,
        "autoDetect": variant != "direct-positive",
        "projectTypes": list(spec.project_types),
        "modules": [],
        "stage": spec.stage,
        "artifact": spec.artifact,
        "risk": spec.risk,
        "contextBudgetTokens": 100000,
        "evidenceBindings": {
            "authorization": "audit-only:no-external-or-destructive-mutation",
            "fixture": f"router-quality-corpus:{spec.task_class}:{variant}",
        },
    }
    if intent is not None:
        contract["taskIntent"] = intent
    return contract

def expand_cases() -> list[CaseSpec]:
    cases: list[CaseSpec] = []
    for spec in CLASS_SPECS:
        for variant in VARIANTS:
            fallback_reason = None
            if spec.task_class == "ambiguous-legacy-fallback":
                fallback_reason = (
                    "task-intent-missing"
                    if variant == "near-miss-negative"
                    else "task-intent-ambiguous:mixed"
                )
            cases.append(CaseSpec(
                case_id=f"{spec.task_class}.{variant}",
                task_class=spec.task_class,
                variant=variant,
                contract=make_contract(spec, variant),
                expected_mode=(
                    "legacy-compatible-fallback"
                    if spec.task_class == "ambiguous-legacy-fallback"
                    else "task-aware-v2"
                ),
                expected_fallback_reason=fallback_reason,
                expected_topics=spec.expected_topics,
                required_rules=spec.required_rules,
                forbidden_topics=spec.forbidden_topics,
                expected_effective_risk=(
                    "critical"
                    if "default-updater" in spec.flags and spec.stage == "completion"
                    else "high"
                    if "default-updater" in spec.flags
                    and spec.stage in ("implementation", "promotion")
                    else spec.risk
                ),
                expected_adjustment_rules=(
                    ("rd.updater.safe-client",)
                    if "default-updater" in spec.flags
                    and spec.stage in ("implementation", "promotion", "completion")
                    and spec.risk not in ("high", "critical")
                    else ()
                ),
                max_selected_topics=spec.max_selected_topics,
                cap_policy=spec.cap_policy,
                flags=spec.flags,
            ))
    updater_contracts = (
        {
            "schemaVersion": 2,
            "autoDetect": False,
            "projectTypes": ["software"],
            "modules": [],
            "taskIntent": "secure-self-update",
            "stage": "discovery",
            "artifact": "updater",
            "risk": "low",
            "contextBudgetTokens": 100000,
            "evidenceBindings": {
                "authorization": "discovery-only:no-download-or-execution",
                "fixture": "router-quality-corpus:updater-discovery",
            },
        },
        {
            "schemaVersion": 2,
            "autoDetect": False,
            "projectTypes": ["software"],
            "modules": [],
            "taskIntent": "secure-self-update",
            "stage": "promotion",
            "artifact": "updater",
            "risk": "low",
            "contextBudgetTokens": 100000,
            "evidenceBindings": {
                "authorization": "local-implementation-only:no-external-promotion",
                "fixture": "router-quality-corpus:updater-promotion-floor",
            },
        },
        {
            "schemaVersion": 2,
            "autoDetect": False,
            "projectTypes": ["software"],
            "modules": [],
            "taskIntent": "secure-self-update",
            "stage": "completion",
            "artifact": "updater",
            "risk": "low",
            "contextBudgetTokens": 100000,
            "evidenceBindings": {
                "authorization": "verification-only:retirement-requires-current-user-authorization",
                "fixture": "router-quality-corpus:updater-completion",
            },
        },
    )
    for template, contract in zip(UPDATER_SPECS, updater_contracts):
        cases.append(CaseSpec(**{**template.__dict__, "contract": contract}))
    return cases

def write_fixture_files(project: Path, case: CaseSpec) -> None:
    files: dict[str, str] = {}
    if case.task_class == "mixed-ts-rust-audit":
        files.update({
            "package.json": '{"name":"mixed-fixture","private":true}',
            "Cargo.toml": '[package]\nname = "mixed_fixture"\nversion = "0.0.0"\n',
            "src/index.ts": "export const fixture = true;\n",
            "src/lib.rs": "pub fn fixture() -> bool { true }\n",
        })
    if case.task_class == "mcp-session-ai-skill":
        files.update({
            "SKILL.md": "---\nname: fixture\ndescription: MCP fixture.\n---\n",
            "mcp.fixture.json": '{"transport":"stdio","fixture":true}',
        })
    if case.variant == "near-miss-negative":
        files.update({
            "near-miss/index.html.example": "not a web project marker\n",
            "near-miss/timeline.media.json": '{"kind":"distractor"}',
            "near-miss/benchmark-metrics.old": "stale and irrelevant\n",
        })
    if case.variant == "stale-or-distractor":
        files[".rd/cache/stale-route-receipt.json"] = json.dumps({
            "schemaVersion": 2,
            "profileSha256": "0" * 64,
            "selectedTopicIds": ["media-evidence", "benchmark-metrics"],
            "status": "STALE_FIXTURE_DO_NOT_TRUST",
        }, indent=2)
    for relative, content in files.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

def assertion(
    assertion_id: str,
    passed: bool,
    *,
    expected: Any = None,
    observed: Any = None,
    detail: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": assertion_id,
        "status": "PASS" if passed else "FAIL",
    }
    if expected is not None:
        item["expected"] = expected
    if observed is not None:
        item["observed"] = observed
    if detail:
        item["detail"] = detail
    return item

def not_checked(assertion_id: str, detail: str) -> dict[str, Any]:
    return {"id": assertion_id, "status": "NOT_CHECKED", "detail": detail}

def reference_hashes_are_fresh(route_value: dict[str, Any]) -> tuple[bool, list[str]]:
    mismatches: list[str] = []
    for reference, expected_hash in route_value.get("selectedReferenceHashes", {}).items():
        path = (ROOT / reference).resolve()
        if not path.is_file() or sha256(path) != expected_hash:
            mismatches.append(reference)
    return not mismatches, mismatches

def irrelevant_reference_fragments(case: CaseSpec) -> list[str]:
    if case.expected_mode != "task-aware-v2":
        return []
    fragments = ["references/tooling-and-architecture-gates.md"]
    topics = set(case.expected_topics)
    if "media-evidence" not in topics:
        fragments.append("references/media-artifact-evidence.md")
    if "benchmark-metrics" not in topics:
        fragments.append("references/metrics.md")
    if "completion-detail" not in topics:
        fragments.extend([
            "references/capability-obligations.md",
            "references/completion-closure.md",
        ])
    return fragments

def prepare_case(workspace: Path, case: CaseSpec) -> tuple[Path, Path]:
    project = workspace / "projects" / case.case_id
    project.mkdir(parents=True, exist_ok=True)
    write_fixture_files(project, case)
    contract_path = workspace / "contracts" / f"{case.case_id}.json"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(
        json.dumps(case.contract, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return project, contract_path

def route_error_result(case: CaseSpec, exc: Exception) -> dict[str, Any]:
    return {
        "id": case.case_id,
        "taskClass": case.task_class,
        "variant": case.variant,
        "flags": list(case.flags),
        "decision": "FAIL",
        "routeError": {"type": type(exc).__name__, "message": str(exc)},
        "assertions": [{
            "id": "canonical-compose-route",
            "status": "FAIL",
            "detail": f"{type(exc).__name__}: {exc}",
        }],
        "expected": {
            "topics": list(case.expected_topics),
            "criticalRuleIds": list(case.required_rules),
        },
        "metrics": {
            "selectedTopics": [],
            "requiredTopicHits": 0,
            "requiredTopicCount": len(case.expected_topics),
            "criticalRuleHits": 0,
            "criticalRuleCount": len(case.required_rules),
            "estimatedTokens": None,
        },
    }

def route_observations(case: CaseSpec, route_value: dict[str, Any]) -> dict[str, Any]:
    selected = route_value.get("selectedTopicIds", [])
    critical = route_value.get("criticalRuleIds", [])
    references = route_value.get("references", [])
    expected_topics = set(case.expected_topics)
    selected_set = set(selected)
    irrelevant_fragments = irrelevant_reference_fragments(case)
    return {
        "selected": selected,
        "critical": critical,
        "references": references,
        "expected_topics": expected_topics,
        "selected_set": selected_set,
        "missing_topics": sorted(expected_topics - selected_set),
        "unexpected_topics": sorted(selected_set - expected_topics),
        "forbidden_hits": sorted(selected_set & set(case.forbidden_topics)),
        "missing_rules": sorted(set(case.required_rules) - set(critical)),
        "adjustment_ids": [
            item.get("ruleId")
            for item in route_value.get("task", {}).get("safetyAdjustments", [])
        ],
        "hash_freshness": reference_hashes_are_fresh(route_value),
        "expected_profile_hash": sha256(PROFILE_PATH),
        "leaked_fragments": sorted({
            fragment
            for fragment in irrelevant_fragments
            if any(reference.endswith(fragment) or reference == fragment for reference in references)
        }),
    }

def base_case_assertions(case: CaseSpec, route_value: dict[str, Any], observed: dict[str, Any]) -> list[dict[str, Any]]:
    selected = observed["selected"]
    critical = observed["critical"]
    missing_topics = observed["missing_topics"]
    unexpected_topics = observed["unexpected_topics"]
    forbidden_hits = observed["forbidden_hits"]
    missing_rules = observed["missing_rules"]
    adjustment_ids = observed["adjustment_ids"]
    stale_hash_ok, stale_hash_mismatches = observed["hash_freshness"]
    update_obligation = route_value.get("task", {}).get("updateObligation", {})
    expected_update_status = (
        "REQUIRED_EXPLICIT" if "updater" in case.flags
        else "REQUIRED_DEFAULT" if "default-updater" in case.flags
        else "EXCLUDED"
    )
    expected_update_required = expected_update_status != "EXCLUDED"
    expected_capability_ids = (
        ["update.client-check", "update.release-channel"]
        if expected_update_required else []
    )
    return [
        assertion("route-schema-v2", route_value.get("schemaVersion") == 2, expected=2,
                  observed=route_value.get("schemaVersion")),
        assertion("selection-only-not-a-pass-claim",
                  route_value.get("selectionOnly") is True
                  and route_value.get("evidenceStatus") == "NOT_EVALUATED"
                  and route_value.get("gateEvidence", {}).get("status") == "NOT_EVALUATED"),
        assertion("routing-mode", route_value.get("routingMode") == case.expected_mode, expected=case.expected_mode,
                  observed=route_value.get("routingMode")),
        assertion("fallback-reason", route_value.get("fallbackReason") == case.expected_fallback_reason,
                  expected=case.expected_fallback_reason,
                  observed=route_value.get("fallbackReason")),
        assertion("required-topics", not missing_topics, expected=list(case.expected_topics), observed=selected,
                  detail=(f"missing: {', '.join(missing_topics)}" if missing_topics else None)),
        assertion("no-unexpected-topics", not unexpected_topics, expected=list(case.expected_topics), observed=selected,
                  detail=(f"unexpected: {', '.join(unexpected_topics)}" if unexpected_topics else None)),
        assertion("near-miss-forbidden-topics", not forbidden_hits, expected=f"none of {sorted(case.forbidden_topics)}",
                  observed=forbidden_hits),
        assertion("required-critical-rules", not missing_rules, expected=list(case.required_rules), observed=critical,
                  detail=(f"missing: {', '.join(missing_rules)}" if missing_rules else None)),
        assertion("declared-risk-retained", route_value.get("task", {}).get("declaredRisk") == case.contract["risk"],
                  expected=case.contract["risk"],
                  observed=route_value.get("task", {}).get("declaredRisk")),
        assertion("effective-risk", route_value.get("task", {}).get("risk") == case.expected_effective_risk,
                  expected=case.expected_effective_risk,
                  observed=route_value.get("task", {}).get("risk")),
        assertion("safety-adjustment-rules", adjustment_ids == list(case.expected_adjustment_rules), expected=list(case.expected_adjustment_rules), observed=adjustment_ids),
        assertion(
            "typed-update-obligation",
            update_obligation.get("schemaVersion") == 1
            and update_obligation.get("scope") == "target-project-capability"
            and update_obligation.get("status") == expected_update_status
            and update_obligation.get("required") is expected_update_required
            and update_obligation.get("authorityEffect")
            == "selection-only-no-additional-authority",
            expected={
                "schemaVersion": 1,
                "scope": "target-project-capability",
                "status": expected_update_status,
                "required": expected_update_required,
                "authorityEffect": "selection-only-no-additional-authority",
            },
            observed=update_obligation,
        ),
        assertion(
            "update-capability-floor",
            route_value.get("requiredCapabilityObligationIds")
            == expected_capability_ids
            and update_obligation.get("requiredCapabilityObligationIds")
            == expected_capability_ids,
            expected=expected_capability_ids,
            observed={
                "route": route_value.get("requiredCapabilityObligationIds"),
                "task": update_obligation.get("requiredCapabilityObligationIds"),
            },
        ),
        assertion("selected-topic-cap", case.max_selected_topics is None or len(selected) <= case.max_selected_topics,
                  expected=(f"<= {case.max_selected_topics}" if case.max_selected_topics is not None else "documented exception"),
                  observed=len(selected), detail=case.cap_policy),
        assertion("context-token-estimate-present", isinstance(route_value.get("contextBudget", {}).get("estimatedReferenceTokens"), int),
                  observed=route_value.get("contextBudget", {}).get("estimatedReferenceTokens")),
        assertion("profile-hash-fresh", route_value.get("profile", {}).get("sha256") == observed["expected_profile_hash"],
                  expected=observed["expected_profile_hash"],
                  observed=route_value.get("profile", {}).get("sha256")),
        assertion("selected-reference-hashes-fresh", stale_hash_ok, expected="all selected reference hashes match current bytes",
                  observed=stale_hash_mismatches),
        assertion("no-irrelevant-media-metrics-tooling-capability", not observed["leaked_fragments"],
                  expected="no irrelevant focused-route references", observed=observed["leaked_fragments"]),
    ]

def add_optional_case_assertions(assertions: list[dict[str, Any]], case: CaseSpec, route_value: dict[str, Any], observed: dict[str, Any]) -> None:
    selected = observed["selected"]
    critical = observed["critical"]
    references = observed["references"]
    if case.expected_mode == "legacy-compatible-fallback":
        assertions.append(assertion(
            "fallback-retains-full-legacy-route",
            references == route_value.get("legacyReferences")
            and route_value.get("contextBudget", {}).get("enforced") is False,
        ))
    if "audit-authorization" in case.flags:
        assertions.append(assertion(
            "audit-only-authorization-boundary",
            route_value.get("projectEvidence", {}).get("authorization")
            == "audit-only:no-external-or-destructive-mutation"
            and "audit.read-only-unless-implementation-authorized" in critical,
        ))
    if "mixed-language-not-checked" in case.flags:
        add_capability_assertion(
            assertions, critical, "mixed-ts-rust-non-python-not-checked-semantics",
            ("not-checked", "not_checked"),
            "Router profile exposes the audit authorization rule but no criticalRuleId for unresolved non-Python graph semantics; provider behavior remains outside this route-only corpus.",
        )
    if "session-ai" in case.flags:
        add_capability_assertion(
            assertions, [*selected, *critical], "mcp-session-specific-route-contract",
            ("session", "mcp"),
            "The closed-world profile has model-context and skill-artifact coverage but no MCP/session-specific topic or criticalRuleId.",
        )
    if "external-release" in case.flags:
        assertions.append(assertion(
            "external-release-authority-and-postverify",
            {"rd.external.current-authority", "rd.external.postverify"}.issubset(critical),
        ))
    if "destructive-boundary" in case.flags:
        assertions.append(assertion(
            "destructive-retirement-remains-user-controlled",
            route_value.get("selectionOnly") is True
            and route_value.get("projectEvidence", {}).get("authorization")
            == "verification-only:retirement-requires-current-user-authorization"
            and {"rd.updater.user-control", "rd.updater.retirement"}.issubset(critical),
        ))

def add_capability_assertion(assertions: list[dict[str, Any]], candidate_ids: list[str], assertion_id: str,
                             fragments: tuple[str, ...], unchecked_detail: str) -> None:
    matching_ids = [
        item for item in candidate_ids
        if any(fragment in item.lower() for fragment in fragments)
    ]
    if matching_ids:
        assertions.append(assertion(assertion_id, True, observed=matching_ids))
    else:
        assertions.append(not_checked(assertion_id, unchecked_detail))

def successful_case_result(case: CaseSpec, route_value: dict[str, Any], observed: dict[str, Any],
                           assertions: list[dict[str, Any]]) -> dict[str, Any]:
    selected = observed["selected"]
    critical = observed["critical"]
    references = observed["references"]
    selected_set = observed["selected_set"]
    expected_topics = observed["expected_topics"]
    estimated_tokens = route_value.get("contextBudget", {}).get("estimatedReferenceTokens")
    failures = [item for item in assertions if item["status"] == "FAIL"]
    return {
        "id": case.case_id,
        "taskClass": case.task_class,
        "variant": case.variant,
        "flags": list(case.flags),
        "decision": "PASS" if not failures else "FAIL",
        "capPolicy": case.cap_policy,
        "route": {
            "routingMode": route_value.get("routingMode"),
            "fallbackReason": route_value.get("fallbackReason"),
            "selectedTopicIds": selected,
            "criticalRuleIds": critical,
            "referenceCount": len(references),
            "estimatedTokens": estimated_tokens,
            "declaredRisk": route_value.get("task", {}).get("declaredRisk"),
            "effectiveRisk": route_value.get("task", {}).get("risk"),
            "safetyAdjustments": route_value.get("task", {}).get("safetyAdjustments", []),
            "routingInputSha256": route_value.get("hashes", {}).get("routingInputSha256"),
            "selectedReferencesSha256": route_value.get("hashes", {}).get("selectedReferencesSha256"),
        },
        "expected": {
            "topics": list(case.expected_topics),
            "forbiddenTopics": list(case.forbidden_topics),
            "criticalRuleIds": list(case.required_rules),
            "effectiveRisk": case.expected_effective_risk,
            "maxSelectedTopics": case.max_selected_topics,
        },
        "assertions": assertions,
        "metrics": {
            "selectedTopics": selected,
            "relevantSelectedTopics": len(selected_set & expected_topics),
            "selectedTopicCount": len(selected),
            "requiredTopicHits": len(selected_set & expected_topics),
            "requiredTopicCount": len(expected_topics),
            "criticalRuleHits": len(set(critical) & set(case.required_rules)),
            "criticalRuleCount": len(set(case.required_rules)),
            "estimatedTokens": estimated_tokens,
            "fallbackSafe": (
                case.expected_mode != "legacy-compatible-fallback"
                or (
                    route_value.get("routingMode") == "legacy-compatible-fallback"
                    and references == route_value.get("legacyReferences")
                    and not observed["missing_rules"]
                )
            ),
            "irrelevantReferenceLeaks": len(observed["leaked_fragments"]),
        },
    }

def evaluate_case(workspace: Path, case: CaseSpec) -> dict[str, Any]:
    project, contract_path = prepare_case(workspace, case)
    try:
        route_value = router.compose_route(project, PROFILE_PATH, contract_path)
    except Exception as exc:  # preserve the rest of the corpus after one route failure
        return route_error_result(case, exc)

    observed = route_observations(case, route_value)
    assertions = base_case_assertions(case, route_value, observed)
    add_optional_case_assertions(assertions, case, route_value, observed)
    return successful_case_result(case, route_value, observed, assertions)

def percentile(values: list[int], percentile_value: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil((percentile_value / 100) * len(ordered)) - 1)
    return ordered[index]

def token_summary(values: list[int]) -> dict[str, Any]:
    if not values:
        return {
            "status": "NOT_CHECKED",
            "count": 0,
            "p50": None,
            "p95": None,
            "reason": "Router output did not expose integer token estimates.",
        }
    return {
        "status": "MEASURED",
        "count": len(values),
        "min": min(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "max": max(values),
        "mean": round(statistics.fmean(values), 2),
        "estimator": "router unicode-conservative-v1 receipt",
    }

def status_target(target_id: str, passed: bool | None, actual: Any, threshold: str) -> dict[str, Any]:
    return {
        "id": target_id,
        "status": "NOT_CHECKED" if passed is None else ("PASS" if passed else "FAIL"),
        "actual": actual,
        "threshold": threshold,
    }

def run_cases() -> list[dict[str, Any]]:
    cases = expand_cases()
    expected_count = len(CLASS_SPECS) * len(VARIANTS) + len(UPDATER_SPECS)
    if len(cases) != expected_count:
        raise AssertionError(
            f"corpus definition must contain {expected_count} cases, got {len(cases)}"
        )
    with tempfile.TemporaryDirectory(prefix="rd-router-quality-") as temp:
        workspace = Path(temp)
        return [evaluate_case(workspace, case) for case in cases]

def aggregate_quality(results: list[dict[str, Any]]) -> dict[str, Any]:
    selected_total = sum(item["metrics"]["selectedTopicCount"] for item in results)
    relevant_total = sum(item["metrics"]["relevantSelectedTopics"] for item in results)
    required_total = sum(item["metrics"]["requiredTopicCount"] for item in results)
    required_hits = sum(item["metrics"]["requiredTopicHits"] for item in results)
    critical_total = sum(item["metrics"]["criticalRuleCount"] for item in results)
    critical_hits = sum(item["metrics"]["criticalRuleHits"] for item in results)
    fallback_results = [item for item in results if item["taskClass"] == "ambiguous-legacy-fallback"]
    fallback_safe = sum(bool(item["metrics"].get("fallbackSafe")) for item in fallback_results)
    updater_results = [
        item for item in results
        if item["taskClass"] == "secure-self-update"
        or "default-updater" in item.get("flags", [])
    ]
    updater_critical_total = sum(item["metrics"]["criticalRuleCount"] for item in updater_results)
    updater_critical_hits = sum(item["metrics"]["criticalRuleHits"] for item in updater_results)
    return {
        "pass_count": sum(item["decision"] == "PASS" for item in results),
        "precision": relevant_total / selected_total if selected_total else 0.0,
        "recall": required_hits / required_total if required_total else 0.0,
        "critical_recall": critical_hits / critical_total if critical_total else 0.0,
        "fallback_results": fallback_results,
        "fallback_safe": fallback_safe,
        "fallback_ratio": fallback_safe / len(fallback_results) if fallback_results else 0.0,
        "updater_results": updater_results,
        "updater_pass_count": sum(item["decision"] == "PASS" for item in updater_results),
        "updater_critical_recall": (
            updater_critical_hits / updater_critical_total if updater_critical_total else 0.0
        ),
        "not_checked_items": [
            {"caseId": item["id"], "assertionId": check["id"], "detail": check.get("detail")}
            for item in results
            for check in item.get("assertions", [])
            if check["status"] == "NOT_CHECKED"
        ],
        "default_cap_violations": [
            item["id"] for item in results
            if item.get("capPolicy") == "default-five-card-cap"
            and item["metrics"]["selectedTopicCount"] > 5
        ],
    }

def collect_token_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    token_values = [
        item["metrics"]["estimatedTokens"] for item in results
        if isinstance(item["metrics"].get("estimatedTokens"), int)
    ]
    task_aware_values = [
        item["metrics"]["estimatedTokens"] for item in results
        if item.get("route", {}).get("routingMode") == "task-aware-v2"
        and isinstance(item["metrics"].get("estimatedTokens"), int)
    ]
    task_aware_over_target = [
        {
            "caseId": item["id"],
            "taskClass": item["taskClass"],
            "estimatedTokens": item["metrics"]["estimatedTokens"],
            "selectedTopicIds": item.get("route", {}).get("selectedTopicIds", []),
            "capPolicy": item.get("capPolicy"),
        }
        for item in sorted(
            results,
            key=lambda result: result["metrics"].get("estimatedTokens") or -1,
            reverse=True,
        )
        if item.get("route", {}).get("routingMode") == "task-aware-v2"
        and isinstance(item["metrics"].get("estimatedTokens"), int)
        and item["metrics"]["estimatedTokens"] > 6000
    ]
    default_values = [
        item["metrics"]["estimatedTokens"] for item in results
        if item.get("capPolicy") == "default-five-card-cap"
        and item.get("route", {}).get("routingMode") == "task-aware-v2"
        and isinstance(item["metrics"].get("estimatedTokens"), int)
    ]
    return {
        "all": token_summary(token_values),
        "task_aware": token_summary(task_aware_values),
        "default": token_summary(default_values),
        "task_aware_over_target": task_aware_over_target,
    }

def quality_targets(quality: dict[str, Any], tokens: dict[str, Any]) -> list[dict[str, Any]]:
    expected_count = len(CLASS_SPECS) * len(VARIANTS) + len(UPDATER_SPECS)
    task_aware_tokens = tokens["task_aware"]
    token_target_supported = (
        task_aware_tokens["status"] == "MEASURED"
        and task_aware_tokens["p50"] is not None
        and task_aware_tokens["p95"] is not None
    )
    return [
        status_target("case-pass-count", quality["pass_count"] == expected_count,
                      f"{quality['pass_count']}/{expected_count}",
                      f"{expected_count}/{expected_count}"),
        status_target("critical-rule-recall", quality["critical_recall"] == 1.0,
                      round(quality["critical_recall"], 6), "100%"),
        status_target("required-topic-recall", quality["recall"] >= 0.98,
                      round(quality["recall"], 6), ">= 98%"),
        status_target("selected-topic-precision", quality["precision"] >= 0.90,
                      round(quality["precision"], 6), ">= 90%"),
        status_target("fallback-safety", quality["fallback_ratio"] == 1.0,
                      f"{quality['fallback_safe']}/{len(quality['fallback_results'])}", "100%"),
        status_target("default-five-card-cap", not quality["default_cap_violations"],
                      quality["default_cap_violations"], "0 violations"),
        status_target(
            "task-aware-token-p50",
            (task_aware_tokens["p50"] <= 4000) if token_target_supported else None,
            task_aware_tokens["p50"],
            "<= 4000 estimated tokens",
        ),
        status_target(
            "task-aware-token-p95",
            (task_aware_tokens["p95"] <= 6000) if token_target_supported else None,
            task_aware_tokens["p95"],
            "<= 6000 estimated tokens",
        ),
    ]

def aggregate_decision(
    targets: list[dict[str, Any]],
    not_checked_items: list[dict[str, Any]],
) -> tuple[str, str]:
    failed_targets = [item["id"] for item in targets if item["status"] == "FAIL"]
    unchecked_targets = [item["id"] for item in targets if item["status"] == "NOT_CHECKED"]
    target_status = "PASS" if not failed_targets and not unchecked_targets else (
        "NOT_CHECKED" if not failed_targets else "FAIL"
    )
    decision = target_status
    if decision == "PASS" and not_checked_items:
        decision = "PASS_WITH_NOT_CHECKED"
    return decision, target_status

def report_metrics(
    results: list[dict[str, Any]],
    quality: dict[str, Any],
    tokens: dict[str, Any],
) -> dict[str, Any]:
    return {
        "casePassCount": quality["pass_count"],
        "caseCount": len(results),
        "selectedTopicPrecision": round(quality["precision"], 6),
        "requiredTopicRecall": round(quality["recall"], 6),
        "criticalRuleRecall": round(quality["critical_recall"], 6),
        "fallbackSafety": {
            "safe": quality["fallback_safe"],
            "count": len(quality["fallback_results"]),
            "ratio": round(quality["fallback_ratio"], 6),
        },
        "defaultFiveCardCapViolations": quality["default_cap_violations"],
        "focusedIrrelevantReferenceLeakCount": sum(
            item["metrics"].get("irrelevantReferenceLeaks", 0) for item in results
        ),
        "estimatedTokens": {
            "allRoutesIncludingLegacy": tokens["all"],
            "taskAwareRoutes": tokens["task_aware"],
            "defaultFiveCardRoutes": tokens["default"],
            "taskAwareRoutesOver6000": tokens["task_aware_over_target"],
        },
        "notCheckedAssertionCount": len(quality["not_checked_items"]),
    }

def updater_metrics(quality: dict[str, Any]) -> dict[str, Any]:
    updater_results = quality["updater_results"]
    return {
        "casePassCount": quality["updater_pass_count"],
        "caseCount": len(updater_results),
        "criticalRuleRecall": round(quality["updater_critical_recall"], 6),
        "riskFloors": {
            "discoveryRemainsLow": any(
                item["id"] == "updater.discovery-low"
                and item.get("route", {}).get("effectiveRisk") == "low"
                for item in updater_results
            ),
            "promotionRaisedToHigh": any(
                item["id"] == "updater.implementation-promotion-risk-floor"
                and item.get("route", {}).get("effectiveRisk") == "high"
                for item in updater_results
            ),
            "completionRaisedToCritical": any(
                item["id"] == "updater.completion-destructive"
                and item.get("route", {}).get("effectiveRisk") == "critical"
                for item in updater_results
            ),
        },
    }

def build_report() -> dict[str, Any]:
    started = time.perf_counter()
    results = run_cases()
    quality = aggregate_quality(results)
    tokens = collect_token_metrics(results)
    targets = quality_targets(quality, tokens)
    decision, target_status = aggregate_decision(targets, quality["not_checked_items"])

    return {
        "schemaVersion": 1,
        "corpusVersion": "1.0",
        "decision": decision,
        "targetStatus": target_status,
        "scope": {
            "caseCount": len(results),
            "originalTaskClasses": len(CLASS_SPECS),
            "originalTaskClassIds": [item.task_class for item in CLASS_SPECS],
            "variantsPerOriginalClass": len(VARIANTS),
            "secureUpdaterCases": len(UPDATER_SPECS),
            "sideEffects": "temporary fixture writes only; canonical router/profile are read-only",
        },
        "provenance": {
            "routerPath": str(ROUTER_PATH),
            "routerSha256": sha256(ROUTER_PATH),
            "profilePath": str(PROFILE_PATH),
            "profileSha256": sha256(PROFILE_PATH),
            "composeEntryPoint": "project_profile_gate.compose_route",
        },
        "metrics": report_metrics(results, quality, tokens),
        "updaterMetrics": updater_metrics(quality),
        "targets": targets,
        "notCheckedAssertions": quality["not_checked_items"],
        "cases": results,
        "elapsedMs": round((time.perf_counter() - started) * 1000, 3),
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.quiet and not args.output:
        parser.error("--quiet requires --output")
    try:
        report = build_report()
        if args.self_test:
            expected_count = len(CLASS_SPECS) * len(VARIANTS) + len(UPDATER_SPECS)
            report["selfTest"] = {
                "status": "PASS" if report["scope"]["caseCount"] == expected_count else "FAIL",
                "checks": [
                    f"{expected_count} deterministic cases constructed",
                    "canonical compose entry point invoked",
                    "supported assertions and NOT_CHECKED are separated",
                    "aggregate metrics recomputed from case evidence",
                ],
            }
    except Exception as exc:
        report = {
            "schemaVersion": 1,
            "corpusVersion": "1.0",
            "decision": "FAIL",
            "targetStatus": "FAIL",
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    if args.output:
        atomic_write_json(args.output, report)
    if not args.quiet:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("targetStatus") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
