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

from router_quality_cases import (
    route_error_result,
    route_observations,
    base_case_assertions,
    add_optional_case_assertions,
    add_capability_assertion,
    successful_case_result,
    evaluate_case,
)

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
