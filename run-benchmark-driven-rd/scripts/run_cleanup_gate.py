#!/usr/bin/env python3
"""Capture and gate code-cleanup-helper evidence for benchmark-driven R&D."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "1.0"
SUPPORTED_PROVIDER_SCHEMAS = {"1.1"}
STATUSES = {"PASS", "FAIL", "REVIEW", "NOT_CHECKED"}
REQUIRED_FIELDS = {
    "schema_version",
    "target",
    "mode",
    "config",
    "summary",
    "inventory",
    "architecture",
    "findings",
}
PROVIDER_FILES = ("audit.py", "audit_core.py", "self_test.py")


class MeasurementError(RuntimeError):
    """The evaluator failed its machine contract."""


def normalized_path(value: str | Path) -> str:
    return os.path.normcase(str(Path(value).resolve()))


def resolve_cleanup_root(explicit: Path | None = None) -> Path:
    if explicit:
        root = explicit.resolve()
        if all((root / "scripts" / name).is_file() for name in PROVIDER_FILES):
            return root
        raise MeasurementError(f"explicit code-cleanup-helper provider is invalid: {root}")
    candidates: list[Path] = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        candidates.append(Path(codex_home) / "skills" / "code-cleanup-helper")
    candidates.extend(
        [
            Path(__file__).resolve().parents[2] / "code-cleanup-helper",
            Path.home() / ".codex" / "skills" / "code-cleanup-helper",
        ]
    )
    for candidate in candidates:
        root = candidate.resolve()
        if all((root / "scripts" / name).is_file() for name in PROVIDER_FILES):
            return root
    checked = ", ".join(str(item.resolve()) for item in candidates)
    raise MeasurementError(f"code-cleanup-helper provider not found; checked: {checked}")


def digest_files(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        if not path.is_file():
            raise MeasurementError(f"evaluator file missing: {path}")
        try:
            label = path.relative_to(root).as_posix()
        except ValueError:
            label = path.name
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


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


def validate_report(report: dict[str, Any], target: Path, mode: str) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(report))
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
    if str(report.get("schema_version")) not in SUPPORTED_PROVIDER_SCHEMAS:
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
    return errors


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
) -> dict[str, Any]:
    blocks: list[str] = []
    if phase == "promotion" and report["summary"]["fail"]:
        blocks.append(f"promotion has {report['summary']['fail']} FAIL finding(s)")
    if phase == "promotion":
        blocks.extend(required_dimension_blocks(report, required_dimensions))
    decision = "BASELINE_CAPTURED" if phase == "baseline" else ("BLOCK" if blocks else "ALLOW")
    return {
        "contract_version": CONTRACT_VERSION,
        "decision": decision,
        "phase": phase,
        "provider": {
            "skill": "code-cleanup-helper",
            "root": str(cleanup_root),
            "schema_version": report["schema_version"],
            "evaluator_sha256": evaluator_sha256,
            "config_sha256": config_sha256,
        },
        "required_dimensions": sorted(required_dimensions),
        "block_reasons": blocks,
        "unmeasured": [
            item for item in report["findings"] if item.get("status") == "NOT_CHECKED"
        ],
        "report": report,
    }


def run_provider(
    cleanup_root: Path,
    target: Path,
    mode: str,
    config: Path | None,
) -> tuple[dict[str, Any], str, str | None]:
    scripts = cleanup_root / "scripts"
    environment = {**os.environ, "PYTHONUTF8": "1"}
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
    errors = validate_report(report, target, mode)
    if errors:
        raise MeasurementError("; ".join(errors))

    provider_paths = [scripts / name for name in PROVIDER_FILES]
    evaluator_sha256 = digest_files(provider_paths, cleanup_root)
    loaded_config = report.get("config")
    config_sha256 = None
    if loaded_config:
        config_path = Path(str(loaded_config)).resolve()
        config_sha256 = digest_files([config_path], config_path.parent)
    return report, evaluator_sha256, config_sha256


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


def write_envelope(envelope: dict[str, Any], output: Path | None) -> None:
    payload = json.dumps(envelope, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)


def run_self_test() -> None:
    target = Path.cwd().resolve()
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
    baseline = build_envelope(base, target, "a" * 64, None, "baseline", {6})
    assert baseline["decision"] == "BASELINE_CAPTURED"
    promotion = build_envelope(base, target, "a" * 64, None, "promotion", {6})
    assert promotion["decision"] == "BLOCK"
    assert any("FAIL" in item for item in promotion["block_reasons"])
    assert any("NOT_CHECKED" in item for item in promotion["block_reasons"])
    mismatch = json.loads(json.dumps(base))
    mismatch["summary"]["review"] = 0
    assert any("summary.review mismatch" in item for item in validate_report(mismatch, target, "architecture"))
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", type=Path)
    parser.add_argument("--mode", choices=("a", "b", "architecture", "all"), default="architecture")
    parser.add_argument("--phase", choices=("baseline", "promotion"), default="baseline")
    parser.add_argument("--require-checked", type=parse_dimensions, default=set())
    parser.add_argument("--config", type=Path)
    parser.add_argument("--cleanup-root", type=Path)
    parser.add_argument("--output", type=Path)
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
    try:
        cleanup_root = resolve_cleanup_root(args.cleanup_root)
        report, evaluator_hash, config_hash = run_provider(
            cleanup_root, args.target, args.mode, args.config
        )
        envelope = build_envelope(
            report,
            cleanup_root,
            evaluator_hash,
            config_hash,
            args.phase,
            args.require_checked,
        )
    except (MeasurementError, OSError, UnicodeError) as exc:
        envelope = {
            "contract_version": CONTRACT_VERSION,
            "decision": "MEASUREMENT_BLOCK",
            "phase": args.phase,
            "errors": [str(exc)],
        }
        write_envelope(envelope, args.output)
        return 2
    write_envelope(envelope, args.output)
    return 1 if envelope["decision"] == "BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
