#!/usr/bin/env python3
"""Re-audit a target and prove a saved Cleanup promotion envelope is still fresh."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cleanup_gate_paths import relative_output_path, report_contains_path
from run_cleanup_gate import (
    CONTRACT_VERSION,
    MeasurementError,
    adapter_sha256,
    capture_skill_revision,
    resolve_active_cleanup_root,
    run_provider,
    run_snapshot_checker,
    validate_skill_revision_snapshot,
)


def validate_envelope(envelope: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(envelope, dict):
        return ["evidence root must be an object"]
    if envelope.get("contract_version") != CONTRACT_VERSION:
        errors.append(
            f"contract version mismatch: expected {CONTRACT_VERSION}, got {envelope.get('contract_version')!r}"
        )
    if not isinstance(envelope.get("report"), dict):
        errors.append("evidence.report must be an object")
    provider = envelope.get("provider")
    if not isinstance(provider, dict) or not provider.get("root"):
        errors.append("evidence.provider.root is required")
    elif not isinstance(provider.get("revision"), dict):
        errors.append("evidence.provider.revision is required")
    else:
        try:
            validate_skill_revision_snapshot(provider["revision"])
        except MeasurementError as exc:
            errors.append(f"evidence.provider.revision is invalid: {exc}")
    adapter = envelope.get("adapter")
    if not isinstance(adapter, dict) or not adapter.get("sha256"):
        errors.append("evidence.adapter.sha256 is required")
    elif not isinstance(adapter.get("revision"), dict):
        errors.append("evidence.adapter.revision is required")
    else:
        try:
            validate_skill_revision_snapshot(adapter["revision"])
        except MeasurementError as exc:
            errors.append(f"evidence.adapter.revision is invalid: {exc}")
    snapshot = envelope.get("snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("algorithm") != "cleanup-inventory-sha256-v1":
        errors.append("evidence.snapshot uses an unsupported contract")
    return errors


def verify(evidence_path: Path) -> dict[str, Any]:
    try:
        envelope = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"schemaVersion": 1, "status": "MEASUREMENT_BLOCK", "errors": [str(exc)]}
    errors = validate_envelope(envelope)
    if errors:
        return {"schemaVersion": 1, "status": "MEASUREMENT_BLOCK", "errors": errors}
    report = envelope["report"]
    target = Path(report["target"]).resolve()
    provider_root = Path(envelope["provider"]["root"]).resolve()
    config = Path(report["config"]).resolve() if report.get("config") else None
    try:
        provider_root = resolve_active_cleanup_root(provider_root)
        current, evaluator_hash, config_hash, provider_revision = run_provider(
            provider_root, target, report["mode"], config
        )
        measurement_errors: list[str] = []
        if evaluator_hash != envelope["provider"].get("evaluator_sha256"):
            measurement_errors.append("Cleanup evaluator changed; recapture the baseline and promotion")
        if config_hash != envelope["provider"].get("config_sha256"):
            measurement_errors.append("Cleanup config changed; recapture the baseline and promotion")
        if provider_revision != envelope["provider"].get("revision"):
            measurement_errors.append("Cleanup Skill revision changed; re-read the latest Skill and recapture")
        if adapter_sha256() != envelope["adapter"].get("sha256"):
            measurement_errors.append("R&D Cleanup adapter changed; recapture the promotion")
        rd_root = Path(__file__).resolve().parents[1]
        adapter_revision = capture_skill_revision(provider_root, rd_root)
        if adapter_revision != envelope["adapter"].get("revision"):
            measurement_errors.append("R&D Skill revision changed; re-read the latest Skill and recapture")
        relative = relative_output_path(evidence_path, target)
        if relative and report_contains_path(current, relative):
            measurement_errors.append("evidence envelope is part of the audited inventory")
        if measurement_errors:
            return {"schemaVersion": 1, "status": "MEASUREMENT_BLOCK", "errors": measurement_errors}
        comparison = run_snapshot_checker(provider_root, report, current)
        if comparison["before"] != envelope["snapshot"]:
            return {
                "schemaVersion": 1,
                "status": "MEASUREMENT_BLOCK",
                "errors": ["saved snapshot does not match the envelope's embedded audit report"],
            }
        if comparison["status"] == "STALE":
            return {
                "schemaVersion": 1,
                "status": "STALE",
                "target": str(target),
                "changes": comparison["changes"],
            }
        return {
            "schemaVersion": 1,
            "status": "FRESH",
            "target": str(target),
            "snapshot": comparison["after"],
        }
    except (MeasurementError, OSError, UnicodeError, KeyError) as exc:
        return {"schemaVersion": 1, "status": "MEASUREMENT_BLOCK", "errors": [str(exc)]}


def run_self_test() -> None:
    missing = validate_envelope({})
    if not any("contract version" in item for item in missing):
        raise AssertionError("missing contract version was accepted")
    valid_shape = {
        "contract_version": CONTRACT_VERSION,
        "report": {},
        "provider": {
            "root": "provider",
            "revision": {
                "algorithm": "skill-revision-sha256-v1",
                "roots": 1,
                "files": 1,
                "bytes": 1,
                "sha256": "b" * 64,
            },
        },
        "adapter": {
            "sha256": "a" * 64,
            "revision": {
                "algorithm": "skill-revision-sha256-v1",
                "roots": 1,
                "files": 1,
                "bytes": 1,
                "sha256": "c" * 64,
            },
        },
        "snapshot": {"algorithm": "cleanup-inventory-sha256-v1"},
    }
    if validate_envelope(valid_shape):
        raise AssertionError("valid freshness envelope shape was rejected")
    malformed = json.loads(json.dumps(valid_shape))
    malformed["provider"]["revision"]["sha256"] = "invalid"
    if not any("provider.revision is invalid" in item for item in validate_envelope(malformed)):
        raise AssertionError("malformed provider revision was accepted")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        print("Cleanup evidence freshness self-test passed")
        return 0
    if not args.evidence:
        parser.error("evidence is required unless --self-test is used")
    report = verify(args.evidence.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "FRESH" else (1 if report["status"] == "STALE" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
