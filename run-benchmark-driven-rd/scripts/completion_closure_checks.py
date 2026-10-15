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
from completion_receipt_checks import (
    _check_cleanup,
    _check_delivery,
    _security_ledger_bindings,
    _check_capabilities,
    _check_receipt,
    _security_control_digest,
    _check_security_assessment,
    _check_json_evidence,
)

from completion_route_floor import (
    _check_public_evidence_floor,
    _route_capability_holder,
    _validate_security_capability_bindings,
)

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


def _dispatch_file_check(capability_evaluator, capability_receipts, check_id, cleanup_verifier, delivery_evaluator, fail, kind, path, product, raw, root, route_receipts, scope, subject_receipts, version):
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
        _dispatch_file_check(capability_evaluator, capability_receipts, check_id, cleanup_verifier, delivery_evaluator, fail, kind, path, product, raw, root, route_receipts, scope, subject_receipts, version)
    return (
        checked, seen, valid_checks, route_receipts,
        capability_receipts, security_receipts, subject_receipts,
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

    holder_receipt = _route_capability_holder(capability_receipts, checks, fail, route_receipts)
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
    _validate_security_capability_bindings(fail, holder_receipt, route_receipts, security_receipts, security_required)
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
