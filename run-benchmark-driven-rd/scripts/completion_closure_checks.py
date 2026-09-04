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


def _validate_header(
    document: dict[str, Any], fail: FailureSink,
) -> tuple[str, str, str, str | None]:
    schema_version = document.get("schemaVersion")
    if schema_version == 1:
        fail(
            "legacy-unbound-completion-contract",
            "completion contract v1 has no current route binding and cannot close",
            None,
        )
    elif schema_version != 2:
        fail("schema-version", "schemaVersion must be 2", None)
    product = document.get("product")
    version = document.get("productVersion")
    scope = document.get("scope")
    product_valid = _valid_target_identity(
        product,
        max_chars=TARGET_PRODUCT_MAX_CHARS,
        max_utf8_bytes=TARGET_PRODUCT_MAX_UTF8_BYTES,
    )
    version_valid = _valid_target_identity(
        version,
        max_chars=TARGET_VERSION_MAX_CHARS,
        max_utf8_bytes=TARGET_VERSION_MAX_UTF8_BYTES,
    )
    if not product_valid:
        fail("target-identity", "product must be a bounded NFC identity", None)
        product = ""
    if not version_valid:
        fail("target-identity", "productVersion must be a bounded NFC identity", None)
        version = ""
    if scope not in SCOPES:
        fail("invalid-scope", "scope must be internal, public or parity", None)
        scope = "internal"
    controls = document.get("negativeControls")
    if not isinstance(controls, list) or any(not isinstance(item, str) or not item for item in controls):
        fail("negative-controls", "negativeControls must be a non-empty string array", None)
        controls = []
    if len(set(controls)) != len(controls):
        fail("duplicate-negative-control", "negativeControls contains duplicates", None)
    missing = sorted(REQUIRED_NEGATIVE_CONTROLS - set(controls))
    if missing:
        fail("missing-negative-control", "completion failure classes are uncalibrated", None, missing=missing)
    identity_sha256 = (
        _target_identity_sha256(product, version)
        if product_valid and version_valid
        else None
    )
    return product, version, scope, identity_sha256


def _declared_checks(document: dict[str, Any], fail: FailureSink) -> tuple[list[str], list[Any]]:
    required = document.get("requiredCheckIds")
    checks = document.get("checks")
    if not isinstance(required, list) or not required or any(not isinstance(item, str) or not item for item in required):
        fail("required-check-list", "requiredCheckIds must be a non-empty string array", None)
        required = []
    elif len({item.casefold() for item in required}) != len(required):
        fail("duplicate-required-check", "requiredCheckIds contains case-insensitive duplicates", None)
    if not isinstance(checks, list):
        fail("checks", "checks must be an array", None)
        checks = []
    return required, checks


def _run_checks(
    checks: list[Any], root: Path, product: str, version: str, scope: str,
    fail: FailureSink, cleanup_verifier: CleanupVerifier,
    delivery_evaluator: DeliveryEvaluator, capability_evaluator: CapabilityEvaluator,
    receipt_verifier: ReceiptVerifier, security_verifier: SecurityVerifier,
) -> tuple[
    list[str], set[str], list[dict[str, Any]], list[dict[str, Any]],
    list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]],
]:
    checked: list[str] = []
    seen: set[str] = set()
    path_roles: set[str] = set()
    valid_checks: list[dict[str, Any]] = []
    route_receipts: list[dict[str, Any]] = []
    capability_receipts: list[dict[str, Any]] = []
    security_receipts: list[dict[str, Any]] = []
    subject_receipts: list[dict[str, Any]] = []

    for raw in checks:
        if not isinstance(raw, dict):
            fail("invalid-check", "check must be an object", None)
            continue
        check_id = raw.get("id")
        kind = raw.get("kind")
        if not isinstance(check_id, str) or not check_id:
            fail("missing-check-id", "check id is required", None)
            continue
        normalized_id = check_id.casefold()
        if normalized_id in seen:
            fail("duplicate-check-id", "check IDs must be case-insensitively unique", check_id)
            continue
        seen.add(normalized_id)
        if kind not in CHECK_KINDS:
            fail("invalid-check-kind", f"unsupported check kind: {kind}", check_id)
            continue
        checked.append(check_id)
        valid_checks.append(raw)

        if kind == "build-receipt":
            try:
                subject = _check_receipt(raw, root, check_id, fail, receipt_verifier)
                if subject is not None:
                    subject_receipts.append(subject)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError, KeyError, RecursionError) as exc:
                fail("measurement-error", str(exc), check_id)
            continue
        if kind == "security-assessment":
            try:
                security_receipt = _check_security_assessment(
                    raw, root, check_id, product, version, fail, security_verifier
                )
                if security_receipt is not None:
                    security_receipts.append(security_receipt)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError, KeyError, RecursionError) as exc:
                fail("measurement-error", str(exc), check_id)
            continue
        path, error = _resolve(root, raw.get("path"))
        if error or path is None:
            fail("unsafe-path", f"{kind}: {error}", check_id)
            continue
        path_key = str(path).casefold()
        if path_key in path_roles:
            fail("duplicate-check-path", "one file cannot satisfy multiple closure checks", check_id)
        path_roles.add(path_key)
        try:
            if kind == "cleanup-promotion":
                subject = _check_cleanup(
                    raw, path, root, check_id, fail, cleanup_verifier
                )
                if subject is not None:
                    subject_receipts.append(subject)
            elif kind == "delivery-contract":
                subject = _check_delivery(
                    raw, path, root, check_id, product, version, fail,
                    delivery_evaluator,
                )
                if subject is not None:
                    subject_receipts.append(subject)
            elif kind == "capability-ledger":
                capability_receipt = _check_capabilities(
                    raw, path, root, check_id, scope, product, version, fail,
                    capability_evaluator,
                )
                if capability_receipt is not None:
                    capability_receipts.append(capability_receipt)
            elif kind == "file-identity":
                subject = _check_identity(path, raw, root, check_id, fail)
                if subject is not None:
                    subject_receipts.append(subject)
            elif kind == "json-evidence":
                _check_json_evidence(raw, path, check_id, fail)
            elif kind == "route-receipt":
                route_receipt = _check_route_receipt(raw, path, root, check_id, fail)
                if route_receipt is not None:
                    route_receipts.append(route_receipt)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, KeyError, RecursionError) as exc:
            fail("measurement-error", str(exc), check_id)
    return (
        checked, seen, valid_checks, route_receipts,
        capability_receipts, security_receipts, subject_receipts,
    )


def _check_public_evidence_floor(
    checks: list[dict[str, Any]],
    route_receipt: dict[str, Any],
    subject_receipts: list[dict[str, Any]],
    fail: FailureSink,
) -> None:
    counts = {
        kind: sum(check.get("kind") == kind for check in checks)
        for kind in PUBLIC_EXACTLY_ONE_CHECK_KINDS | PUBLIC_AT_LEAST_ONE_CHECK_KINDS
    }
    if any(counts[kind] != 1 for kind in PUBLIC_EXACTLY_ONE_CHECK_KINDS) or any(
        counts[kind] < 1 for kind in PUBLIC_AT_LEAST_ONE_CHECK_KINDS
    ):
        fail(
            "public-check-kind-floor",
            "public or parity completion lacks its mandatory independent evidence kinds",
            None,
        )
    route_root = route_receipt["projectRoot"]
    subjects = {
        kind: [
            item for item in subject_receipts
            if item.get("kind") == kind and item.get("projectRoot") == route_root
        ]
        for kind in ("cleanup-promotion", "delivery-contract", "build-receipt")
    }
    if any(len(records) != 1 for records in subjects.values()):
        fail(
            "public-check-subject",
            "public evidence kinds must belong exactly once to the routed project",
            None,
        )
    release_artifacts = [
        item for item in subject_receipts
        if item.get("kind") == "file-identity"
        and item.get("projectRoot") == route_root
        and item.get("role") == "release-artifact"
    ]
    if len(release_artifacts) != 1:
        fail(
            "public-artifact-binding",
            "public completion needs exactly one routed release-artifact identity",
            None,
        )
    if (
        len(release_artifacts) == 1
        and len(subjects["delivery-contract"]) == 1
        and len(subjects["build-receipt"]) == 1
    ):
        release_identity = release_artifacts[0]["identity"]
        output_key = (release_identity["bytes"], release_identity["sha256"])
        if (
            release_identity != subjects["delivery-contract"][0].get("identity")
            or output_key not in subjects["build-receipt"][0]["outputIdentities"]
        ):
            fail(
                "public-artifact-binding",
                "release artifact must equal the delivered envelope and a verified build output",
                None,
            )


def _check_route_floor(
    required: list[str], checks: list[dict[str, Any]],
    route_receipts: list[dict[str, Any]], capability_receipts: list[dict[str, Any]],
    security_receipts: list[dict[str, Any]], root: Path, scope: str,
    fail: FailureSink, subject_receipts: list[dict[str, Any]],
) -> None:
    route_checks = [check for check in checks if check.get("kind") == "route-receipt"]
    if len(route_checks) != 1 or len(route_receipts) != 1:
        fail(
            "route-receipt-required",
            "completion requires exactly one valid current route-receipt check",
            None,
            observed=len(route_checks),
        )
        return
    route_check_id = route_receipts[0]["checkId"]
    if route_check_id.casefold() not in {item.casefold() for item in required}:
        fail("route-receipt-required", "route receipt must be a required closure check", route_check_id)

    expected_floor = route_receipts[0]["requiredCapabilityObligationIds"]
    capability_checks = [check for check in checks if check.get("kind") == "capability-ledger"]
    holders: list[str] = []
    for check in capability_checks:
        floor = check.get("requiredObligationIds")
        if isinstance(floor, list) and all(isinstance(item, str) for item in floor):
            folded = [item.casefold() for item in floor]
            has_case_drift = len(folded) != len(set(folded)) or any(
                item.casefold() in {expected.casefold() for expected in expected_floor}
                and item not in expected_floor
                for item in floor
            )
            if not has_case_drift and set(expected_floor).issubset(set(floor)):
                holders.append(str(check.get("id")))
    if len(holders) != 1:
        fail(
            "route-capability-floor",
            "exactly one capability ledger must contain the complete current route floor",
            None,
            expected=expected_floor,
            holders=holders,
        )
    holder_receipt = next((
        item for item in capability_receipts
        if len(holders) == 1 and item.get("checkId") == holders[0]
    ), None)
    if (
        len(holders) == 1
        and (
            not isinstance(holder_receipt, dict)
            or holder_receipt.get("projectRoot") != route_receipts[0]["projectRoot"]
        )
    ):
        fail(
            "route-capability-floor",
            "route capability ledger must belong to the routed project root",
            None,
        )

    security_check_records = [
        check for check in checks if check.get("kind") == "security-assessment"
    ]
    security_checks = len(security_check_records)
    update_required = route_receipts[0]["updateRequired"]
    security_required = route_receipts[0]["securityRequired"]
    if scope in {"public", "parity"}:
        _check_public_evidence_floor(
            checks, route_receipts[0], subject_receipts, fail
        )
    if scope in {"public", "parity"} and not (update_required and security_required):
        fail(
            "public-route-floor",
            "public or parity completion requires a distributable update-and-security route",
            route_check_id,
            updateRequired=update_required,
            securityRequired=security_required,
        )
    if security_required and security_checks != 1:
        fail(
            "security-assessment-floor",
            "current route requires exactly one live security-assessment check",
            None,
            observed=security_checks,
        )
    if security_required and security_checks == 1:
        security_root, security_root_error = _resolve(
            root, security_check_records[0].get("projectRoot"), directory=True
        )
        if (
            security_root_error
            or security_root is None
            or security_root != route_receipts[0]["projectRoot"]
        ):
            fail(
                "security-assessment-subject",
                "security assessment subject must equal the routed project root",
                None,
            )
    if security_required:
        security_receipt = security_receipts[0] if len(security_receipts) == 1 else None
        bindings = (
            holder_receipt.get("securityBindings")
            if isinstance(holder_receipt, dict)
            and isinstance(holder_receipt.get("securityBindings"), dict)
            else {}
        )
        if security_receipt is None or set(bindings) != SECURITY_CAPABILITY_IDS:
            fail(
                "security-capability-binding",
                "security capability floor lacks one validated assessment binding",
                None,
            )
        elif (
            security_receipt.get("controlCoverageSha256")
            != route_receipts[0]["requiredSecurityControlIdsSha256"]
        ):
            fail(
                "security-control-coverage",
                "security receipt control coverage differs from the current route",
                None,
            )
        else:
            expected_binding = {
                "receiptPath": security_receipt["receiptPath"],
                "receiptBytes": security_receipt["receiptBytes"],
                "receiptSha256": security_receipt["receiptSha256"],
                "planSha256": security_receipt["planSha256"],
                "snapshotSha256": security_receipt["snapshotSha256"],
                "routingInputSha256": route_receipts[0]["routingInputSha256"],
                "controlCoverageSha256": security_receipt["controlCoverageSha256"],
            }
            for capability_id in SECURITY_CAPABILITY_IDS:
                binding = bindings[capability_id]
                if any(
                    binding.get(field) != expected
                    for field, expected in expected_binding.items()
                ):
                    fail(
                        "security-capability-binding",
                        "security capability binding differs from route or assessment",
                        None,
                    )
                    break
    if not security_required and security_checks:
        fail(
            "security-assessment-floor",
            "current route excludes a security-assessment check",
            None,
            observed=security_checks,
        )


def evaluate(
    document: dict[str, Any], root: Path, *,
    cleanup_verifier: CleanupVerifier = verify_cleanup,
    delivery_evaluator: DeliveryEvaluator = evaluate_delivery,
    capability_evaluator: CapabilityEvaluator = evaluate_capabilities,
    receipt_verifier: ReceiptVerifier = default_receipt_verifier,
    security_verifier: SecurityVerifier = default_security_verifier,
) -> dict[str, Any]:
    root = _lexical_absolute(root)
    findings: list[dict[str, Any]] = []

    def fail(code: str, message: str, check_id: str | None, **details: Any) -> None:
        del message, check_id, details
        findings.append({
            "status": "FAIL",
            "code": code if re.fullmatch(r"[a-z0-9-]{1,80}", code) else "validation-error",
            "message": "completion closure validation failed",
        })

    if not isinstance(document, dict):
        fail("invalid-json-model", "completion contract JSON root must be an object", None)
        document = {}
    else:
        try:
            _validate_json_model(document)
        except ValueError as exc:
            fail("invalid-json-model", str(exc), None)
    root_error = _path_chain_error(root, directory=True)
    if root_error:
        fail("unsafe-path", f"closure root: {root_error}", None)

    product, version, scope, identity_sha256 = _validate_header(document, fail)
    required, checks = _declared_checks(document, fail)
    (
        checked, seen, valid_checks, route_receipts,
        capability_receipts, security_receipts, subject_receipts,
    ) = _run_checks(
        checks, root, product, version, scope, fail, cleanup_verifier,
        delivery_evaluator, capability_evaluator, receipt_verifier,
        security_verifier,
    )
    _check_route_floor(
        required, valid_checks, route_receipts, capability_receipts,
        security_receipts, root, scope, fail, subject_receipts,
    )

    required_keys = {item.casefold() for item in required}
    missing_checks = sorted(item for item in required if item.casefold() not in seen)
    unexpected = sorted(item for item in checked if item.casefold() not in required_keys)
    if missing_checks:
        fail("missing-required-check", "required closure checks are missing", None, missing=missing_checks)
    if unexpected:
        fail("unexpected-check", "checks contains undeclared IDs", None, unexpected=unexpected)
    return {
        "schemaVersion": 1,
        "status": "BLOCK" if findings else "GREEN",
        "targetIdentity": {
            "profile": SECURITY_TARGET_IDENTITY_PROFILE if identity_sha256 else None,
            "sha256": identity_sha256,
        },
        "scope": scope,
        "checked": {
            "count": len(checked),
            "idsSha256": sha256_json(checked),
        },
        "findings": findings or [{
            "status": "PASS",
            "code": "completion-closure",
            "message": "all declared live completion checks are fresh and closed",
        }],
    }


__all__ = [
    '_check_cleanup',
    '_check_delivery',
    '_security_ledger_bindings',
    '_check_capabilities',
    '_check_receipt',
    '_security_control_digest',
    '_check_security_assessment',
    '_check_json_evidence',
    '_validate_header',
    '_declared_checks',
    '_run_checks',
    '_check_public_evidence_floor',
    '_check_route_floor',
    'evaluate'
]
