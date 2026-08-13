#!/usr/bin/env python3
"""Task-shaped positive and negative regression corpus for the R&D gates."""

from __future__ import annotations

import tempfile
from pathlib import Path

from run_cleanup_gate import build_envelope, resolve_cleanup_root, run_provider
from score_gate import evaluate


ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def cleanup_provider_corpus() -> None:
    cleanup_root = resolve_cleanup_root()
    report, evaluator_hash, config_hash = run_provider(
        cleanup_root, ROOT, "architecture", None
    )
    positive = build_envelope(
        report,
        cleanup_root,
        evaluator_hash,
        config_hash,
        "promotion",
        {10},
    )
    if positive["decision"] != "ALLOW":
        raise AssertionError(f"real R&D skill corpus should promote: {positive['block_reasons']}")

    with tempfile.TemporaryDirectory(prefix="rd-cleanup-negative-corpus-") as raw:
        target = Path(raw)
        write(target / "a.py", "from b import value\n")
        write(target / "b.py", "from a import value\nvalue = 1\n")
        broken, broken_hash, broken_config_hash = run_provider(
            cleanup_root, target, "architecture", None
        )
        negative = build_envelope(
            broken,
            cleanup_root,
            broken_hash,
            broken_config_hash,
            "promotion",
            {10},
        )
        if negative["decision"] != "BLOCK":
            raise AssertionError("dependency-cycle corpus must block promotion")


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


def main() -> int:
    cleanup_provider_corpus()
    score_gate_corpus()
    print("R&D gate regression corpus passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
