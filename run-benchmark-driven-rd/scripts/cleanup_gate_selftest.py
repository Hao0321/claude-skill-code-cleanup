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


def _test_strict_review_policy(base, target):
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


def run_self_test(api) -> None:
    globals().update({name: getattr(api, name) for name in ('resolve_cleanup_root', 'resolve_active_cleanup_root', 'capture_skill_revision', 'validate_skill_revision_snapshot', 'validate_report', 'build_envelope', 'run_snapshot_checker', 'parse_single_json', 'write_envelope', 'preflight_config_scope', 'validate_config_scope')})
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
    _test_strict_review_policy(base, target)
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
