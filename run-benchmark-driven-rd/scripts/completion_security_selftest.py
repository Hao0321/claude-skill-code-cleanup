"""Deterministic fixtures and negative controls for completion closure."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable

from capability_gate import evaluate as evaluate_capabilities
from project_profile_gate import compose_route, sha256_json

from completion_closure_common import *  # noqa: F403
from completion_closure_checks import evaluate
from completion_test_fixtures import (
    fixture_document,
    _security_fixture_report,
)

def _test_security_receipt_metadata(adapters, root, security_document):
    report = evaluate(
        security_document, root,
        **{**adapters, "security_verifier": lambda _root, _receipt: {"status": "NOT_CHECKED"}},
    )
    if not any(item["code"] == "security-assessment-block" for item in report["findings"]):
        raise AssertionError(f"partial security receipt escaped closure: {report}")

    report = evaluate(
        security_document, root,
        **{**adapters, "security_verifier": lambda _root, _receipt: {
            **_security_fixture_report(),
            "controlCoverage": {
                **_security_fixture_report()["controlCoverage"],
                "executedCells": 1,
            },
        }},
    )
    if not any(item["code"] == "security-control-coverage" for item in report["findings"]):
        raise AssertionError(f"shallow security control coverage escaped closure: {report}")

    report = evaluate(
        security_document, root,
        **{**adapters, "security_verifier": lambda _root, _receipt: {
            **_security_fixture_report(version="0.9.0")
        }},
    )
    if not any(item["code"] == "security-assessment-version-drift" for item in report["findings"]):
        raise AssertionError(f"stale security target escaped closure: {report}")

    report = evaluate(
        security_document, root,
        **{**adapters, "security_verifier": lambda _root, _receipt:
           _security_fixture_report(receipt_schema_version=1)},
    )
    if not any(item["code"] == "security-assessment-schema" for item in report["findings"]):
        raise AssertionError(f"legacy security receipt escaped closure: {report}")

    report = evaluate(
        security_document, root,
        **{**adapters, "security_verifier": lambda _root, _receipt:
           _security_fixture_report(age_seconds=MAX_COMPLETION_SECURITY_AGE_SECONDS + 1)},
    )
    if not any(item["code"] == "security-assessment-stale" for item in report["findings"]):
        raise AssertionError(f"old security receipt escaped closure: {report}")

    expected_grant = "c" * 64
    external = json.loads(json.dumps(security_document))
    external["checks"][-1]["expectedGrantSha256"] = expected_grant
    report = evaluate(
        external, root,
        **{**adapters, "security_verifier": lambda _root, _receipt:
           _security_fixture_report(
               external_contact=True,
               frozen_grant_sha256="d" * 64,
           )},
    )
    if not any(item["code"] == "security-assessment-grant" for item in report["findings"]):
        raise AssertionError(f"mismatched external grant escaped closure: {report}")

    report = evaluate(
        external, root,
        **{**adapters, "security_verifier": lambda _root, _receipt:
           _security_fixture_report(
               external_contact=True,
               frozen_grant_sha256=expected_grant,
           )},
    )
    if report["status"] != "GREEN":
        raise AssertionError(f"matching external grant was rejected: {report}")


def _test_security_floor_and_receipt_negatives(
    root: Path,
    security_document: dict[str, Any],
    security_ids: list[str],
    adapters: dict[str, Any],
) -> None:
    missing = json.loads(json.dumps(security_document))
    missing["checks"].pop()
    missing["requiredCheckIds"].remove("security")
    report = evaluate(missing, root, **adapters)
    if not any(item["code"] == "security-assessment-floor" for item in report["findings"]):
        raise AssertionError(f"missing security check escaped closure: {report}")

    partial = json.loads(json.dumps(security_document))
    partial["checks"][2]["requiredObligationIds"] = [security_ids[0]]
    report = evaluate(partial, root, **adapters)
    if not any(item["code"] == "route-capability-floor" for item in report["findings"]):
        raise AssertionError(f"partial security floor escaped closure: {report}")

    split = json.loads(json.dumps(security_document))
    split["checks"][2]["requiredObligationIds"] = security_ids[:3]
    split_ledger_path = root / "product" / "capabilities-second.json"
    split_ledger_path.write_text(json.dumps({
        "product": "Fixture", "productVersion": "1.0.0",
        "requiredObligationIds": security_ids[3:],
    }), encoding="utf-8")
    split["requiredCheckIds"].append("capabilities-second")
    split["checks"].append({
        "id": "capabilities-second", "kind": "capability-ledger",
        "path": "product/capabilities-second.json",
        "packageJson": "product/package.json",
        "requiredObligationIds": security_ids[3:],
    })
    report = evaluate(split, root, **adapters)
    if not any(item["code"] == "route-capability-floor" for item in report["findings"]):
        raise AssertionError(f"split security floors escaped closure: {report}")

    case_drift = json.loads(json.dumps(security_document))
    case_drift["checks"][2]["requiredObligationIds"] = [item.upper() for item in security_ids]
    report = evaluate(case_drift, root, **adapters)
    if not any(item["code"] == "route-capability-floor" for item in report["findings"]):
        raise AssertionError(f"case-drifted security floor escaped closure: {report}")

    _test_security_receipt_metadata(adapters, root, security_document)


def _test_public_subject_and_artifact_controls(
    root: Path,
    security_document: dict[str, Any],
    adapters: dict[str, Any],
) -> None:
    minimal = json.loads(json.dumps(security_document))
    minimal["checks"] = [
        check for check in minimal["checks"]
        if check["kind"] in {
            "route-receipt", "capability-ledger", "security-assessment"
        }
    ]
    minimal["requiredCheckIds"] = [check["id"] for check in minimal["checks"]]
    report = evaluate(minimal, root, **adapters)
    if not any(item["code"] == "public-check-kind-floor" for item in report["findings"]):
        raise AssertionError(f"three-check public closure escaped its kind floor: {report}")

    decoy_root = root / "decoy"
    decoy_root.mkdir(parents=True, exist_ok=True)
    (decoy_root / "receipt.json").write_text(
        (root / "product" / "receipt.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    decoy_artifact = decoy_root / "setup.exe"
    decoy_artifact.write_bytes(b"decoy installer")
    for kind in ("cleanup-promotion", "delivery-contract", "build-receipt"):
        decoy = json.loads(json.dumps(security_document))
        check = next(item for item in decoy["checks"] if item["kind"] == kind)
        check["projectRoot"] = "decoy"
        report = evaluate(decoy, root, **adapters)
        if not any(item["code"] == "public-check-subject" for item in report["findings"]):
            raise AssertionError(f"sibling {kind} evidence escaped subject binding: {report}")

    decoy_file = json.loads(json.dumps(security_document))
    artifact_check = next(
        item for item in decoy_file["checks"] if item["kind"] == "file-identity"
    )
    artifact_check.update({
        "path": "decoy/setup.exe", "projectRoot": "decoy",
        **file_identity(decoy_artifact),
    })
    report = evaluate(decoy_file, root, **adapters)
    if not any(item["code"] == "public-artifact-binding" for item in report["findings"]):
        raise AssertionError(f"sibling release artifact escaped binding: {report}")

    other_artifact = root / "product" / "dist" / "other.exe"
    other_artifact.write_bytes(b"other installer")
    mismatched = json.loads(json.dumps(security_document))
    artifact_check = next(
        item for item in mismatched["checks"] if item["kind"] == "file-identity"
    )
    artifact_check.update({
        "path": "product/dist/other.exe", **file_identity(other_artifact),
    })
    report = evaluate(mismatched, root, **adapters)
    if not any(item["code"] == "public-artifact-binding" for item in report["findings"]):
        raise AssertionError(f"unbound release artifact escaped closure: {report}")


def _replay_security_closure_matrix(adapters, ledger_path, original_ledger, original_route, root, route_path, security_document, security_ids, security_ledger):
    try:
        report = evaluate(security_document, root, **adapters)
        if report["status"] != "GREEN":
            raise AssertionError(f"valid security closure was rejected: {report}")
        report = evaluate(
            security_document,
            root,
            **{**adapters, "capability_evaluator": evaluate_capabilities},
        )
        if report["status"] != "GREEN":
            raise AssertionError(f"real capability/security binding was rejected: {report}")

        _test_public_subject_and_artifact_controls(
            root, security_document, adapters
        )

        decoy_receipt = root / "decoy" / ".rd" / "security-assessment.json"
        decoy_receipt.parent.mkdir(parents=True)
        decoy_receipt.write_text("{}", encoding="utf-8")
        decoy = json.loads(json.dumps(security_document))
        decoy["checks"][-1]["projectRoot"] = "decoy"
        report = evaluate(decoy, root, **adapters)
        if not any(
            item["code"] == "security-assessment-subject"
            for item in report["findings"]
        ):
            raise AssertionError(f"sibling decoy security receipt escaped closure: {report}")

        wrong_plan = json.loads(json.dumps(security_document))
        wrong_plan["checks"][-1]["expectedPlanSha256"] = "c" * 64
        report = evaluate(wrong_plan, root, **adapters)
        if not any(item["code"] == "security-assessment-plan" for item in report["findings"]):
            raise AssertionError(f"unbound security plan escaped closure: {report}")

        untyped_ledger = json.loads(json.dumps(security_ledger))
        for obligation in untyped_ledger["obligations"]:
            obligation["evidence"] = [{
                "kind": "file",
                "value": ".rd/security-assessment.json",
            }]
        ledger_path.write_text(json.dumps(untyped_ledger), encoding="utf-8")
        report = evaluate(security_document, root, **adapters)
        ledger_path.write_text(json.dumps(security_ledger), encoding="utf-8")
        if not any(
            item["code"] == "security-capability-binding"
            for item in report["findings"]
        ):
            raise AssertionError(f"generic security file evidence escaped closure: {report}")

        route_drift_ledger = json.loads(json.dumps(security_ledger))
        next(
            item
            for item in route_drift_ledger["obligations"]
            if item["id"] == "security.scan-scope"
        )["evidence"][0]["routingInputSha256"] = "d" * 64
        ledger_path.write_text(json.dumps(route_drift_ledger), encoding="utf-8")
        report = evaluate(security_document, root, **adapters)
        ledger_path.write_text(json.dumps(security_ledger), encoding="utf-8")
        if not any(
            item["code"] == "security-capability-binding"
            for item in report["findings"]
        ):
            raise AssertionError(f"route-drifted security evidence escaped closure: {report}")

        _test_security_floor_and_receipt_negatives(
            root, security_document, security_ids, adapters
        )
    finally:
        ledger_path.write_text(original_ledger, encoding="utf-8")
        route_path.write_text(original_route, encoding="utf-8")


def _test_security_closure(
    root: Path, document: dict[str, Any], adapters: dict[str, Any]
) -> None:
    security_ids = [
        "security.scan-scope",
        "security.scan-coverage",
        "security.scanner-provenance",
        "security.finding-normalization",
        "security.engine-admission",
        "security.adapter-integrity",
    ]
    ledger_path = root / "product" / "capabilities.json"
    route_path = root / "evidence" / "route.json"
    original_ledger = ledger_path.read_text(encoding="utf-8")
    original_route = route_path.read_text(encoding="utf-8")
    security_document = json.loads(json.dumps(document))
    security_document["scope"] = "public"
    security_route = compose_route(
        root / "product",
        task_intent="completion",
        stage="completion",
        artifact="release",
        risk="critical",
        context_budget_tokens=50_000,
    )
    route_path.write_text(json.dumps(security_route), encoding="utf-8")
    security_receipt_path = root / "product" / ".rd" / "security-assessment.json"
    security_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    security_receipt_path.write_text("{}", encoding="utf-8")
    route_check = next(check for check in security_document["checks"] if check["id"] == "route")
    route_check.update(file_identity(route_path))
    security_document["requiredCheckIds"].append("security")
    security_document["checks"][2]["requiredObligationIds"].extend(security_ids)
    security_document["checks"].append({
        "id": "security", "kind": "security-assessment",
        "projectRoot": "product", "receipt": ".rd/security-assessment.json",
        "expectedPlanSha256": "b" * 64,
        "expectedSnapshotSha256": "a" * 64,
    })
    security_ledger = json.loads(original_ledger)
    security_ledger["requiredObligationIds"].extend(security_ids)
    security_receipt_identity = file_identity(security_receipt_path)
    security_ledger["obligations"] = [
        {
            "id": "update.client-check",
            "status": "verified",
            "requiredFor": ["internal", "public"],
            "verifiedVersion": "1.0.0",
            "evidence": [{"kind": "npm_script", "value": "check:update"}],
        },
        {
            "id": "update.release-channel",
            "status": "verified",
            "requiredFor": ["public"],
            "verifiedVersion": "1.0.0",
            "evidence": [{"kind": "npm_script", "value": "verify:release"}],
        },
    ] + [{
        "id": capability_id,
        "status": "verified",
        "requiredFor": ["internal", "public"],
        "verifiedVersion": "1.0.0",
        "evidence": [{
            "kind": "security-assessment",
            "capabilityId": capability_id,
            "value": ".rd/security-assessment.json",
            "receiptBytes": security_receipt_identity["bytes"],
            "receiptSha256": security_receipt_identity["sha256"],
            "planSha256": "b" * 64,
            "snapshotSha256": "a" * 64,
            "routingInputSha256": security_route["hashes"]["routingInputSha256"],
            "controlCoverageSha256": sha256_json(list(SECURITY_CONTROL_IDS)),
        }],
    } for capability_id in security_ids]
    ledger_path.write_text(json.dumps(security_ledger), encoding="utf-8")
    _replay_security_closure_matrix(adapters, ledger_path, original_ledger, original_route, root, route_path, security_document, security_ids, security_ledger)
