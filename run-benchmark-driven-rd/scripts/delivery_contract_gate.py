#!/usr/bin/env python3
"""Gate installer/package promotion on a complete delivery-evidence contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from evidence_identity import SHA256_RE, valid_identity


REQUIRED_NEGATIVE_CONTROLS = {
    "unsafe-entry",
    "duplicate-entry",
    "missing-file",
    "unexpected-file",
    "identity-mismatch",
    "stale-build-inputs",
    "stale-build-outputs",
    "missing-embedded-receipt",
    "semantic-version-drift",
}


def file_identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _resolve_live_file(root: Path, value: Any) -> tuple[Path | None, str | None]:
    if not isinstance(value, str) or not value or "\\" in value:
        return None, "path must be a non-empty root-relative POSIX string"
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
        return None, "path must remain inside the evidence root"
    candidate = (root / Path(*relative.parts)).resolve()
    if candidate != root and root not in candidate.parents:
        return None, "path resolves outside the evidence root"
    return candidate, None


Fail = Callable[..., None]


def _check_live_identity(root: Path, identity: Any, role: str, fail: Fail) -> None:
    if not valid_identity(identity):
        fail("invalid-live-identity", f"{role} needs path, bytes and SHA-256", role=role)
        return
    candidate, error = _resolve_live_file(root, identity.get("path"))
    if error or candidate is None:
        fail("unsafe-live-path", f"{role}: {error}", role=role)
    elif not candidate.is_file() or candidate.is_symlink():
        fail("missing-live-file", f"{role} is missing or not a regular file", role=role, path=identity.get("path"))
    elif file_identity(candidate) != {"bytes": identity["bytes"], "sha256": identity["sha256"]}:
        fail("stale-live-identity", f"{role} no longer matches live bytes", role=role, path=identity.get("path"))


def _validate_header(document: dict[str, Any], root: Path, fail: Fail) -> None:
    if document.get("schemaVersion") != 1:
        fail("schema-version", "schemaVersion must be 1")
    for field in ("artifactKind", "product", "productVersion"):
        if not isinstance(document.get(field), str) or not document[field].strip():
            fail("missing-identity", f"{field} must be a non-empty string", field=field)

    evaluator = document.get("evaluator") if isinstance(document.get("evaluator"), dict) else {}
    if not isinstance(evaluator.get("name"), str) or not evaluator["name"].strip():
        fail("evaluator-name", "evaluator.name is required")
    if not isinstance(evaluator.get("sha256"), str) or not SHA256_RE.fullmatch(evaluator["sha256"]):
        fail("evaluator-identity", "evaluator.sha256 must be lowercase SHA-256")
    if evaluator.get("selfTestPassed") is not True:
        fail("evaluator-self-test", "product evaluator self-test must pass")
    if evaluator.get("taskFixturePassed") is not True:
        fail("evaluator-task-fixture", "task-shaped positive/negative fixture must pass")
    _check_live_identity(root, evaluator.get("report"), "evaluator.report", fail)


def _validate_artifacts(document: dict[str, Any], root: Path, fail: Fail) -> None:
    for role in ("deliveryEnvelope", "buildArtifact"):
        _check_live_identity(root, document.get(role), role, fail)

    envelope = document.get("deliveryEnvelope") if isinstance(document.get("deliveryEnvelope"), dict) else {}
    if envelope.get("inspected") is not True:
        fail("envelope-not-inspected", "the actual delivery envelope must be inspected")

    build_artifact = document.get("buildArtifact") if isinstance(document.get("buildArtifact"), dict) else {}
    delivered = document.get("deliveredArtifact") if isinstance(document.get("deliveredArtifact"), dict) else {}
    if build_artifact.get("authority") is not False:
        fail("build-artifact-authority", "build-directory artifact must be explicitly non-authoritative")
    if delivered.get("authority") is not True:
        fail("delivered-artifact-authority", "the artifact extracted from the delivery envelope must be authoritative")
    if delivered.get("source") != "delivery-envelope-extraction":
        fail("delivered-artifact-source", "delivered artifact must come from delivery-envelope extraction")
    if not valid_identity(delivered):
        fail("delivered-artifact-identity", "deliveredArtifact needs bytes and SHA-256 from extraction")
    delivered_identity = delivered.get("identity") if isinstance(delivered.get("identity"), dict) else {}
    for field in ("architecture", "productName", "productVersion"):
        if not isinstance(delivered_identity.get(field), str) or not delivered_identity[field].strip():
            fail("delivered-product-identity", f"deliveredArtifact.identity.{field} is required", field=field)
    if delivered_identity.get("productName") != document.get("product") or delivered_identity.get("productVersion") != document.get("productVersion"):
        fail("delivered-product-drift", "delivered product name/version must match the contract")


def _validate_payload_and_receipt(document: dict[str, Any], fail: Fail) -> None:
    payload = document.get("payload") if isinstance(document.get("payload"), dict) else {}
    if not isinstance(payload.get("entryCount"), int) or payload["entryCount"] <= 0:
        fail("payload-empty", "payload.entryCount must be positive")
    if payload.get("unsafeEntryCount") != 0:
        fail("unsafe-payload", "payload contains unsafe archive entries")
    if payload.get("duplicateEntryCount") != 0:
        fail("duplicate-payload", "payload contains case-insensitive duplicate entries")
    closed = payload.get("closedWorld") if isinstance(payload.get("closedWorld"), dict) else {}
    for field in ("missingCount", "unexpectedCount", "identityMismatchCount"):
        if closed.get(field) != 0:
            fail("payload-not-closed-world", f"payload.closedWorld.{field} must be zero", field=field, value=closed.get(field))
    if not isinstance(closed.get("expectedCount"), int) or not isinstance(closed.get("actualCount"), int) or closed.get("expectedCount") <= 0 or closed.get("expectedCount") != closed.get("actualCount"):
        fail("payload-count-drift", "closed-world expected and actual counts must be equal and positive")

    receipt = document.get("buildReceipt") if isinstance(document.get("buildReceipt"), dict) else {}
    for field in ("currentInputs", "currentOutputs", "rawBytesEmbedded", "runtimeSemanticReadback"):
        if receipt.get(field) is not True:
            fail("build-receipt-incomplete", f"buildReceipt.{field} must be true", field=field)
    modes = receipt.get("identityModes") if isinstance(receipt.get("identityModes"), dict) else {}
    if modes.get("embedding") != "raw-bytes" or modes.get("runtime") != "semantic-fields":
        fail("identity-mode-conflation", "embedding must use raw bytes while runtime readback uses semantic fields")


def _validate_promotion_controls(document: dict[str, Any], fail: Fail) -> None:
    canonical = document.get("canonicalBuild") if isinstance(document.get("canonicalBuild"), dict) else {}
    if canonical.get("nativeOutputsRebuilt") is not True:
        fail("native-output-not-rebuilt", "canonical build must rebuild and promote native outputs")
    if canonical.get("deliveryGateAutomatic") is not True:
        fail("manual-delivery-gate", "canonical build must automatically run the delivery gate")

    metadata = document.get("distributionMetadata") if isinstance(document.get("distributionMetadata"), dict) else {}
    if metadata.get("sbomEmbedded") is not True or metadata.get("noticesEmbedded") is not True:
        fail("distribution-metadata-not-embedded", "SBOM and third-party notices must be in the actual payload")

    journey = document.get("runtimeJourney") if isinstance(document.get("runtimeJourney"), dict) else {}
    for field in ("deliveredPayloadExecutedOrLoaded", "receiptReadback", "semanticFieldsMatch"):
        if journey.get(field) is not True:
            fail("runtime-journey-incomplete", f"runtimeJourney.{field} must be true", field=field)

    controls = document.get("negativeControls")
    if not isinstance(controls, list) or any(not isinstance(item, str) or not item for item in controls):
        fail("negative-controls", "negativeControls must be a string array")
        controls = []
    if len(set(controls)) != len(controls):
        fail("duplicate-negative-control", "negativeControls contains duplicates")
    missing_controls = sorted(REQUIRED_NEGATIVE_CONTROLS - set(controls))
    if missing_controls:
        fail("missing-negative-control", "required delivery failure classes are uncalibrated", missing=missing_controls)

    archives = document.get("deterministicArchives", [])
    if not isinstance(archives, list):
        fail("deterministic-archives", "deterministicArchives must be an array")
    else:
        for index, archive in enumerate(archives):
            if not isinstance(archive, dict) or archive.get("twoBuildByteIdentical") is not True:
                fail("archive-not-deterministic", "declared archive must be generated twice with exact byte identity", index=index)


def evaluate(document: dict[str, Any], root: Path) -> dict[str, Any]:
    root = root.resolve()
    findings: list[dict[str, Any]] = []

    def fail(code: str, message: str, **details: Any) -> None:
        findings.append({"status": "FAIL", "code": code, "message": message, **details})

    _validate_header(document, root, fail)
    _validate_artifacts(document, root, fail)
    _validate_payload_and_receipt(document, fail)
    _validate_promotion_controls(document, fail)
    return {
        "schemaVersion": 1,
        "status": "BLOCK" if findings else "GREEN",
        "product": document.get("product"),
        "productVersion": document.get("productVersion"),
        "artifactKind": document.get("artifactKind"),
        "findings": findings or [{
            "status": "PASS",
            "code": "delivery-contract-closed",
            "message": "actual delivery envelope, payload, receipt and runtime journey evidence are closed",
        }],
    }


def fixture_document(root: Path) -> dict[str, Any]:
    report = root / "evidence/report.json"
    envelope = root / "dist/setup.exe"
    build = root / "build/app.exe"
    report.parent.mkdir(parents=True, exist_ok=True)
    envelope.parent.mkdir(parents=True, exist_ok=True)
    build.parent.mkdir(parents=True, exist_ok=True)
    report.write_text('{"status":"GREEN"}', encoding="utf-8")
    envelope.write_bytes(b"installer-envelope")
    build.write_bytes(b"build-executable")
    return {
        "schemaVersion": 1,
        "artifactKind": "installer",
        "product": "Fixture",
        "productVersion": "1.2.3",
        "evaluator": {
            "name": "fixture-delivery-evaluator",
            "sha256": "a" * 64,
            "selfTestPassed": True,
            "taskFixturePassed": True,
            "report": {"path": "evidence/report.json", **file_identity(report)},
        },
        "deliveryEnvelope": {"path": "dist/setup.exe", **file_identity(envelope), "inspected": True},
        "buildArtifact": {"path": "build/app.exe", **file_identity(build), "authority": False},
        "deliveredArtifact": {
            "path": "setup.exe!/app.exe",
            "bytes": 123,
            "sha256": "b" * 64,
            "authority": True,
            "source": "delivery-envelope-extraction",
            "identity": {"architecture": "x64", "productName": "Fixture", "productVersion": "1.2.3"},
        },
        "payload": {
            "entryCount": 10,
            "unsafeEntryCount": 0,
            "duplicateEntryCount": 0,
            "closedWorld": {"expectedCount": 10, "actualCount": 10, "missingCount": 0, "unexpectedCount": 0, "identityMismatchCount": 0},
        },
        "buildReceipt": {
            "currentInputs": True,
            "currentOutputs": True,
            "rawBytesEmbedded": True,
            "runtimeSemanticReadback": True,
            "identityModes": {"embedding": "raw-bytes", "runtime": "semantic-fields"},
        },
        "canonicalBuild": {"nativeOutputsRebuilt": True, "deliveryGateAutomatic": True},
        "distributionMetadata": {"sbomEmbedded": True, "noticesEmbedded": True},
        "runtimeJourney": {"deliveredPayloadExecutedOrLoaded": True, "receiptReadback": True, "semanticFieldsMatch": True},
        "negativeControls": sorted(REQUIRED_NEGATIVE_CONTROLS),
        "deterministicArchives": [{"path": "creator-pack.zip", "twoBuildByteIdentical": True}],
    }


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="rd-delivery-contract-") as raw:
        root = Path(raw)
        valid = fixture_document(root)
        assert evaluate(valid, root)["status"] == "GREEN"
        assert valid["buildArtifact"]["sha256"] != valid["deliveredArtifact"]["sha256"]

        missing_control = json.loads(json.dumps(valid))
        missing_control["negativeControls"].remove("unsafe-entry")
        assert any(item["code"] == "missing-negative-control" for item in evaluate(missing_control, root)["findings"])

        stale = json.loads(json.dumps(valid))
        (root / "dist/setup.exe").write_bytes(b"changed-envelope")
        assert any(item["code"] == "stale-live-identity" for item in evaluate(stale, root)["findings"])
        (root / "dist/setup.exe").write_bytes(b"installer-envelope")

        conflated = json.loads(json.dumps(valid))
        conflated["buildReceipt"]["identityModes"]["runtime"] = "raw-bytes"
        assert any(item["code"] == "identity-mode-conflation" for item in evaluate(conflated, root)["findings"])

        manual = json.loads(json.dumps(valid))
        manual["canonicalBuild"]["deliveryGateAutomatic"] = False
        assert any(item["code"] == "manual-delivery-gate" for item in evaluate(manual, root)["findings"])

        reordered = json.loads(json.dumps(valid, sort_keys=True))
        assert evaluate(reordered, root)["status"] == "GREEN"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?")
    parser.add_argument("--root")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        print("delivery contract gate self-test passed")
        return 0
    if not args.manifest:
        parser.error("manifest is required unless --self-test is used")
    manifest = Path(args.manifest).resolve()
    root = Path(args.root).resolve() if args.root else manifest.parent
    report = evaluate(json.loads(manifest.read_text(encoding="utf-8")), root)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
