"""Completion-closure check evaluation and cross-evidence binding."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
from typing import Any

from capability_gate import evaluate as evaluate_capabilities
from delivery_contract_gate import evaluate as evaluate_delivery
from evidence_identity import valid_identity
from project_profile_gate import sha256_json
from verify_cleanup_evidence import verify as verify_cleanup

from completion_closure_common import *  # noqa: F403
from completion_closure_route import *  # noqa: F403


def _check_cleanup(
    check: dict[str, Any], path: Path, root: Path, check_id: str,
    fail: FailureSink, verifier: CleanupVerifier,
) -> dict[str, Any] | None:
    envelope, envelope_identity = _read_json_with_identity(path)
    summary = envelope.get("report", {}).get("summary", {})
    project_root, error = _resolve(root, check.get("projectRoot"), directory=True)
    target = envelope.get("report", {}).get("target")
    if error or project_root is None:
        fail("public-check-subject", "Cleanup project root is missing or unsafe", check_id)
        return None
    try:
        target_root = _lexical_absolute(Path(target)) if isinstance(target, str) else None
    except (OSError, ValueError):
        target_root = None
    if target_root != project_root or _path_chain_error(project_root, directory=True):
        fail("public-check-subject", "Cleanup evidence belongs to another project", check_id)
    if envelope.get("phase") != "promotion" or envelope.get("decision") != "ALLOW":
        fail("cleanup-not-promoted", "Cleanup evidence must be an allowed promotion", check_id)
    if envelope.get("review_policy") != "block" or summary.get("fail") != 0 or summary.get("review") != 0:
        fail("cleanup-not-strict", "completion requires strict Cleanup with zero FAIL and REVIEW", check_id)
    result = verifier(path)
    if file_identity(path) != envelope_identity:
        fail("cleanup-not-fresh", "Cleanup evidence changed during verification", check_id)
    if result.get("status") != "FRESH":
        fail("cleanup-not-fresh", "Cleanup promotion is stale or measurement-blocked", check_id, result=result)
    return {"kind": "cleanup-promotion", "projectRoot": project_root}


def _check_delivery(check: dict[str, Any], path: Path, root: Path, check_id: str,
                    product: str, version: str, fail: FailureSink,
                    evaluator: DeliveryEvaluator) -> dict[str, Any] | None:
    project_root, project_error = _resolve(
        root, check.get("projectRoot"), directory=True
    )
    if project_error or project_root is None:
        fail("public-check-subject", "delivery project root is missing or unsafe", check_id)
        return None
    evidence_root_value = check.get("evidenceRoot")
    if evidence_root_value in (None, "."):
        evidence_root = project_root
    else:
        evidence_root, error = _resolve(root, evidence_root_value, directory=True)
        if error or evidence_root is None or evidence_root != project_root:
            fail("unsafe-path", f"delivery evidenceRoot: {error}", check_id)
            return
    delivery = _read_json(path)
    result = evaluator(delivery, evidence_root)
    if result.get("status") != "GREEN":
        fail("delivery-block", "delivery contract did not close", check_id, result=result)
    if result.get("product") != product or result.get("productVersion") != version:
        fail("delivery-version-drift", "delivery identity differs from completion identity", check_id)
    envelope = delivery.get("deliveryEnvelope")
    envelope_identity = (
        {"bytes": envelope.get("bytes"), "sha256": envelope.get("sha256")}
        if isinstance(envelope, dict) and valid_identity(envelope)
        else None
    )
    if envelope_identity is None:
        fail("public-artifact-binding", "delivery envelope identity is missing", check_id)
    return {
        "kind": "delivery-contract",
        "projectRoot": project_root,
        "identity": envelope_identity,
    }


def _security_ledger_bindings(
    ledger: dict[str, Any], product_root: Path, check_id: str, fail: FailureSink,
) -> dict[str, dict[str, Any]]:
    obligations = ledger.get("obligations")
    if not isinstance(obligations, list):
        fail("security-capability-binding", "security ledger obligations are missing", check_id)
        return {}
    by_id = {
        item.get("id"): item
        for item in obligations
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    allowed_fields = {
        "kind", "capabilityId", "value", "receiptBytes", "receiptSha256",
        "planSha256", "snapshotSha256", "routingInputSha256",
        "controlCoverageSha256",
    }
    bindings: dict[str, dict[str, Any]] = {}
    for capability_id in sorted(SECURITY_CAPABILITY_IDS):
        obligation = by_id.get(capability_id)
        if not isinstance(obligation, dict) or obligation.get("status") != "verified":
            fail("security-capability-binding", "security obligation is not verified", check_id)
            continue
        evidence = obligation.get("evidence")
        typed = [
            item for item in evidence
            if isinstance(item, dict) and item.get("kind") == "security-assessment"
        ] if isinstance(evidence, list) else []
        if len(typed) != 1:
            fail(
                "security-capability-binding",
                "security obligation needs exactly one typed assessment binding",
                check_id,
            )
            continue
        binding = typed[0]
        if set(binding) != allowed_fields or binding.get("capabilityId") != capability_id:
            fail("security-capability-binding", "security binding schema or role drifted", check_id)
            continue
        receipt_path, receipt_error = _resolve(product_root, binding.get("value"))
        receipt_bytes = binding.get("receiptBytes")
        digests = (
            binding.get("receiptSha256"),
            binding.get("planSha256"),
            binding.get("snapshotSha256"),
            binding.get("routingInputSha256"),
            binding.get("controlCoverageSha256"),
        )
        if (
            receipt_error
            or receipt_path is None
            or isinstance(receipt_bytes, bool)
            or not isinstance(receipt_bytes, int)
            or receipt_bytes <= 0
            or any(not isinstance(value, str) or not SHA256_RE.fullmatch(value) for value in digests)
        ):
            fail("security-capability-binding", "security binding identity is invalid", check_id)
            continue
        identity = file_identity(receipt_path)
        if identity != {
            "bytes": receipt_bytes,
            "sha256": binding["receiptSha256"],
        }:
            fail("security-capability-binding", "security receipt identity drifted", check_id)
            continue
        bindings[capability_id] = {
            **binding,
            "receiptPath": receipt_path,
        }
    return bindings


def _check_capabilities(check: dict[str, Any], manifest: Path, root: Path, check_id: str,
                        scope: str, product: str, version: str, fail: FailureSink,
                        evaluator: CapabilityEvaluator) -> dict[str, Any] | None:
    package, error = _resolve(root, check.get("packageJson"))
    if error or package is None:
        fail("unsafe-path", f"capability packageJson: {error}", check_id)
        return
    ledger = _read_json(manifest)
    floor = check.get("requiredObligationIds")
    if not isinstance(floor, list) or not floor or any(
        not isinstance(item, str) or not item for item in floor
    ):
        fail(
            "capability-obligation-floor",
            "capability check requires a non-empty requiredObligationIds floor",
            check_id,
        )
        floor = []
    elif len(set(floor)) != len(floor):
        fail(
            "capability-obligation-floor",
            "capability requiredObligationIds floor contains duplicates",
            check_id,
        )
    declared = ledger.get("requiredObligationIds")
    if not isinstance(declared, list) or any(
        not isinstance(item, str) or not item for item in declared
    ):
        fail(
            "capability-obligation-floor",
            "capability ledger has no valid requiredObligationIds",
            check_id,
        )
        declared = []
    missing_floor = sorted(set(floor) - set(declared))
    if missing_floor:
        fail(
            "capability-obligation-floor",
            "capability ledger omitted route-required obligations",
            check_id,
            missing=missing_floor,
        )
    result = evaluator(ledger, package.parent, _read_json(package), scope)
    if result.get("status") != "GREEN":
        fail("capability-block", f"{scope} capability obligations remain open", check_id, result=result)
    if ledger.get("product") != product or ledger.get("productVersion") != version:
        fail("capability-version-drift", "capability identity differs from completion identity", check_id)
    security_bindings = (
        _security_ledger_bindings(ledger, package.parent, check_id, fail)
        if SECURITY_CAPABILITY_IDS.issubset(set(floor))
        else {}
    )
    return {
        "checkId": check_id,
        "projectRoot": package.parent,
        "securityBindings": security_bindings,
    }


def _check_receipt(
    check: dict[str, Any], root: Path, check_id: str, fail: FailureSink,
    verifier: ReceiptVerifier,
) -> dict[str, Any] | None:
    project_root, error = _resolve(root, check.get("projectRoot"), directory=True)
    receipt = check.get("receipt")
    if error or project_root is None:
        fail("unsafe-path", f"build receipt projectRoot: {error}", check_id)
        return
    receipt_path, receipt_error = _resolve(project_root, receipt)
    if receipt_error or receipt_path is None:
        fail("unsafe-path", f"build receipt: {receipt_error}", check_id)
        return
    receipt_document, receipt_identity = _read_json_with_identity(receipt_path)
    result = verifier(project_root, receipt)
    if file_identity(receipt_path) != receipt_identity:
        fail("build-receipt-block", "build receipt changed during verification", check_id)
    if result.get("status") != "GREEN":
        fail("build-receipt-block", "live build receipt is stale or invalid", check_id, result=result)
    output_identities = {
        (item.get("bytes"), item.get("sha256"))
        for item in receipt_document.get("outputs", [])
        if isinstance(item, dict) and valid_identity(item)
    } if isinstance(receipt_document.get("outputs"), list) else set()
    return {
        "kind": "build-receipt",
        "projectRoot": project_root,
        "outputIdentities": output_identities,
    }


def _security_control_digest(
    result: dict[str, Any], check_id: str, fail: FailureSink,
) -> str | None:
    coverage = (
        result.get("controlCoverage")
        if isinstance(result.get("controlCoverage"), dict)
        else {}
    )
    expected_digest = sha256_json(list(SECURITY_CONTROL_IDS))
    target_count = coverage.get("targetCount")
    required_cells = coverage.get("requiredCells")
    if (
        coverage.get("profile") != SECURITY_CONTROL_PROFILE
        or coverage.get("requiredControlIdsSha256") != expected_digest
        or coverage.get("requiredControls") != len(SECURITY_CONTROL_IDS)
        or isinstance(target_count, bool)
        or not isinstance(target_count, int)
        or target_count < 1
        or required_cells != len(SECURITY_CONTROL_IDS) * target_count
        or coverage.get("plannedCells") != required_cells
        or coverage.get("executedCells") != required_cells
    ):
        fail(
            "security-control-coverage",
            "security assessment lacks the route-owned canonical control denominator",
            check_id,
        )
        return None
    return expected_digest


def _validate_security_recency(check_id, fail, result):
    recorded_at = result.get("recordedAt")
    age_seconds = result.get("ageSeconds")
    try:
        if not isinstance(recorded_at, str) or not recorded_at.endswith("Z"):
            raise ValueError("recordedAt must be canonical UTC")
        parsed_recorded_at = datetime.fromisoformat(
            recorded_at[:-1] + "+00:00"
        )
        measured_age = int(
            (datetime.now(timezone.utc) - parsed_recorded_at).total_seconds()
        )
    except (AttributeError, TypeError, ValueError):
        measured_age = MAX_COMPLETION_SECURITY_AGE_SECONDS + 1
    if (
        isinstance(age_seconds, bool)
        or not isinstance(age_seconds, int)
        or not 0 <= age_seconds <= MAX_COMPLETION_SECURITY_AGE_SECONDS
        or measured_age < -5
        or measured_age > MAX_COMPLETION_SECURITY_AGE_SECONDS
        or abs(measured_age - age_seconds) > 5
    ):
        fail(
            "security-assessment-stale",
            "security assessment must be a current report no older than 24 hours",
            check_id,
        )


def _security_binding_receipt(check, check_id, fail, project_root, receipt_identity, receipt_path, result, target):
    authorization = (
        result.get("authorization") if isinstance(result.get("authorization"), dict) else {}
    )
    control_coverage_sha256 = _security_control_digest(result, check_id, fail)
    external_contact = authorization.get("externalContact")
    plan_sha256 = authorization.get("planSha256")
    frozen_grant_sha256 = authorization.get("frozenGrantSha256")
    expected_grant_sha256 = check.get("expectedGrantSha256")
    if (
        not isinstance(external_contact, bool)
        or not isinstance(plan_sha256, str)
        or not SHA256_RE.fullmatch(plan_sha256)
    ):
        fail(
            "security-assessment-binding",
            "security assessment lacks a validated authorization-plan binding",
            check_id,
        )
    expected_plan_sha256 = check.get("expectedPlanSha256")
    expected_snapshot_sha256 = check.get("expectedSnapshotSha256")
    if (
        not isinstance(expected_plan_sha256, str)
        or not SHA256_RE.fullmatch(expected_plan_sha256)
        or expected_plan_sha256 != plan_sha256
        or not isinstance(expected_snapshot_sha256, str)
        or not SHA256_RE.fullmatch(expected_snapshot_sha256)
        or expected_snapshot_sha256 != target.get("snapshotSha256")
    ):
        fail(
            "security-assessment-plan",
            "security assessment must match closure-owned plan and snapshot digests",
            check_id,
        )
    if external_contact:
        if (
            not isinstance(expected_grant_sha256, str)
            or not SHA256_RE.fullmatch(expected_grant_sha256)
            or frozen_grant_sha256 != expected_grant_sha256
        ):
            fail(
                "security-assessment-grant",
                "external assessment grant does not match the closure-owned expected hash",
                check_id,
            )
    elif expected_grant_sha256 is not None or frozen_grant_sha256 is not None:
        fail(
            "security-assessment-grant",
            "local assessment must not carry an external grant binding",
            check_id,
        )
    return {
        "checkId": check_id,
        "projectRoot": project_root,
        "receiptPath": receipt_path,
        "receiptBytes": receipt_identity["bytes"],
        "receiptSha256": receipt_identity["sha256"],
        "planSha256": plan_sha256,
        "snapshotSha256": target.get("snapshotSha256"),
        "controlCoverageSha256": control_coverage_sha256,
    }


def _check_security_assessment(
    check: dict[str, Any], root: Path, check_id: str, product: str, version: str,
    fail: FailureSink, verifier: SecurityVerifier,
) -> dict[str, Any] | None:
    project_root, error = _resolve(root, check.get("projectRoot"), directory=True)
    receipt = check.get("receipt")
    if error or project_root is None:
        fail("unsafe-path", f"security assessment projectRoot: {error}", check_id)
        return
    receipt_path, receipt_error = _resolve(project_root, receipt)
    if receipt_error or receipt_path is None:
        fail("unsafe-path", f"security assessment receipt: {receipt_error}", check_id)
        return
    _receipt_document, receipt_identity = _read_json_with_identity(receipt_path)
    result = verifier(project_root, receipt)
    if file_identity(receipt_path) != receipt_identity:
        fail(
            "security-assessment-block",
            "security assessment receipt changed during verification",
            check_id,
        )
    if result.get("status") != "GREEN":
        fail(
            "security-assessment-block",
            "security assessment is invalid, partial, stale, or has open findings",
            check_id,
            result=result,
        )
        return
    if result.get("receiptSchemaVersion") != 2:
        fail(
            "security-assessment-schema",
            "completion accepts only a live-bound security receipt v2",
            check_id,
        )
        return
    _validate_security_recency(check_id, fail, result)
    target = result.get("target") if isinstance(result.get("target"), dict) else {}
    expected_identity_sha256 = _target_identity_sha256(product, version)
    if (
        target.get("identityProfile") != SECURITY_TARGET_IDENTITY_PROFILE
        or target.get("identitySha256") != expected_identity_sha256
    ):
        fail(
            "security-assessment-version-drift",
            "security assessment target differs from completion identity",
            check_id,
        )
    if (
        target.get("snapshotVerified") is not True
        or target.get("snapshotProfile") != SECURITY_SNAPSHOT_PROFILE
        or not isinstance(target.get("snapshotSha256"), str)
        or not SHA256_RE.fullmatch(target["snapshotSha256"])
    ):
        fail(
            "security-assessment-binding",
            "security assessment lacks a verified live target snapshot",
            check_id,
        )
    return _security_binding_receipt(check, check_id, fail, project_root, receipt_identity, receipt_path, result, target)


def _check_json_evidence(check: dict[str, Any], path: Path, check_id: str,
                         fail: FailureSink) -> None:
    document, identity = _read_json_with_identity(path)
    _check_observed_identity(identity, check, check_id, fail)
    assertions = check.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        fail("evidence-assertion", "json-evidence needs at least one assertion", check_id)
        return
    for assertion in assertions:
        if not isinstance(assertion, dict) or "pointer" not in assertion or "equals" not in assertion:
            fail("evidence-assertion", "assertion needs pointer and equals", check_id)
            continue
        try:
            actual = _json_pointer(document, assertion["pointer"])
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            fail("evidence-assertion", f"JSON pointer failed: {exc}", check_id, pointer=assertion.get("pointer"))
            continue
        if actual != assertion["equals"]:
            fail("evidence-assertion", "JSON evidence field did not match", check_id,
                 pointer=assertion["pointer"], expected=assertion["equals"], actual=actual)
