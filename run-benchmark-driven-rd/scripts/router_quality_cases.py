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
from pathlib import Path
from typing import Any

import project_profile_gate as router
from router_quality_catalog import (
    BASE_RULES,
    BASE_TOPICS,
    CLASS_SPECS,
    SECURITY_CAPABILITY_IDS,
    UPDATER_SPECS,
    VARIANTS,
    CaseSpec,
    ClassSpec,
)
from router_quality_fixtures import (
    ROOT,
    ROUTER_PATH,
    PROFILE_PATH,
    sha256,
    unique,
    make_contract,
    expand_cases,
    write_fixture_files,
    assertion,
    not_checked,
    reference_hashes_are_fresh,
    irrelevant_reference_fragments,
    prepare_case,
)

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

def _route_selection_assertions(adjustment_ids, case, critical, forbidden_hits, missing_rules, missing_topics, route_value, selected, unexpected_topics):
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
    ]

def _route_obligation_and_identity_assertions(case, expected_capability_ids, expected_security_required, expected_security_status, expected_update_required, expected_update_status, observed, route_value, security_obligation, selected, stale_hash_mismatches, stale_hash_ok, update_obligation):
    return [
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
            "combined-capability-floor",
            route_value.get("requiredCapabilityObligationIds")
            == expected_capability_ids
            and update_obligation.get("requiredCapabilityObligationIds")
            == (["update.client-check", "update.release-channel"]
                if expected_update_required else []),
            expected=expected_capability_ids,
            observed={
                "route": route_value.get("requiredCapabilityObligationIds"),
                "updateTask": update_obligation.get("requiredCapabilityObligationIds"),
                "securityTask": security_obligation.get("requiredCapabilityObligationIds"),
            },
        ),
        assertion(
            "typed-security-assessment-obligation",
            security_obligation.get("schemaVersion") == 1
            and security_obligation.get("scope") == "target-project-security-assessment"
            and security_obligation.get("status") == expected_security_status
            and security_obligation.get("required") is expected_security_required
            and security_obligation.get("requiredCapabilityObligationIds")
            == (list(SECURITY_CAPABILITY_IDS) if expected_security_required else [])
            and security_obligation.get("requiredSecurityControlIds")
            == (list(SECURITY_CAPABILITY_IDS) if expected_security_required else [])
            and security_obligation.get("authorityEffect")
            == "selection-only-no-scan-or-contact-authority",
            expected={
                "status": expected_security_status,
                "required": expected_security_required,
                "requiredCapabilityObligationIds": (
                    list(SECURITY_CAPABILITY_IDS) if expected_security_required else []
                ),
                "requiredSecurityControlIds": (
                    list(SECURITY_CAPABILITY_IDS) if expected_security_required else []
                ),
                "authorityEffect": "selection-only-no-scan-or-contact-authority",
            },
            observed=security_obligation,
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
    security_obligation = route_value.get("task", {}).get("securityAssessmentObligation", {})
    expected_update_status = (
        "REQUIRED_EXPLICIT" if "updater" in case.flags
        else "REQUIRED_DEFAULT" if "default-updater" in case.flags
        else "EXCLUDED"
    )
    expected_update_required = expected_update_status != "EXCLUDED"
    expected_security_status = (
        "REQUIRED_EXPLICIT" if case.contract.get("taskIntent") == "security-assessment"
        else "REQUIRED_ROUTE" if "security-assessment" in case.expected_topics
        and case.contract.get("taskIntent") != "audit"
        and case.expected_mode != "legacy-compatible-fallback"
        else "EXCLUDED"
    )
    expected_security_required = expected_security_status != "EXCLUDED"
    expected_capability_ids = [
        *(["update.client-check", "update.release-channel"]
          if expected_update_required else []),
        *(SECURITY_CAPABILITY_IDS if expected_security_required else ()),
    ]
    return [
        *_route_selection_assertions(adjustment_ids, case, critical, forbidden_hits, missing_rules, missing_topics, route_value, selected, unexpected_topics),
        *_route_obligation_and_identity_assertions(case, expected_capability_ids, expected_security_required, expected_security_status, expected_update_required, expected_update_status, observed, route_value, security_obligation, selected, stale_hash_mismatches, stale_hash_ok, update_obligation),
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
    if "security-assessment" in case.flags:
        assertions.append(assertion(
            "security-route-grants-no-contact-authority",
            route_value.get("selectionOnly") is True
            and route_value.get("task", {}).get("securityAssessmentObligation", {})
            .get("authorityEffect") == "selection-only-no-scan-or-contact-authority"
            and route_value.get("projectEvidence", {}).get("authorization")
            == "audit-only:no-external-or-destructive-mutation",
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
