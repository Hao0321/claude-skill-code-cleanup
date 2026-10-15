"""completion route floor responsibilities."""
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
from completion_closure_common import *
from completion_closure_route import *
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

def _route_capability_holder(capability_receipts, checks, fail, route_receipts):
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
    return holder_receipt

def _validate_security_capability_bindings(fail, holder_receipt, route_receipts, security_receipts, security_required):
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
