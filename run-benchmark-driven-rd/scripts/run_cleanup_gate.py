#!/usr/bin/env python3
"""Capture and gate code-cleanup-helper evidence for benchmark-driven R&D."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from cleanup_gate_runtime import (
    MeasurementError,
    capture_skill_revision,
    digest_files,
    normalized_path,
    resolve_active_cleanup_root as _resolve_active_cleanup_root,
    resolve_cleanup_root as _resolve_cleanup_root,
    validate_skill_revision_snapshot,
)
from cleanup_gate_update_coverage import (
    SUPPORTED_PROVIDER_SCHEMAS,
    schema_12_fixture,
    schema_required_fields,
    validate_update_coverage,
)


CONTRACT_VERSION = "1.2"
STATUSES = {"PASS", "FAIL", "REVIEW", "NOT_CHECKED"}
BASE_REQUIRED_FIELDS = {
    "schema_version",
    "target",
    "mode",
    "config",
    "summary",
    "inventory",
    "architecture",
    "findings",
}
PROVIDER_FILES = (
    "audit.py",
    "audit_core.py",
    "self_test.py",
    "check_build_receipt.py",
    "check_audit_snapshot.py",
    "check_skill_revision.py",
)
ADAPTER_FILES = (
    "run_cleanup_gate.py",
    "cleanup_gate_paths.py",
    "cleanup_gate_runtime.py",
    "cleanup_gate_command.py",
    "cleanup_gate_update_coverage.py",
)


def resolve_cleanup_root(explicit: Path | None = None) -> Path:
    return _resolve_cleanup_root(PROVIDER_FILES, explicit)


def resolve_active_cleanup_root(explicit: Path | None = None) -> Path:
    return _resolve_active_cleanup_root(PROVIDER_FILES, explicit)


def adapter_sha256() -> str:
    root = Path(__file__).resolve().parents[1]
    return digest_files([root / "scripts" / name for name in ADAPTER_FILES], root)


def parse_single_json(raw: str) -> dict[str, Any]:
    text = raw.lstrip("\ufeff\r\n\t ")
    try:
        value, offset = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError as exc:
        raise MeasurementError(f"provider stdout is not valid JSON: {exc}") from exc
    if text[offset:].strip():
        raise MeasurementError("provider stdout contains trailing non-JSON output")
    if not isinstance(value, dict):
        raise MeasurementError("provider JSON root must be an object")
    return value


def run_snapshot_checker(
    cleanup_root: Path, before: dict[str, Any], after: dict[str, Any]
) -> dict[str, Any]:
    checker = cleanup_root / "scripts" / "check_audit_snapshot.py"
    environment = {**os.environ, "PYTHONUTF8": "1"}
    with tempfile.TemporaryDirectory(prefix="cleanup-snapshot-contract-") as raw:
        root = Path(raw)
        before_path = root / "before.json"
        after_path = root / "after.json"
        before_path.write_text(json.dumps(before, ensure_ascii=False), encoding="utf-8")
        after_path.write_text(json.dumps(after, ensure_ascii=False), encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(checker),
                str(before_path),
                str(after_path),
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            env=environment,
            check=False,
        )
    if completed.returncode not in {0, 1}:
        detail = (completed.stderr or completed.stdout).strip()
        raise MeasurementError(f"snapshot checker failed with exit {completed.returncode}: {detail}")
    result = parse_single_json(completed.stdout)
    if result.get("schemaVersion") != 1 or result.get("status") not in {"FRESH", "STALE"}:
        raise MeasurementError("snapshot checker returned an unsupported contract")
    return result


def validate_report(report: dict[str, Any], target: Path, mode: str) -> list[str]:
    errors: list[str] = []
    schema = str(report.get("schema_version"))
    required_fields = BASE_REQUIRED_FIELDS | schema_required_fields(schema)
    missing = sorted(required_fields - set(report))
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
    if schema not in SUPPORTED_PROVIDER_SCHEMAS:
        errors.append(f"unsupported provider schema: {report.get('schema_version')!r}")
    if report.get("mode") != mode:
        errors.append(f"mode mismatch: expected {mode!r}, got {report.get('mode')!r}")
    try:
        actual_target = normalized_path(str(report.get("target", "")))
    except (OSError, ValueError):
        actual_target = ""
    if actual_target != normalized_path(target):
        errors.append(f"target mismatch: expected {target.resolve()}, got {report.get('target')!r}")

    findings = report.get("findings")
    summary = report.get("summary")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
        return errors
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
        return errors

    counts: Counter[str] = Counter()
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"findings[{index}] must be an object")
            continue
        status = finding.get("status")
        if status not in STATUSES:
            errors.append(f"findings[{index}] has unsupported status {status!r}")
            continue
        counts[status] += 1
    keys = {"PASS": "pass", "FAIL": "fail", "REVIEW": "review", "NOT_CHECKED": "not_checked"}
    for status, key in keys.items():
        if summary.get(key) != counts[status]:
            errors.append(
                f"summary.{key} mismatch: expected {counts[status]}, got {summary.get(key)!r}"
            )
    errors.extend(validate_update_coverage(report, findings))
    return errors


def validate_config_scope(report: dict[str, Any], target: Path) -> list[str]:
    target_config = target.resolve() / "audit.config.json"
    if not target_config.is_file():
        return []
    loaded = report.get("config")
    if loaded:
        try:
            if Path(str(loaded)).resolve() == target_config.resolve():
                return []
        except (OSError, ValueError):
            pass
    generated_segments = {"node_modules", "dist", "target", "vendor", "desktop-dist"}
    leaked = []
    for item in report.get("inventory", []):
        path = str(item.get("path", "")).replace("\\", "/")
        if any(segment.lower() in generated_segments for segment in path.split("/")[:-1]):
            leaked.append(path)
            if len(leaked) == 5:
                break
    if not leaked:
        return []
    return [
        "effective cleanup config bypassed target audit.config.json and included generated directories: "
        + ", ".join(leaked)
    ]


def preflight_config_scope(target: Path, config: Path | None) -> None:
    target_config = target.resolve() / "audit.config.json"
    if not config or not target_config.is_file() or config.resolve() == target_config.resolve():
        return
    try:
        configured = json.loads(config.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MeasurementError(f"cleanup config preflight failed: {exc}") from exc
    patterns = [str(item).replace("\\", "/").lower() for item in configured.get("exclude", [])]
    generated_roots = ["node_modules", "dist", "target", "vendor", "desktop-dist"]
    exposed = [name for name in generated_roots if (target / name).exists() and not any(name in pattern for pattern in patterns)]
    if exposed:
        raise MeasurementError(
            "external cleanup config bypasses target audit.config.json without excluding present generated roots: "
            + ", ".join(exposed)
        )


def required_dimension_blocks(report: dict[str, Any], required: set[int]) -> list[str]:
    blocks: list[str] = []
    findings = report["findings"]
    for dimension in sorted(required):
        matches = [item for item in findings if item.get("dimension") == dimension]
        if not matches:
            blocks.append(f"required dimension D{dimension} is absent")
        elif any(item.get("status") == "NOT_CHECKED" for item in matches):
            blocks.append(f"required dimension D{dimension} is NOT_CHECKED")
    return blocks


def build_envelope(
    report: dict[str, Any],
    cleanup_root: Path,
    evaluator_sha256: str,
    config_sha256: str | None,
    phase: str,
    required_dimensions: set[int],
    review_policy: str = "visible",
    snapshot: dict[str, Any] | None = None,
    adapter_hash: str | None = None,
    provider_revision: dict[str, Any] | None = None,
    adapter_revision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blocks: list[str] = []
    if phase == "promotion" and report["summary"]["fail"]:
        blocks.append(f"promotion has {report['summary']['fail']} FAIL finding(s)")
    if phase == "promotion" and review_policy == "block" and report["summary"]["review"]:
        blocks.append(f"promotion has {report['summary']['review']} unresolved REVIEW finding(s)")
    if phase == "promotion":
        blocks.extend(required_dimension_blocks(report, required_dimensions))
    decision = "BASELINE_CAPTURED" if phase == "baseline" else ("BLOCK" if blocks else "ALLOW")
    return {
        "contract_version": CONTRACT_VERSION,
        "decision": decision,
        "phase": phase,
        "review_policy": review_policy,
        "adapter": {
            "skill": "run-benchmark-driven-rd",
            "sha256": adapter_hash,
            "revision": adapter_revision,
        },
        "provider": {
            "skill": "code-cleanup-helper",
            "root": str(cleanup_root),
            "schema_version": report["schema_version"],
            "evaluator_sha256": evaluator_sha256,
            "config_sha256": config_sha256,
            "revision": provider_revision,
        },
        "required_dimensions": sorted(required_dimensions),
        "snapshot": snapshot,
        "block_reasons": blocks,
        "unmeasured": [
            item for item in report["findings"] if item.get("status") == "NOT_CHECKED"
        ],
        "update_coverage": report.get("update_coverage"),
        "report": report,
    }


def run_provider(
    cleanup_root: Path,
    target: Path,
    mode: str,
    config: Path | None,
) -> tuple[dict[str, Any], str, str | None, dict[str, Any]]:
    scripts = cleanup_root / "scripts"
    preflight_config_scope(target, config)
    environment = {**os.environ, "PYTHONUTF8": "1"}
    revision = capture_skill_revision(cleanup_root, cleanup_root)
    self_test = subprocess.run(
        [sys.executable, str(scripts / "self_test.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=environment,
        check=False,
    )
    if self_test.returncode != 0:
        detail = (self_test.stderr or self_test.stdout).strip()
        raise MeasurementError(f"provider self-test failed: {detail}")

    command = [
        sys.executable,
        str(scripts / "audit.py"),
        str(target.resolve()),
        "--mode",
        mode,
        "--format",
        "json",
    ]
    if config:
        command.extend(["--config", str(config.resolve())])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=environment,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise MeasurementError(f"provider audit failed with exit {completed.returncode}: {detail}")
    report = parse_single_json(completed.stdout)
    errors = validate_report(report, target, mode) + validate_config_scope(report, target)
    if errors:
        raise MeasurementError("; ".join(errors))

    provider_paths = [scripts / name for name in PROVIDER_FILES]
    evaluator_sha256 = digest_files(provider_paths, cleanup_root)
    loaded_config = report.get("config")
    config_sha256 = None
    if loaded_config:
        config_path = Path(str(loaded_config)).resolve()
        config_sha256 = digest_files([config_path], config_path.parent)
    current_revision = capture_skill_revision(
        cleanup_root, cleanup_root, expected_sha256=revision["sha256"]
    )
    return report, evaluator_sha256, config_sha256, current_revision


def parse_dimensions(raw: str) -> set[int]:
    if not raw.strip():
        return set()
    try:
        values = {int(item.strip()) for item in raw.split(",") if item.strip()}
    except ValueError as exc:
        raise argparse.ArgumentTypeError("dimensions must be comma-separated integers") from exc
    if any(value < 1 for value in values):
        raise argparse.ArgumentTypeError("dimensions must be positive integers")
    return values


def write_envelope(envelope: dict[str, Any], output: Path | None, quiet: bool = False) -> None:
    payload = json.dumps(envelope, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    if not quiet:
        sys.stdout.write(payload)


def run_config_scope_self_test(provider_root: Path, base: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory(prefix="cleanup-config-scope-") as raw:
        scoped_target = Path(raw)
        (scoped_target / "audit.config.json").write_text("{}", encoding="utf-8")
        (scoped_target / "node_modules").mkdir()
        try:
            preflight_config_scope(scoped_target, provider_root / "audit.config.json")
        except MeasurementError:
            pass
        else:
            raise AssertionError("external config exposed a generated root without a preflight block")
        polluted = json.loads(json.dumps(base))
        polluted["target"] = str(scoped_target)
        polluted["config"] = str(provider_root / "audit.config.json")
        polluted["inventory"] = [{"path": "node_modules/pkg/index.js"}]
        assert validate_config_scope(polluted, scoped_target)


def run_self_test() -> None:
    target = Path.cwd().resolve()
    provider_root = resolve_cleanup_root()
    revision = capture_skill_revision(provider_root, provider_root)
    assert revision["algorithm"] == "skill-revision-sha256-v1"
    assert capture_skill_revision(provider_root, provider_root, revision["sha256"]) == revision
    validate_skill_revision_snapshot(revision)
    malformed_revision = {**revision, "sha256": "invalid"}
    try:
        validate_skill_revision_snapshot(malformed_revision)
    except MeasurementError:
        pass
    else:
        raise AssertionError("malformed Skill revision snapshot was accepted")
    assert resolve_active_cleanup_root(provider_root) == provider_root
    base = {
        "schema_version": "1.1",
        "target": str(target),
        "mode": "architecture",
        "config": None,
        "summary": {"files": 1, "lines": 1, "bytes": 1, "pass": 0, "fail": 1, "review": 1, "not_checked": 1},
        "inventory": [],
        "architecture": {},
        "findings": [
            {"dimension": 10, "status": "FAIL", "code": "fixture-fail"},
            {"dimension": 4, "status": "REVIEW", "code": "fixture-review"},
            {"dimension": 6, "status": "NOT_CHECKED", "code": "fixture-unmeasured"},
        ],
    }
    assert not validate_report(base, target, "architecture")
    provider_12, coverage = schema_12_fixture(base)
    assert not validate_report(provider_12, target, "architecture")
    envelope_12 = build_envelope(
        provider_12, target, "a" * 64, None, "baseline", set()
    )
    assert envelope_12["update_coverage"] == coverage
    assert envelope_12["report"]["findings"][-1]["status"] == "REVIEW"
    unsupported = json.loads(json.dumps(provider_12))
    unsupported["schema_version"] = "9.9"
    assert any(
        "unsupported provider schema" in item
        for item in validate_report(unsupported, target, "architecture")
    )
    baseline = build_envelope(base, target, "a" * 64, None, "baseline", {6})
    assert baseline["decision"] == "BASELINE_CAPTURED"
    promotion = build_envelope(base, target, "a" * 64, None, "promotion", {6})
    assert promotion["decision"] == "BLOCK"
    assert any("FAIL" in item for item in promotion["block_reasons"])
    assert any("NOT_CHECKED" in item for item in promotion["block_reasons"])
    review_only = json.loads(json.dumps(base))
    review_only["summary"] = {"files": 1, "lines": 1, "bytes": 1, "pass": 0, "fail": 0, "review": 1, "not_checked": 0}
    review_only["findings"] = [{"dimension": 4, "status": "REVIEW", "code": "fixture-review"}]
    visible = build_envelope(review_only, target, "a" * 64, None, "promotion", set())
    strict = build_envelope(
        review_only, target, "a" * 64, None, "promotion", set(), review_policy="block"
    )
    assert visible["decision"] == "ALLOW"
    assert strict["decision"] == "BLOCK"
    assert any("REVIEW" in item for item in strict["block_reasons"])
    clean_snapshot = run_snapshot_checker(provider_root, base, json.loads(json.dumps(base)))
    assert clean_snapshot["status"] == "FRESH"
    changed_report = json.loads(json.dumps(base))
    changed_report["inventory"] = [
        {"path": "new.py", "lines": 1, "bytes": 4, "sha256": "b" * 64}
    ]
    assert run_snapshot_checker(provider_root, base, changed_report)["status"] == "STALE"
    mismatch = json.loads(json.dumps(base))
    mismatch["summary"]["review"] = 0
    assert any("summary.review mismatch" in item for item in validate_report(mismatch, target, "architecture"))
    run_config_scope_self_test(provider_root, base)
    try:
        parse_single_json('{"ok": true}\ntrailing')
    except MeasurementError:
        pass
    else:
        raise AssertionError("trailing provider output was accepted")
    with tempfile.TemporaryDirectory(prefix="invalid-cleanup-provider-") as raw:
        try:
            resolve_cleanup_root(Path(raw))
        except MeasurementError:
            pass
        else:
            raise AssertionError("invalid explicit provider silently fell back to another installation")
    with tempfile.TemporaryDirectory(prefix="quiet-cleanup-envelope-") as raw:
        output = Path(raw) / "envelope.json"
        write_envelope(baseline, output, quiet=True)
        if json.loads(output.read_text(encoding="utf-8"))["decision"] != "BASELINE_CAPTURED":
            raise AssertionError("quiet output did not preserve the evidence envelope")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", type=Path)
    parser.add_argument("--mode", choices=("a", "b", "architecture", "all"), default="architecture")
    parser.add_argument("--phase", choices=("baseline", "promotion"), default="baseline")
    parser.add_argument(
        "--review-policy",
        choices=("visible", "block"),
        default="visible",
        help="keep REVIEW visible or block promotion until every REVIEW is resolved",
    )
    parser.add_argument("--require-checked", type=parse_dimensions, default=set())
    parser.add_argument("--config", type=Path)
    parser.add_argument("--cleanup-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress the JSON envelope on stdout; requires --output",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        run_self_test()
        print("R&D Cleanup gate self-test passed")
        return 0
    if not args.target:
        raise SystemExit("target is required unless --self-test is used")
    if args.quiet and not args.output:
        raise SystemExit("--quiet requires --output so evidence cannot be discarded")
    from cleanup_gate_command import execute

    return execute(args, sys.modules[__name__])


if __name__ == "__main__":
    raise SystemExit(main())
