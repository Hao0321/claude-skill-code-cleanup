#!/usr/bin/env python3
"""Validate a closed-world, versioned product capability obligation ledger."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable


STATUSES = {"verified", "blocked_external", "planned", "unmeasured"}
SCOPES = {"internal", "public", "parity"}
PRIVATE_PATTERN = re.compile(
    r"(?:[a-z]:\\|\\\\|/Users/|/home/|\.claude[\\/]skills|\.codex[\\/]skills|(?:api[_-]?key|token|secret|password)\s*[:=])",
    re.IGNORECASE,
)


FailureSink = Callable[[str, str, str | None], None]


def package_product_name(package: dict[str, Any]) -> Any:
    build = package.get("build") if isinstance(package.get("build"), dict) else {}
    return package.get("productName") or build.get("productName") or package.get("name")


def resolve_product_context(manifest: Path, package_json: Path | None, root: Path | None) -> tuple[Path, Path]:
    manifest = manifest.resolve()
    explicit_package = package_json.resolve() if package_json else None
    if root:
        product_root = root.resolve()
    elif explicit_package:
        product_root = explicit_package.parent
    else:
        candidates = (manifest.parent, *manifest.parents)
        product_root = next((candidate for candidate in candidates if (candidate / "package.json").is_file()), manifest.parent)
    package_path = explicit_package or product_root / "package.json"
    try:
        manifest.relative_to(product_root)
    except ValueError as exc:
        raise ValueError("manifest must remain inside the product root") from exc
    if not package_path.is_file():
        raise ValueError(f"package.json not found: {package_path}")
    return product_root, package_path


def validate_header(
    document: dict[str, Any], package: dict[str, Any], scope: str, fail: FailureSink
) -> list[str]:
    if scope not in SCOPES:
        fail("invalid-scope", f"unsupported scope: {scope}")
    if document.get("schemaVersion") != 1:
        fail("schema-version", "schemaVersion must be 1")
    if document.get("product") != package_product_name(package):
        fail("product-drift", "product does not match package productName")
    if document.get("productVersion") != package.get("version"):
        fail("version-drift", "productVersion does not match package version")
    if PRIVATE_PATTERN.search(json.dumps(document, ensure_ascii=False)):
        fail("private-data", "ledger contains an absolute private path or secret-shaped text")

    required = document.get("requiredObligationIds")
    if not isinstance(required, list) or not required or any(not isinstance(item, str) or not item for item in required):
        fail("required-id-list", "requiredObligationIds must be a non-empty string array")
        return []
    elif len(set(required)) != len(required):
        fail("duplicate-required-id", "requiredObligationIds contains duplicates")
    return required


def validate_verified(
    obligation: dict[str, Any], obligation_id: str, root: Path,
    package: dict[str, Any], package_scripts: dict[str, Any], fail: FailureSink,
) -> None:
    if obligation.get("verifiedVersion") != package.get("version"):
        fail("stale-verification", "verifiedVersion does not match current product version", obligation_id)
    evidence = obligation.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        fail("missing-evidence", "verified obligation needs replayable evidence", obligation_id)
        evidence = []
    for entry in evidence:
        if not isinstance(entry, dict):
            fail("invalid-evidence", "evidence must be an object", obligation_id)
            continue
        value = entry.get("value")
        if entry.get("kind") == "npm_script":
            if not isinstance(value, str) or value not in package_scripts:
                fail("missing-npm-script", f"missing npm script: {value}", obligation_id)
        elif entry.get("kind") == "file":
            if not isinstance(value, str) or not value or "\\" in value:
                fail("unsafe-evidence-path", "evidence path must remain inside product root", obligation_id)
                continue
            path = PurePosixPath(value)
            if path.is_absolute() or "." in path.parts or ".." in path.parts or (path.parts and ":" in path.parts[0]):
                fail("unsafe-evidence-path", "evidence path must remain inside product root", obligation_id)
                continue
            candidate = root.joinpath(*path.parts).resolve()
            if root not in candidate.parents and candidate != root:
                fail("unsafe-evidence-path", "evidence path escapes product root", obligation_id)
            elif not candidate.is_file():
                fail("missing-evidence-file", f"missing evidence file: {value}", obligation_id)
        else:
            fail("invalid-evidence-kind", f"unsupported evidence kind: {entry.get('kind')}", obligation_id)


def validate_obligation(
    obligation: Any, root: Path, package: dict[str, Any], package_scripts: dict[str, Any],
    scope: str, by_id: dict[str, dict[str, Any]], fail: FailureSink,
) -> None:
    if not isinstance(obligation, dict):
        fail("invalid-obligation", "obligation must be an object")
        return
    obligation_id = obligation.get("id")
    if not isinstance(obligation_id, str) or not obligation_id:
        fail("missing-id", "obligation is missing id")
        return
    if obligation_id in by_id:
        fail("duplicate-id", f"duplicate obligation id: {obligation_id}", obligation_id)
    by_id[obligation_id] = obligation
    status = obligation.get("status")
    if status not in STATUSES:
        fail("invalid-status", f"unsupported status: {status}", obligation_id)
    required_for = obligation.get("requiredFor")
    if not isinstance(required_for, list) or any(item not in SCOPES for item in required_for):
        fail("invalid-required-for", "requiredFor must contain only internal/public/parity", obligation_id)
        required_for = []
    if status == "verified":
        validate_verified(obligation, obligation_id, root, package, package_scripts, fail)
    elif status == "blocked_external":
        blocker = obligation.get("blocker") if isinstance(obligation.get("blocker"), dict) else {}
        for field in ("owner", "condition", "action"):
            if not isinstance(blocker.get(field), str) or not blocker[field].strip():
                fail("incomplete-blocker", f"blocked_external missing blocker.{field}", obligation_id)
    elif not isinstance(obligation.get("nextExperiment"), str) or not obligation["nextExperiment"].strip():
        fail("missing-next-experiment", f"{status} obligation needs nextExperiment", obligation_id)
    if scope in required_for and status != "verified":
        fail("required-capability-open", f"{scope} obligation remains {status}", obligation_id)


def evaluate(document: dict[str, Any], root: Path, package: dict[str, Any], scope: str) -> dict[str, Any]:
    findings: list[dict[str, str]] = []

    def fail(code: str, message: str, obligation_id: str | None = None) -> None:
        item = {"status": "FAIL", "code": code, "message": message}
        if obligation_id:
            item["id"] = obligation_id
        findings.append(item)

    required = validate_header(document, package, scope, fail)

    obligations = document.get("obligations")
    if not isinstance(obligations, list):
        fail("obligations", "obligations must be an array")
        obligations = []
    by_id: dict[str, dict[str, Any]] = {}
    package_scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    root = root.resolve()

    for obligation in obligations:
        validate_obligation(obligation, root, package, package_scripts, scope, by_id, fail)

    for obligation_id in required:
        if obligation_id not in by_id:
            fail("missing-obligation", f"required obligation is missing: {obligation_id}", obligation_id)

    counts = {status: sum(1 for item in obligations if isinstance(item, dict) and item.get("status") == status) for status in sorted(STATUSES)}
    return {
        "schemaVersion": 1,
        "status": "BLOCK" if findings else "GREEN",
        "scope": scope,
        "productVersion": document.get("productVersion"),
        "counts": counts,
        "open": [
            {"id": item.get("id"), "status": item.get("status"), "requiredFor": item.get("requiredFor")}
            for item in obligations if isinstance(item, dict) and item.get("status") != "verified"
        ],
        "findings": findings or [{"status": "PASS", "code": "capability-obligation-closure", "message": f"{scope} obligations are closed"}],
    }


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="capability-gate-") as raw:
        root = Path(raw)
        (root / "proof.txt").write_text("proof", encoding="utf-8")
        package = {"productName": "Fixture", "version": "1.0.0", "scripts": {"test": "true"}}
        document = {
            "schemaVersion": 1,
            "product": "Fixture",
            "productVersion": "1.0.0",
            "requiredObligationIds": ["core", "signing"],
            "obligations": [
                {"id": "core", "title": "Core", "status": "verified", "requiredFor": ["internal", "public"], "verifiedVersion": "1.0.0", "evidence": [{"kind": "file", "value": "proof.txt"}, {"kind": "npm_script", "value": "test"}]},
                {"id": "signing", "title": "Signing", "status": "blocked_external", "requiredFor": ["public"], "blocker": {"owner": "owner", "condition": "missing certificate", "action": "provide certificate"}},
            ],
        }
        assert evaluate(document, root, package, "internal")["status"] == "GREEN"
        assert evaluate(document, root, package, "public")["status"] == "BLOCK"
        broken = json.loads(json.dumps(document))
        broken["obligations"] = broken["obligations"][1:]
        report = evaluate(broken, root, package, "internal")
        assert any(item["code"] == "missing-obligation" for item in report["findings"])
        broken = json.loads(json.dumps(document))
        broken["obligations"][0]["verifiedVersion"] = "0.9.0"
        report = evaluate(broken, root, package, "internal")
        assert any(item["code"] == "stale-verification" for item in report["findings"])
        broken = json.loads(json.dumps(document))
        del broken["obligations"][1]["blocker"]["action"]
        report = evaluate(broken, root, package, "internal")
        assert any(item["code"] == "incomplete-blocker" for item in report["findings"])
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?")
    parser.add_argument("--scope", choices=sorted(SCOPES), default="internal")
    parser.add_argument("--package-json")
    parser.add_argument("--root")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        print("capability gate self-test passed")
        return 0
    if not args.manifest:
        parser.error("manifest is required unless --self-test is used")
    manifest_path = Path(args.manifest).resolve()
    product_root, package_path = resolve_product_context(
        manifest_path,
        Path(args.package_json) if args.package_json else None,
        Path(args.root) if args.root else None,
    )
    report = evaluate(
        json.loads(manifest_path.read_text(encoding="utf-8")),
        product_root,
        json.loads(package_path.read_text(encoding="utf-8")),
        args.scope,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
