#!/usr/bin/env python3
"""Close a long-running product scope against fresh live evidence in one gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from capability_gate import evaluate as evaluate_capabilities
from delivery_contract_gate import evaluate as evaluate_delivery
from evidence_identity import valid_identity
from run_cleanup_gate import parse_single_json, resolve_cleanup_root
from verify_cleanup_evidence import verify as verify_cleanup


SCOPES = {"internal", "public", "parity"}
CHECK_KINDS = {
    "cleanup-promotion",
    "delivery-contract",
    "capability-ledger",
    "build-receipt",
    "file-identity",
    "json-evidence",
}
REQUIRED_NEGATIVE_CONTROLS = {
    "missing-required-check",
    "duplicate-check-id",
    "unsafe-path",
    "stale-file-identity",
    "cleanup-not-fresh",
    "cleanup-not-strict",
    "delivery-block",
    "capability-block",
    "build-receipt-block",
    "evidence-assertion",
}

FailureSink = Callable[..., None]
CleanupVerifier = Callable[[Path], dict[str, Any]]
DeliveryEvaluator = Callable[[dict[str, Any], Path], dict[str, Any]]
CapabilityEvaluator = Callable[[dict[str, Any], Path, dict[str, Any], str], dict[str, Any]]
ReceiptVerifier = Callable[[Path, str], dict[str, Any]]


def file_identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _resolve(root: Path, value: Any, *, directory: bool = False) -> tuple[Path | None, str | None]:
    if not isinstance(value, str) or not value or "\\" in value:
        return None, "path must be a non-empty root-relative POSIX string"
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        return None, "path must remain inside the closure root"
    candidate = (root / Path(*relative.parts)).resolve()
    if candidate != root and root not in candidate.parents:
        return None, "path resolves outside the closure root"
    if candidate.is_symlink():
        return None, "symlink paths are not accepted"
    if directory and not candidate.is_dir():
        return None, "directory is missing"
    if not directory and not candidate.is_file():
        return None, "file is missing"
    return candidate, None


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _check_identity(path: Path, check: dict[str, Any], check_id: str, fail: FailureSink) -> None:
    if not valid_identity(check):
        fail("invalid-file-identity", "check needs positive bytes and lowercase SHA-256", check_id)
        return
    if file_identity(path) != {"bytes": check["bytes"], "sha256": check["sha256"]}:
        fail("stale-file-identity", "live file no longer matches the closure contract", check_id, path=check.get("path"))


def _json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("JSON pointer must be empty or begin with /")
    current = document
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        elif isinstance(current, dict):
            current = current[token]
        else:
            raise KeyError(token)
    return current


def default_receipt_verifier(project_root: Path, receipt: str) -> dict[str, Any]:
    cleanup_root = resolve_cleanup_root()
    checker = cleanup_root / "scripts" / "check_build_receipt.py"
    completed = subprocess.run(
        [sys.executable, str(checker), str(project_root), "--receipt", receipt, "--format", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env={**os.environ, "PYTHONUTF8": "1"},
        check=False,
    )
    try:
        report = parse_single_json(completed.stdout)
    except Exception as exc:  # normalized below as measurement evidence
        return {"status": "ERROR", "errors": [str(exc), completed.stderr.strip()]}
    if completed.returncode != 0 and report.get("status") == "GREEN":
        return {"status": "ERROR", "errors": ["receipt checker exited nonzero with GREEN JSON"]}
    return report


def _check_cleanup(check: dict[str, Any], path: Path, check_id: str, fail: FailureSink,
                   verifier: CleanupVerifier) -> None:
    envelope = _read_json(path)
    summary = envelope.get("report", {}).get("summary", {})
    if envelope.get("phase") != "promotion" or envelope.get("decision") != "ALLOW":
        fail("cleanup-not-promoted", "Cleanup evidence must be an allowed promotion", check_id)
    if envelope.get("review_policy") != "block" or summary.get("fail") != 0 or summary.get("review") != 0:
        fail("cleanup-not-strict", "completion requires strict Cleanup with zero FAIL and REVIEW", check_id)
    result = verifier(path)
    if result.get("status") != "FRESH":
        fail("cleanup-not-fresh", "Cleanup promotion is stale or measurement-blocked", check_id, result=result)


def _check_delivery(check: dict[str, Any], path: Path, root: Path, check_id: str,
                    product: str, version: str, fail: FailureSink,
                    evaluator: DeliveryEvaluator) -> None:
    evidence_root_value = check.get("evidenceRoot")
    if evidence_root_value in (None, "."):
        evidence_root = root
    else:
        evidence_root, error = _resolve(root, evidence_root_value, directory=True)
        if error or evidence_root is None:
            fail("unsafe-path", f"delivery evidenceRoot: {error}", check_id)
            return
    result = evaluator(_read_json(path), evidence_root)
    if result.get("status") != "GREEN":
        fail("delivery-block", "delivery contract did not close", check_id, result=result)
    if result.get("product") != product or result.get("productVersion") != version:
        fail("delivery-version-drift", "delivery identity differs from completion identity", check_id)


def _check_capabilities(check: dict[str, Any], manifest: Path, root: Path, check_id: str,
                        scope: str, product: str, version: str, fail: FailureSink,
                        evaluator: CapabilityEvaluator) -> None:
    package, error = _resolve(root, check.get("packageJson"))
    if error or package is None:
        fail("unsafe-path", f"capability packageJson: {error}", check_id)
        return
    ledger = _read_json(manifest)
    result = evaluator(ledger, package.parent, _read_json(package), scope)
    if result.get("status") != "GREEN":
        fail("capability-block", f"{scope} capability obligations remain open", check_id, result=result)
    if ledger.get("product") != product or ledger.get("productVersion") != version:
        fail("capability-version-drift", "capability identity differs from completion identity", check_id)


def _check_receipt(check: dict[str, Any], root: Path, check_id: str, fail: FailureSink,
                   verifier: ReceiptVerifier) -> None:
    project_root, error = _resolve(root, check.get("projectRoot"), directory=True)
    receipt = check.get("receipt")
    if error or project_root is None:
        fail("unsafe-path", f"build receipt projectRoot: {error}", check_id)
    elif not isinstance(receipt, str) or not receipt or "\\" in receipt:
        fail("unsafe-path", "build receipt path must be a relative POSIX string", check_id)
    else:
        result = verifier(project_root, receipt)
        if result.get("status") != "GREEN":
            fail("build-receipt-block", "live build receipt is stale or invalid", check_id, result=result)


def _check_json_evidence(check: dict[str, Any], path: Path, check_id: str,
                         fail: FailureSink) -> None:
    _check_identity(path, check, check_id, fail)
    assertions = check.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        fail("evidence-assertion", "json-evidence needs at least one assertion", check_id)
        return
    document = _read_json(path)
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


def _validate_header(document: dict[str, Any], fail: FailureSink) -> tuple[str, str, str]:
    if document.get("schemaVersion") != 1:
        fail("schema-version", "schemaVersion must be 1", None)
    product = document.get("product")
    version = document.get("productVersion")
    scope = document.get("scope")
    if not isinstance(product, str) or not product.strip():
        fail("missing-product", "product must be a non-empty string", None)
        product = ""
    if not isinstance(version, str) or not version.strip():
        fail("missing-version", "productVersion must be a non-empty string", None)
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
    return product, version, scope


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
    receipt_verifier: ReceiptVerifier,
) -> tuple[list[str], set[str]]:
    checked: list[str] = []
    seen: set[str] = set()
    path_roles: set[str] = set()

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

        if kind == "build-receipt":
            _check_receipt(raw, root, check_id, fail, receipt_verifier)
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
                _check_cleanup(raw, path, check_id, fail, cleanup_verifier)
            elif kind == "delivery-contract":
                _check_delivery(raw, path, root, check_id, product, version, fail, delivery_evaluator)
            elif kind == "capability-ledger":
                _check_capabilities(raw, path, root, check_id, scope, product, version, fail, capability_evaluator)
            elif kind == "file-identity":
                _check_identity(path, raw, check_id, fail)
            elif kind == "json-evidence":
                _check_json_evidence(raw, path, check_id, fail)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, KeyError) as exc:
            fail("measurement-error", str(exc), check_id)
    return checked, seen


def evaluate(
    document: dict[str, Any], root: Path, *,
    cleanup_verifier: CleanupVerifier = verify_cleanup,
    delivery_evaluator: DeliveryEvaluator = evaluate_delivery,
    capability_evaluator: CapabilityEvaluator = evaluate_capabilities,
    receipt_verifier: ReceiptVerifier = default_receipt_verifier,
) -> dict[str, Any]:
    root = root.resolve()
    findings: list[dict[str, Any]] = []

    def fail(code: str, message: str, check_id: str | None, **details: Any) -> None:
        item = {"status": "FAIL", "code": code, "message": message}
        if check_id:
            item["id"] = check_id
        item.update(details)
        findings.append(item)

    product, version, scope = _validate_header(document, fail)
    required, checks = _declared_checks(document, fail)
    checked, seen = _run_checks(
        checks, root, product, version, scope, fail, cleanup_verifier,
        delivery_evaluator, capability_evaluator, receipt_verifier,
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
        "product": product,
        "productVersion": version,
        "scope": scope,
        "checked": checked,
        "findings": findings or [{
            "status": "PASS",
            "code": "completion-closure",
            "message": "all declared live completion checks are fresh and closed",
        }],
    }


def fixture_document(root: Path) -> dict[str, Any]:
    files = {
        "cleanup": root / "evidence/cleanup.json",
        "delivery": root / "evidence/delivery.json",
        "ledger": root / "product/capabilities.json",
        "package": root / "product/package.json",
        "artifact": root / "dist/setup.exe",
        "evidence": root / "evidence/performance.json",
        "receipt": root / "product/receipt.json",
    }
    for path in files.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    files["cleanup"].write_text(json.dumps({
        "phase": "promotion", "decision": "ALLOW", "review_policy": "block",
        "report": {"summary": {"fail": 0, "review": 0}},
    }), encoding="utf-8")
    files["delivery"].write_text("{}", encoding="utf-8")
    files["ledger"].write_text(json.dumps({"product": "Fixture", "productVersion": "1.0.0"}), encoding="utf-8")
    files["package"].write_text(json.dumps({"productName": "Fixture", "version": "1.0.0"}), encoding="utf-8")
    files["artifact"].write_bytes(b"installer")
    files["evidence"].write_text('{"status":"GREEN"}', encoding="utf-8")
    files["receipt"].write_text("{}", encoding="utf-8")
    return {
        "schemaVersion": 1,
        "product": "Fixture",
        "productVersion": "1.0.0",
        "scope": "internal",
        "requiredCheckIds": ["cleanup", "delivery", "capabilities", "receipt", "artifact", "performance"],
        "negativeControls": sorted(REQUIRED_NEGATIVE_CONTROLS),
        "checks": [
            {"id": "cleanup", "kind": "cleanup-promotion", "path": "evidence/cleanup.json"},
            {"id": "delivery", "kind": "delivery-contract", "path": "evidence/delivery.json"},
            {"id": "capabilities", "kind": "capability-ledger", "path": "product/capabilities.json", "packageJson": "product/package.json"},
            {"id": "receipt", "kind": "build-receipt", "projectRoot": "product", "receipt": "receipt.json"},
            {"id": "artifact", "kind": "file-identity", "path": "dist/setup.exe", **file_identity(files["artifact"])},
            {"id": "performance", "kind": "json-evidence", "path": "evidence/performance.json", **file_identity(files["evidence"]), "assertions": [{"pointer": "/status", "equals": "GREEN"}]},
        ],
    }


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="completion-closure-") as raw:
        root = Path(raw)
        document = fixture_document(root)
        adapters = {
            "cleanup_verifier": lambda _path: {"status": "FRESH"},
            "delivery_evaluator": lambda _doc, _root: {"status": "GREEN", "product": "Fixture", "productVersion": "1.0.0"},
            "capability_evaluator": lambda _doc, product_root, package, _scope: {
                "status": "GREEN" if (
                    product_root == (root / "product").resolve()
                    and package.get("productName") == "Fixture"
                ) else "BLOCK"
            },
            "receipt_verifier": lambda _root, _receipt: {"status": "GREEN"},
        }
        if evaluate(document, root, **adapters)["status"] != "GREEN":
            raise AssertionError("valid completion fixture was rejected")

        def rejected(mutator: Callable[[dict[str, Any]], None], code: str, **overrides: Any) -> None:
            broken = json.loads(json.dumps(document))
            mutator(broken)
            report = evaluate(broken, root, **{**adapters, **overrides})
            if not any(item["code"] == code for item in report["findings"]):
                raise AssertionError(f"completion negative {code} was not detected: {report}")

        rejected(lambda value: value["checks"].pop(), "missing-required-check")
        rejected(lambda value: value["checks"].append(dict(value["checks"][0])), "duplicate-check-id")
        rejected(lambda value: value["checks"][4].update({"path": "../escape"}), "unsafe-path")
        rejected(lambda value: value["checks"][4].update({"sha256": "0" * 64}), "stale-file-identity")
        rejected(lambda value: None, "cleanup-not-fresh", cleanup_verifier=lambda _path: {"status": "STALE"})
        cleanup_path = root / "evidence" / "cleanup.json"
        cleanup_original = cleanup_path.read_text(encoding="utf-8")
        cleanup_path.write_text(json.dumps({
            "phase": "promotion", "decision": "ALLOW", "review_policy": "visible",
            "report": {"summary": {"fail": 0, "review": 0}},
        }), encoding="utf-8")
        strict_report = evaluate(document, root, **adapters)
        cleanup_path.write_text(cleanup_original, encoding="utf-8")
        if not any(item["code"] == "cleanup-not-strict" for item in strict_report["findings"]):
            raise AssertionError(f"completion negative cleanup-not-strict was not detected: {strict_report}")
        rejected(lambda value: None, "delivery-block", delivery_evaluator=lambda _doc, _root: {"status": "BLOCK", "product": "Fixture", "productVersion": "1.0.0"})
        rejected(lambda value: None, "capability-block", capability_evaluator=lambda _doc, _root, _package, _scope: {"status": "BLOCK"})
        rejected(lambda value: None, "build-receipt-block", receipt_verifier=lambda _root, _receipt: {"status": "BLOCK"})
        rejected(lambda value: value["checks"][5]["assertions"][0].update({"equals": "BLOCK"}), "evidence-assertion")
        rejected(lambda value: value.update({"productVersion": "2.0.0"}), "delivery-version-drift")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", nargs="?", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        print("completion closure self-test passed")
        return 0
    if not args.contract:
        parser.error("contract is required unless --self-test is used")
    if args.quiet and not args.output:
        parser.error("--quiet requires --output")
    contract_path = args.contract.resolve()
    root = args.root.resolve() if args.root else contract_path.parent
    report = evaluate(_read_json(contract_path), root)
    report["evaluator"] = {"path": str(Path(__file__).resolve()), **file_identity(Path(__file__).resolve())}
    report["contract"] = {"path": str(contract_path), **file_identity(contract_path)}
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, delete=False) as handle:
            handle.write(payload)
            temporary = Path(handle.name)
        temporary.replace(output)
    if not args.quiet:
        print(payload, end="")
    return 0 if report["status"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
