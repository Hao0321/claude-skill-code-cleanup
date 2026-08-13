#!/usr/bin/env python3
"""Compare candidate and baseline aggregate metrics using a JSON gate config."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def load(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def evaluate(candidate: dict, baseline: dict, config: dict) -> list[str]:
    failures: list[str] = []
    if candidate.get("status") != "measured" or baseline.get("status") != "measured":
        failures.append("candidate and baseline must both have status=measured")
    if config.get("requireBlinded", True) and not candidate.get("dataset", {}).get("blinded"):
        failures.append("candidate dataset must be blinded")
    if candidate.get("dataset", {}).get("hash") != baseline.get("dataset", {}).get("hash"):
        failures.append("dataset hashes do not match")
    dataset_hash = str(candidate.get("dataset", {}).get("hash", ""))
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", dataset_hash):
        failures.append("dataset hash must be a frozen SHA-256 digest")
    if candidate.get("dataset", {}).get("id") != baseline.get("dataset", {}).get("id"):
        failures.append("dataset IDs do not match")
    if config.get("requireSameDevice", True):
        candidate_device = candidate.get("engine", {}).get("device")
        baseline_device = baseline.get("engine", {}).get("device")
        if not candidate_device or not baseline_device:
            failures.append("candidate and baseline device IDs are required")
        elif candidate_device != baseline_device:
            failures.append("candidate and baseline device IDs do not match")
    minimum = int(config.get("minRunsPerScenario", 1))
    if int(candidate.get("protocol", {}).get("runsPerScenario", 0)) < minimum:
        failures.append(f"candidate runsPerScenario is below {minimum}")
    for key in ("metricVersion", "stableFrames", "acquireDeadlineMs", "reacquireDeadlineMs", "poseTolerancePx"):
        candidate_value = candidate.get("protocol", {}).get(key)
        baseline_value = baseline.get("protocol", {}).get(key)
        if candidate_value is None or baseline_value is None:
            failures.append(f"protocol field is required: {key}")
        elif candidate_value != baseline_value:
            failures.append(f"protocol field does not match: {key}")
    c_metrics = candidate.get("aggregate", {})
    b_metrics = baseline.get("aggregate", {})
    for gate in config.get("gates", []):
        metric = gate["metric"]
        if metric not in c_metrics or metric not in b_metrics:
            failures.append(f"missing metric: {metric}")
            continue
        c_value = float(c_metrics[metric])
        b_value = float(b_metrics[metric])
        improvement = float(gate.get("relativeImprovement", 0))
        if gate["direction"] == "higher":
            threshold = max(float(gate.get("absoluteFloor", float("-inf"))), b_value * (1 + improvement))
            if c_value < threshold:
                failures.append(f"{metric}: {c_value} < required {threshold}")
        elif gate["direction"] == "lower":
            threshold = min(float(gate.get("absoluteCeiling", float("inf"))), b_value * (1 - improvement))
            if c_value > threshold:
                failures.append(f"{metric}: {c_value} > required {threshold}")
        else:
            failures.append(f"{metric}: invalid direction")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", nargs="?")
    parser.add_argument("baseline", nargs="?")
    parser.add_argument("config", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        dataset_hash = "sha256:" + "a" * 64
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
            "engine": {"device": "fixture"},
            "dataset": {"id": "holdout-v1", "hash": dataset_hash, "blinded": True},
            "protocol": protocol,
            "aggregate": {"recall": 0.9, "latency": 20},
        }
        candidate = {
            **baseline,
            "aggregate": {"recall": 0.94, "latency": 17},
        }
        config = {
            "requireBlinded": True,
            "requireSameDevice": True,
            "minRunsPerScenario": 30,
            "gates": [
                {"metric": "recall", "direction": "higher", "relativeImprovement": 0.02, "absoluteFloor": 0.9},
                {"metric": "latency", "direction": "lower", "relativeImprovement": 0.1, "absoluteCeiling": 18},
            ],
        }
        if evaluate(candidate, baseline, config):
            raise AssertionError("expected passing fixture")
        candidate["aggregate"]["recall"] = 0.89
        if not evaluate(candidate, baseline, config):
            raise AssertionError("expected failing fixture")
        print("score_gate self-test: PASS")
        return 0
    if not args.candidate or not args.baseline or not args.config:
        parser.error("candidate, baseline, and config are required unless --self-test is used")
    failures = evaluate(load(args.candidate), load(args.baseline), load(args.config))
    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
