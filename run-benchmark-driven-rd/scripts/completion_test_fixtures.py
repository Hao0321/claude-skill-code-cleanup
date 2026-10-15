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


def fixture_document(root: Path) -> dict[str, Any]:
    files = {
        "cleanup": root / "evidence/cleanup.json",
        "delivery": root / "evidence/delivery.json",
        "ledger": root / "product/capabilities.json",
        "package": root / "product/package.json",
        "artifact": root / "product/dist/setup.exe",
        "evidence": root / "evidence/performance.json",
        "receipt": root / "product/receipt.json",
        "route": root / "evidence/route.json",
    }
    for path in files.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    files["cleanup"].write_text(json.dumps({
        "phase": "promotion", "decision": "ALLOW", "review_policy": "block",
        "report": {
            "target": str(root / "product"),
            "summary": {"fail": 0, "review": 0},
        },
    }), encoding="utf-8")
    files["ledger"].write_text(json.dumps({
        "schemaVersion": 1,
        "product": "Fixture",
        "productVersion": "1.0.0",
        "requiredObligationIds": ["update.client-check", "update.release-channel"],
    }), encoding="utf-8")
    files["package"].write_text(json.dumps({
        "productName": "Fixture",
        "version": "1.0.0",
        "scripts": {
            "check:update": "true",
            "verify:release": "true",
        },
    }), encoding="utf-8")
    files["artifact"].write_bytes(b"installer")
    artifact_identity = file_identity(files["artifact"])
    files["delivery"].write_text(json.dumps({
        "deliveryEnvelope": {"path": "dist/setup.exe", **artifact_identity},
    }), encoding="utf-8")
    files["evidence"].write_text('{"status":"GREEN"}', encoding="utf-8")
    files["receipt"].write_text(json.dumps({
        "outputs": [{"path": "dist/setup.exe", **artifact_identity}],
    }), encoding="utf-8")
    route = compose_route(
        root / "product",
        task_intent="completion",
        stage="completion",
        artifact="source",
        risk="standard",
        context_budget_tokens=50_000,
    )
    files["route"].write_text(json.dumps(route), encoding="utf-8")
    return {
        "schemaVersion": 2,
        "product": "Fixture",
        "productVersion": "1.0.0",
        "scope": "internal",
        "requiredCheckIds": [
            "cleanup", "delivery", "capabilities", "receipt", "artifact",
            "performance", "route",
        ],
        "negativeControls": sorted(REQUIRED_NEGATIVE_CONTROLS),
        "checks": [
            {"id": "cleanup", "kind": "cleanup-promotion", "path": "evidence/cleanup.json", "projectRoot": "product"},
            {"id": "delivery", "kind": "delivery-contract", "path": "evidence/delivery.json", "projectRoot": "product"},
            {"id": "capabilities", "kind": "capability-ledger", "path": "product/capabilities.json", "packageJson": "product/package.json", "requiredObligationIds": ["update.client-check", "update.release-channel"]},
            {"id": "receipt", "kind": "build-receipt", "projectRoot": "product", "receipt": "receipt.json"},
            {"id": "artifact", "kind": "file-identity", "path": "product/dist/setup.exe", "projectRoot": "product", "role": "release-artifact", **artifact_identity},
            {"id": "performance", "kind": "json-evidence", "path": "evidence/performance.json", **file_identity(files["evidence"]), "assertions": [{"pointer": "/status", "equals": "GREEN"}]},
            {"id": "route", "kind": "route-receipt", "path": "evidence/route.json", "projectRoot": "product", **file_identity(files["route"])},
        ],
    }


def _security_fixture_report(
    *,
    receipt_schema_version: int = 2,
    age_seconds: int = 0,
    product: str = "Fixture",
    version: str = "1.0.0",
    external_contact: bool = False,
    frozen_grant_sha256: str | None = None,
) -> dict[str, Any]:
    recorded_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return {
        "status": "GREEN",
        "receiptSchemaVersion": receipt_schema_version,
        "recordedAt": recorded_at.isoformat().replace("+00:00", "Z"),
        "ageSeconds": age_seconds,
        "target": {
            "identityProfile": SECURITY_TARGET_IDENTITY_PROFILE,
            "identitySha256": _target_identity_sha256(product, version),
            "snapshotSha256": "a" * 64,
            "snapshotProfile": SECURITY_SNAPSHOT_PROFILE,
            "snapshotVerified": True,
        },
        "authorization": {
            "externalContact": external_contact,
            "planSha256": "b" * 64,
            "frozenGrantSha256": frozen_grant_sha256,
        },
        "controlCoverage": {
            "profile": SECURITY_CONTROL_PROFILE,
            "requiredControlIdsSha256": sha256_json(list(SECURITY_CONTROL_IDS)),
            "requiredControls": len(SECURITY_CONTROL_IDS),
            "targetCount": 1,
            "requiredCells": len(SECURITY_CONTROL_IDS),
            "plannedCells": len(SECURITY_CONTROL_IDS),
            "executedCells": len(SECURITY_CONTROL_IDS),
        },
    }
