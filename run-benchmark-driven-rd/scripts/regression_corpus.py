#!/usr/bin/env python3
"""Task-shaped positive and negative regression corpus for the R&D gates."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from delivery_contract_gate import evaluate as evaluate_delivery_contract, fixture_document
from completion_closure_gate import evaluate as evaluate_completion, fixture_document as completion_fixture_document
from run_cleanup_gate import build_envelope, resolve_cleanup_root, run_provider
from score_gate import evaluate
from web_acceptance_gate import evaluate as evaluate_web_acceptance, fixture_document as web_fixture_document


ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def cleanup_provider_corpus() -> None:
    cleanup_root = resolve_cleanup_root()
    report, evaluator_hash, config_hash, provider_revision = run_provider(
        cleanup_root, ROOT, "architecture", None
    )
    positive = build_envelope(
        report,
        cleanup_root,
        evaluator_hash,
        config_hash,
        "promotion",
        {10},
        provider_revision=provider_revision,
    )
    if positive["decision"] != "ALLOW":
        raise AssertionError(f"real R&D skill corpus should promote: {positive['block_reasons']}")

    with tempfile.TemporaryDirectory(prefix="rd-cleanup-negative-corpus-") as raw:
        target = Path(raw)
        write(target / "a.py", "from b import value\n")
        write(target / "b.py", "from a import value\nvalue = 1\n")
        broken, broken_hash, broken_config_hash, broken_revision = run_provider(
            cleanup_root, target, "architecture", None
        )
        negative = build_envelope(
            broken,
            cleanup_root,
            broken_hash,
            broken_config_hash,
            "promotion",
            {10},
            provider_revision=broken_revision,
        )
        if negative["decision"] != "BLOCK":
            raise AssertionError("dependency-cycle corpus must block promotion")

    review_report = json.loads(json.dumps(report))
    review_report["findings"].append(
        {"dimension": 4, "status": "REVIEW", "code": "fixture-review"}
    )
    review_report["summary"]["review"] += 1
    strict = build_envelope(
        review_report,
        cleanup_root,
        evaluator_hash,
        config_hash,
        "promotion",
        {10},
        review_policy="block",
        provider_revision=provider_revision,
    )
    if strict["decision"] != "BLOCK":
        raise AssertionError("strict completion corpus must block unresolved REVIEW")


def cleanup_freshness_corpus() -> None:
    cleanup_root = resolve_cleanup_root()
    gate = Path(__file__).with_name("run_cleanup_gate.py")
    verifier = Path(__file__).with_name("verify_cleanup_evidence.py")
    environment = {**os.environ, "PYTHONUTF8": "1"}
    with tempfile.TemporaryDirectory(prefix="rd-cleanup-freshness-") as raw:
        target = Path(raw)
        write(target / "clean.py", "value = 1\n")
        unexcluded = target / "promotion.json"
        blocked = subprocess.run(
            [sys.executable, str(gate), str(target), "--phase", "promotion",
             "--cleanup-root", str(cleanup_root), "--output", str(unexcluded), "--quiet"],
            capture_output=True, text=True, encoding="utf-8", errors="strict",
            env=environment, check=False,
        )
        if blocked.returncode != 2:
            raise AssertionError("self-referential evidence output must measurement-block")
        blocked_document = json.loads(unexcluded.read_text(encoding="utf-8"))
        if blocked_document.get("decision") != "MEASUREMENT_BLOCK":
            raise AssertionError("self-referential output returned the wrong decision")

    with tempfile.TemporaryDirectory(prefix="rd-cleanup-freshness-") as raw:
        target = Path(raw)
        write(target / "clean.py", "value = 1\n")
        write(target / "audit.config.json", json.dumps({"exclude": [".rd/**"]}))
        evidence = target / ".rd" / "promotion.json"
        captured = subprocess.run(
            [sys.executable, str(gate), str(target), "--phase", "promotion",
             "--review-policy", "block", "--require-checked", "10",
             "--config", str(target / "audit.config.json"),
             "--cleanup-root", str(cleanup_root), "--output", str(evidence), "--quiet"],
            capture_output=True, text=True, encoding="utf-8", errors="strict",
            env=environment, check=False,
        )
        if captured.returncode != 0:
            raise AssertionError(f"excluded evidence corpus did not promote: {captured.stderr}")
        fresh = subprocess.run(
            [sys.executable, str(verifier), str(evidence)], capture_output=True, text=True,
            encoding="utf-8", errors="strict", env=environment, check=False,
        )
        if fresh.returncode != 0 or json.loads(fresh.stdout).get("status") != "FRESH":
            raise AssertionError("unchanged promotion evidence was not fresh")
        write(target / "clean.py", "value = 2\n")
        stale = subprocess.run(
            [sys.executable, str(verifier), str(evidence)], capture_output=True, text=True,
            encoding="utf-8", errors="strict", env=environment, check=False,
        )
        stale_document = json.loads(stale.stdout)
        if stale.returncode != 1 or stale_document.get("changes", {}).get("changed") != ["clean.py"]:
            raise AssertionError("post-promotion mutation was not rejected as stale")


def score_gate_corpus() -> None:
    dataset_hash = "sha256:" + "b" * 64
    protocol = {
        "runsPerScenario": 30,
        "metricVersion": "1.0.0",
        "stableFrames": 3,
        "acquireDeadlineMs": 350,
        "reacquireDeadlineMs": 450,
        "poseTolerancePx": 3,
    }
    baseline = {
        "status": "measured",
        "engine": {"device": "corpus-device"},
        "dataset": {"id": "frozen-corpus-v1", "hash": dataset_hash, "blinded": True},
        "protocol": protocol,
        "aggregate": {"quality": 0.80, "latency": 25.0},
    }
    candidate = {
        **baseline,
        "aggregate": {"quality": 0.88, "latency": 20.0},
    }
    config = {
        "requireBlinded": True,
        "requireSameDevice": True,
        "minRunsPerScenario": 30,
        "gates": [
            {"metric": "quality", "direction": "higher", "relativeImprovement": 0.05},
            {"metric": "latency", "direction": "lower", "relativeImprovement": 0.10},
        ],
    }
    if evaluate(candidate, baseline, config):
        raise AssertionError("positive score corpus should pass")
    broken = {
        **candidate,
        "dataset": {**candidate["dataset"], "hash": "sha256:" + "c" * 64},
    }
    failures = evaluate(broken, baseline, config)
    if not any("dataset hashes do not match" in item for item in failures):
        raise AssertionError("mismatched provenance corpus must fail")


def delivery_contract_corpus() -> None:
    with tempfile.TemporaryDirectory(prefix="rd-delivery-corpus-") as raw:
        root = Path(raw)
        positive = fixture_document(root)
        if evaluate_delivery_contract(positive, root)["status"] != "GREEN":
            raise AssertionError("complete actual-delivery corpus should promote")
        negative = dict(positive)
        negative["payload"] = {
            **positive["payload"],
            "closedWorld": {**positive["payload"]["closedWorld"], "unexpectedCount": 1},
        }
        report = evaluate_delivery_contract(negative, root)
        if not any(item["code"] == "payload-not-closed-world" for item in report["findings"]):
            raise AssertionError("orphan delivered payload must block promotion")


def completion_closure_corpus() -> None:
    with tempfile.TemporaryDirectory(prefix="rd-completion-corpus-") as raw:
        root = Path(raw)
        document = completion_fixture_document(root)
        adapters = {
            "cleanup_verifier": lambda _path: {"status": "FRESH"},
            "delivery_evaluator": lambda _doc, _root: {
                "status": "GREEN", "product": "Fixture", "productVersion": "1.0.0",
            },
            "capability_evaluator": lambda _doc, _root, _package, _scope: {"status": "GREEN"},
            "receipt_verifier": lambda _root, _receipt: {"status": "GREEN"},
        }
        if evaluate_completion(document, root, **adapters)["status"] != "GREEN":
            raise AssertionError("complete closure corpus should promote")
        stale = json.loads(json.dumps(document))
        artifact = next(item for item in stale["checks"] if item["id"] == "artifact")
        artifact["sha256"] = "0" * 64
        report = evaluate_completion(stale, root, **adapters)
        if not any(item["code"] == "stale-file-identity" for item in report["findings"]):
            raise AssertionError("stale handoff artifact must block completion")
        missing_update_floor = json.loads(json.dumps(document))
        capabilities = next(
            item for item in missing_update_floor["checks"] if item["id"] == "capabilities"
        )
        capabilities["requiredObligationIds"].append("update.missing")
        report = evaluate_completion(missing_update_floor, root, **adapters)
        if not any(
            item["code"] == "capability-obligation-floor"
            for item in report["findings"]
        ):
            raise AssertionError("missing route-required updater obligation must block completion")


def web_acceptance_corpus() -> None:
    with tempfile.TemporaryDirectory(prefix="rd-web-corpus-") as raw:
        root = Path(raw)
        positive = web_fixture_document(root)
        if evaluate_web_acceptance(positive, root)["status"] != "GREEN":
            raise AssertionError("live browser evidence corpus should promote")
        declared_only = json.loads(json.dumps(positive))
        declared_only["negativeControls"] = [item["id"] for item in positive["negativeControls"]]
        if evaluate_web_acceptance(declared_only, root)["status"] != "BLOCK":
            raise AssertionError("declared-only browser controls must not promote")
        stale = json.loads(json.dumps(positive))
        evidence = root / stale["collector"]["rawEvidence"]["path"]
        evidence.write_bytes(evidence.read_bytes() + b"tampered")
        if not any(item["code"] == "evidence-stale" for item in evaluate_web_acceptance(stale, root)["findings"]):
            raise AssertionError("stale raw browser evidence must block promotion")


def invocation_revision_corpus() -> None:
    gate = Path(__file__).with_name("invocation_revision_gate.py")
    environment = {**os.environ, "PYTHONUTF8": "1"}
    with tempfile.TemporaryDirectory(prefix="rd-invocation-corpus-") as raw:
        root = Path(raw)
        cleanup = root / "fixture-cleanup"
        research = root / "fixture-rd"
        for skill_root, name in ((cleanup, "fixture-cleanup"), (research, "fixture-rd")):
            write(skill_root / "SKILL.md", f"---\nname: {name}\n---\n")
            write(skill_root / "references" / "rules.md", "stable\n")
        evidence = root / "revision.json"
        capture = subprocess.run(
            [sys.executable, str(gate), "capture", "--skill-root", str(cleanup),
             "--skill-root", str(research), "--output", str(evidence), "--quiet"],
            capture_output=True, text=True, encoding="utf-8", errors="strict",
            env=environment, check=False,
        )
        if capture.returncode != 0 or not evidence.is_file():
            raise AssertionError(capture.stderr or capture.stdout or "revision corpus capture failed")
        current = subprocess.run(
            [sys.executable, str(gate), "verify", str(evidence)], capture_output=True,
            text=True, encoding="utf-8", errors="strict", env=environment, check=False,
        )
        if current.returncode != 0 or json.loads(current.stdout).get("status") != "CURRENT":
            raise AssertionError("unchanged multi-Skill corpus was not current")
        write(research / "references" / "rules.md", "landed update\n")
        stale = subprocess.run(
            [sys.executable, str(gate), "verify", str(evidence)], capture_output=True,
            text=True, encoding="utf-8", errors="strict", env=environment, check=False,
        )
        if stale.returncode != 1 or json.loads(stale.stdout).get("status") != "STALE":
            raise AssertionError("landed canonical update did not invalidate invocation evidence")
        write(research / "references" / "rules.md", "stable\n")
        write(research / ".skill-proposals" / "unfinished.md", "not landed\n")
        ignored = subprocess.run(
            [sys.executable, str(gate), "verify", str(evidence)], capture_output=True,
            text=True, encoding="utf-8", errors="strict", env=environment, check=False,
        )
        if ignored.returncode != 0 or json.loads(ignored.stdout).get("status") != "CURRENT":
            raise AssertionError("unfinished proposal incorrectly changed the canonical revision")


def main() -> int:
    invocation_revision_corpus()
    cleanup_provider_corpus()
    cleanup_freshness_corpus()
    score_gate_corpus()
    delivery_contract_corpus()
    completion_closure_corpus()
    web_acceptance_corpus()
    print("R&D gate regression corpus passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
