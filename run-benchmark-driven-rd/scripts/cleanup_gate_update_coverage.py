#!/usr/bin/env python3
"""Narrow Cleanup provider-schema compatibility for update coverage."""

from __future__ import annotations

import json
from typing import Any


SUPPORTED_PROVIDER_SCHEMAS = {"1.1", "1.2"}
UPDATE_COVERAGE_CLASSES = {
    "managed", "check-only", "safe-auto-update", "manual-only", "no-origin"
}
UPDATE_COVERAGE_FIELDS = {
    "unit", "classification", "declared_classification", "canonical_origin",
    "origin_source", "manager", "assurance", "evidence",
    "requires_deep_validation", "errors",
}


def schema_required_fields(schema: str) -> set[str]:
    return {"update_coverage"} if schema == "1.2" else set()


def validate_update_coverage(
    report: dict[str, Any], findings: list[Any]
) -> list[str]:
    if str(report.get("schema_version")) != "1.2":
        return []
    errors: list[str] = []
    coverage = report.get("update_coverage")
    if not isinstance(coverage, dict):
        errors.append("update_coverage must be an object for provider schema 1.2")
    else:
        missing = sorted(UPDATE_COVERAGE_FIELDS - set(coverage))
        if missing:
            errors.append("update_coverage missing fields: " + ", ".join(missing))
        if coverage.get("classification") not in UPDATE_COVERAGE_CLASSES:
            errors.append("update_coverage.classification is outside the supported closed world")
        if not isinstance(coverage.get("evidence"), list):
            errors.append("update_coverage.evidence must be a list")
        if not isinstance(coverage.get("errors"), list):
            errors.append("update_coverage.errors must be a list")
        if not isinstance(coverage.get("requires_deep_validation"), bool):
            errors.append("update_coverage.requires_deep_validation must be boolean")
    update_findings = [
        item for item in findings
        if isinstance(item, dict) and item.get("dimension") == 11
    ]
    if len(update_findings) != 1:
        errors.append("provider schema 1.2 requires exactly one D11 update finding")
    elif isinstance(coverage, dict) and update_findings[0].get("details") != coverage:
        errors.append("D11 details do not preserve the update_coverage record")
    return errors


def schema_12_fixture(base: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    coverage = {
        "unit": ".", "classification": "check-only",
        "declared_classification": "check-only",
        "canonical_origin": "https://github.com/example/project",
        "origin_source": "config", "manager": None,
        "assurance": "declared-evidence",
        "evidence": [{"path": "update-check.json", "bytes": 2, "sha256": "b" * 64}],
        "requires_deep_validation": False, "errors": [],
    }
    report = json.loads(json.dumps(base))
    report.update({"schema_version": "1.2", "update_coverage": coverage})
    report["findings"].append({
        "dimension": 11, "status": "REVIEW", "code": "update-coverage",
        "details": coverage,
    })
    report["summary"]["review"] += 1
    return report, coverage
