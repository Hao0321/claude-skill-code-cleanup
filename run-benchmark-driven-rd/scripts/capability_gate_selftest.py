"""Capability and security floor calibration fixtures."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable

def _test_security_capability_controls(document, package, root, security):
    generic_security = json.loads(json.dumps(security))
    for obligation in generic_security["obligations"][len(document["obligations"]):]:
        obligation["evidence"] = [{"kind": "file", "value": "proof.txt"}]
    report = evaluate(generic_security, root, package, "internal")
    assert any(
        item["code"] == "security-evidence-binding"
        for item in report["findings"]
    )

    partial_security = json.loads(json.dumps(security))
    partial_security["requiredObligationIds"].pop()
    partial_security["obligations"].pop()
    report = evaluate(partial_security, root, package, "internal")
    assert any(
        item["code"] == "security-capability-set"
        for item in report["findings"]
    )

    case_variant_security = json.loads(json.dumps(security))
    first_security = len(document["obligations"])
    case_variant_security["requiredObligationIds"][first_security] = (
        "Security.scan-scope"
    )
    case_variant_security["obligations"][first_security]["id"] = (
        "Security.scan-scope"
    )
    report = evaluate(case_variant_security, root, package, "internal")
    assert any(
        item["code"] == "security-capability-set"
        for item in report["findings"]
    )

    extra_security = json.loads(json.dumps(security))
    extra_security["requiredObligationIds"].append("security.unexpected")
    extra = json.loads(json.dumps(extra_security["obligations"][first_security]))
    extra["id"] = "security.unexpected"
    extra_security["obligations"].append(extra)
    report = evaluate(extra_security, root, package, "internal")
    assert any(
        item["code"] == "security-capability-set"
        for item in report["findings"]
    )

    colliding_security = json.loads(json.dumps(security))
    colliding_security["requiredObligationIds"].append("Security.scan-scope")
    collision = json.loads(json.dumps(colliding_security["obligations"][first_security]))
    collision["id"] = "Security.scan-scope"
    colliding_security["obligations"].append(collision)
    report = evaluate(colliding_security, root, package, "internal")
    codes = {item["code"] for item in report["findings"]}
    assert {
        "duplicate-required-id-casefold",
        "duplicate-id-casefold",
        "security-capability-set",
    }.issubset(codes)

    missing_security_scope = json.loads(json.dumps(security))
    missing_security_scope["obligations"][3]["requiredFor"] = ["internal"]
    report = evaluate(missing_security_scope, root, package, "internal")
    assert any(item["code"] == "required-scope-floor" for item in report["findings"])

def _security_capability_fixture(document, package, root):
    security = json.loads(json.dumps(document))
    security_receipt = root / "security-assessment.json"
    security_receipt.write_text("{}", encoding="utf-8")
    security_identity = streamed_identity(security_receipt)
    security_ids = list(SECURITY_CAPABILITY_IDS)
    security["requiredObligationIds"].extend(security_ids)
    security["obligations"].extend({
        "id": obligation_id,
        "title": obligation_id,
        "status": "verified",
        "requiredFor": ["internal", "public"],
        "verifiedVersion": "1.0.0",
        "evidence": [{
            "kind": "security-assessment",
            "capabilityId": obligation_id,
            "value": "security-assessment.json",
            "receiptBytes": security_identity["bytes"],
            "receiptSha256": security_identity["sha256"],
            "planSha256": "a" * 64,
            "snapshotSha256": "b" * 64,
            "routingInputSha256": "c" * 64,
            "controlCoverageSha256": "d" * 64,
        }],
    } for obligation_id in security_ids)
    assert evaluate(security, root, package, "internal")["status"] == "GREEN"
    return security

def run_self_test(api) -> None:
    globals().update({name: getattr(api, name) for name in ('evaluate', 'SECURITY_CAPABILITY_IDS', 'streamed_identity', 'resolve_product_context')})
    with tempfile.TemporaryDirectory(prefix="capability-gate-") as raw:
        root = Path(raw)
        (root / "proof.txt").write_text("proof", encoding="utf-8")
        package = {"productName": "Fixture", "version": "1.0.0", "scripts": {"test": "true"}}
        document = {
            "schemaVersion": 1,
            "product": "Fixture",
            "productVersion": "1.0.0",
            "requiredObligationIds": [
                "core", "update.client-check", "update.release-channel"
            ],
            "obligations": [
                {"id": "core", "title": "Core", "status": "verified", "requiredFor": ["internal", "public"], "verifiedVersion": "1.0.0", "evidence": [{"kind": "file", "value": "proof.txt"}, {"kind": "npm_script", "value": "test"}]},
                {"id": "update.client-check", "title": "Automatic update check client", "status": "verified", "requiredFor": ["internal", "public"], "verifiedVersion": "1.0.0", "evidence": [{"kind": "npm_script", "value": "test"}]},
                {"id": "update.release-channel", "title": "Authorized public update channel", "status": "blocked_external", "requiredFor": ["public"], "blocker": {"owner": "release-owner", "condition": "no authorized GitHub release channel", "action": "authorize and verify the exact repo/release/signer"}},
            ],
        }
        assert evaluate(document, root, package, "internal")["status"] == "GREEN"
        assert evaluate(document, root, package, "public")["status"] == "BLOCK"
        assert evaluate(document, root, package, "parity")["status"] == "BLOCK"
        parity_closed = json.loads(json.dumps(document))
        parity_closed["obligations"][2] = {
            "id": "update.release-channel", "title": "Authorized public update channel",
            "status": "verified", "requiredFor": ["public"],
            "verifiedVersion": "1.0.0",
            "evidence": [{"kind": "npm_script", "value": "test"}],
        }
        assert evaluate(parity_closed, root, package, "parity")["status"] == "GREEN"
        broken = json.loads(json.dumps(document))
        broken["obligations"] = broken["obligations"][1:]
        report = evaluate(broken, root, package, "internal")
        assert any(item["code"] == "missing-obligation" for item in report["findings"])
        broken = json.loads(json.dumps(document))
        broken["obligations"][0]["verifiedVersion"] = "0.9.0"
        report = evaluate(broken, root, package, "internal")
        assert any(item["code"] == "stale-verification" for item in report["findings"])
        broken = json.loads(json.dumps(document))
        broken["obligations"][1]["requiredFor"] = ["public"]
        report = evaluate(broken, root, package, "internal")
        assert any(item["code"] == "required-scope-floor" for item in report["findings"])
        broken = json.loads(json.dumps(document))
        del broken["obligations"][2]["blocker"]["action"]
        report = evaluate(broken, root, package, "internal")
        assert any(item["code"] == "incomplete-blocker" for item in report["findings"])
        security = _security_capability_fixture(document, package, root)
        _test_security_capability_controls(document, package, root, security)
        nested = root / "nested-product"
        (nested / ".rd").mkdir(parents=True)
        (nested / "package.json").write_text(json.dumps({"name": "fixture", "version": "1.0.0", "scripts": {"test": "true"}, "build": {"productName": "Fixture"}}), encoding="utf-8")
        manifest = nested / ".rd" / "capability-ledger.json"
        manifest.write_text(json.dumps(document), encoding="utf-8")
        (nested / ".rd" / "proof.txt").write_text("proof", encoding="utf-8")
        nested_document = json.loads(json.dumps(document))
        nested_document["obligations"][0]["evidence"][0]["value"] = ".rd/proof.txt"
        product_root, package_path = resolve_product_context(manifest, None, None)
        nested_package = json.loads(package_path.read_text(encoding="utf-8"))
        assert product_root == nested.resolve()
        nested_report = evaluate(nested_document, product_root, nested_package, "internal")
        assert nested_report["status"] == "GREEN", nested_report
