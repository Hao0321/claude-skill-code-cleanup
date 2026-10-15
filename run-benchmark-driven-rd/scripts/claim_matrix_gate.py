#!/usr/bin/env python3
"""Validate cross-system workflow closure and market-comparison claim matrices."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


CLAIM_STATUSES = {"verified", "unmeasured"}
STAGE_STATUSES = {"verified", "unmeasured", "blocked_external"}
CELL_STATUSES = {"measured", "diagnostic", "unmeasured"}
PRIVATE_PATTERN = re.compile(r"(?:[a-z]:\\|\\\\|/Users/|/home/|\.claude[\\/]skills|\.codex[\\/]skills)", re.IGNORECASE)


def _safe_file(root: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    relative = PurePosixPath(value)
    if relative.is_absolute() or value != relative.as_posix() or ".." in relative.parts or (relative.parts and ":" in relative.parts[0]):
        return None
    candidate = root.joinpath(*relative.parts).resolve()
    return candidate if candidate == root or root in candidate.parents else None


def _evidence_ok(root: Path, evidence: Any) -> bool:
    if not isinstance(evidence, list) or not evidence:
        return False
    for item in evidence:
        if not isinstance(item, dict) or item.get("kind") != "file":
            return False
        candidate = _safe_file(root, item.get("value"))
        if candidate is None or not candidate.is_file():
            return False
        expected = item.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected, re.IGNORECASE):
            return False
        try:
            digest = hashlib.sha256()
            with candidate.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest().lower() != expected.lower():
                return False
        except OSError:
            return False
    return True


def _closed_world(required: Any, rows: Any, label: str, fail) -> dict[str, dict[str, Any]]:
    if not isinstance(required, list) or not required or any(not isinstance(item, str) or not item for item in required):
        fail(f"{label}-required", f"required {label} IDs must be a non-empty string array")
        required = []
    if len(set(required)) != len(required):
        fail(f"{label}-required-duplicate", f"required {label} IDs contain duplicates")
    if not isinstance(rows, list):
        fail(f"{label}-rows", f"{label} rows must be an array")
        rows = []
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = row.get("id") if isinstance(row, dict) else None
        if not isinstance(row_id, str) or not row_id:
            fail(f"{label}-id", f"{label} row is missing id")
            continue
        if row_id in by_id:
            fail(f"{label}-duplicate", f"duplicate {label} id: {row_id}")
        by_id[row_id] = row
    missing = sorted(set(required) - set(by_id))
    extra = sorted(set(by_id) - set(required))
    if missing:
        fail(f"{label}-missing", f"missing {label}: {missing}")
    if extra:
        fail(f"{label}-extra", f"undeclared {label}: {extra}")
    return by_id


def _validate_sources(document: dict[str, Any], fail) -> dict[str, dict[str, Any]]:
    sources = _closed_world(document.get("requiredSourceIds"), document.get("sources"), "source", fail)
    for source_id, source in sources.items():
        revision = source.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, (str, int)) or str(revision).strip() == "":
            fail("source-revision", f"source {source_id} lacks revision")
        if not isinstance(source.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"], re.IGNORECASE):
            fail("source-sha256", f"source {source_id} lacks sha256")
    return sources


def _validate_flows(document: dict[str, Any], root: Path, fail) -> tuple[dict[str, dict[str, Any]], list[str]]:
    flows = _closed_world(document.get("requiredFlowIds"), document.get("flows"), "flow", fail)
    open_stages: list[str] = []
    for flow_id, flow in flows.items():
        stages = _closed_world(flow.get("requiredStageIds"), flow.get("stages"), f"stage-{flow_id}", fail)
        for stage_id, stage in stages.items():
            status = stage.get("status")
            if not isinstance(status, str) or status not in STAGE_STATUSES:
                fail("stage-status", f"{flow_id}/{stage_id} has invalid status")
            elif status == "verified":
                if not _evidence_ok(root, stage.get("evidence")):
                    fail("stage-evidence", f"{flow_id}/{stage_id} lacks replayable file evidence")
            elif status == "unmeasured":
                if not isinstance(stage.get("nextExperiment"), str) or not stage["nextExperiment"].strip():
                    fail("stage-next-experiment", f"{flow_id}/{stage_id} lacks nextExperiment")
                open_stages.append(f"{flow_id}/{stage_id}")
            else:
                blocker = stage.get("blocker") if isinstance(stage.get("blocker"), dict) else {}
                if any(not isinstance(blocker.get(key), str) or not blocker[key].strip() for key in ("owner", "condition", "action")):
                    fail("stage-blocker", f"{flow_id}/{stage_id} has an incomplete blocker")
                open_stages.append(f"{flow_id}/{stage_id}")
    return flows, open_stages


def _validate_adapter_contract(document: dict[str, Any], flows: dict[str, dict[str, Any]], fail) -> None:
    adapter = document.get("adapterContract")
    if adapter is None:
        return
    if not isinstance(adapter, dict):
        fail("adapter-contract", "adapterContract must be an object")
        return
    current = adapter.get("currentSchema")
    legacy = adapter.get("legacySchemas")
    required = adapter.get("requiredCurrentFlowIds")
    if not isinstance(current, str) or not current.strip():
        fail("adapter-current-schema", "adapterContract.currentSchema must be non-empty")
        return
    if not isinstance(legacy, list) or any(not isinstance(item, str) or not item for item in legacy) or len(set(legacy)) != len(legacy):
        fail("adapter-legacy-schemas", "adapterContract.legacySchemas must be a unique string array")
        legacy = []
    if current in legacy:
        fail("adapter-schema-overlap", "currentSchema cannot also be legacy")
    if not isinstance(required, list) or not required or any(not isinstance(item, str) or not item for item in required) or len(set(required)) != len(required):
        fail("adapter-current-flows", "requiredCurrentFlowIds must be unique and non-empty")
        required = []
    for flow_id in required:
        flow = flows.get(flow_id)
        if flow is None:
            fail("adapter-unknown-flow", f"adapter current flow is undeclared: {flow_id}")
            continue
        schema = flow.get("contractSchema")
        if not isinstance(schema, str):
            fail("adapter-flow-schema", f"{flow_id} must use current schema {current}")
        elif schema in legacy:
            fail("adapter-legacy-flow", f"{flow_id} uses legacy schema {schema}; compatibility cannot close current integration")
        elif schema != current:
            fail("adapter-flow-schema", f"{flow_id} must use current schema {current}")


def _comparison_axis(comparison: dict[str, Any], key: str, code: str, fail) -> list[str]:
    values = comparison.get(key)
    if not isinstance(values, list) or not values or any(not isinstance(item, str) or not item for item in values) or len(set(values)) != len(values):
        fail(code, f"{key} must be unique and non-empty")
        return []
    return values


def _comparison_rows(comparison: dict[str, Any], fail) -> dict[tuple[Any, Any], dict[str, Any]]:
    rows = comparison.get("results") if isinstance(comparison.get("results"), list) else []
    by_cell: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or any(not isinstance(row.get(field), str) or not row[field] for field in ("baselineId", "surfaceId")):
            fail("comparison-cell-id", "comparison cell requires string baselineId and surfaceId")
            continue
        key = (row["baselineId"], row["surfaceId"])
        if key in by_cell:
            fail("comparison-duplicate-cell", f"duplicate comparison cell: {key}")
        by_cell[key] = row
    return by_cell


def _measured_cell_valid(row: dict[str, Any], key: tuple[str, str], root: Path, fail) -> bool:
    provenance = row.get("independentGroundTruth") is True and isinstance(row.get("datasetId"), str) and bool(row["datasetId"].strip())
    samples = type(row.get("sampleCount")) is int and row["sampleCount"] >= 1
    if not provenance or not samples:
        fail("comparison-provenance", f"{key} lacks independent truth, dataset or samples")
        return False
    if not _evidence_ok(root, row.get("evidence")):
        fail("comparison-evidence", f"{key} lacks replayable evidence")
        return False
    return True


def _validate_comparison(document: dict[str, Any], root: Path, fail) -> tuple[int, int, list[str]]:
    comparison = document.get("comparison")
    if comparison is None:
        return 0, 0, []
    if not isinstance(comparison, dict):
        fail("comparison", "comparison must be an object")
        return 0, 0, []
    baseline_ids = _comparison_axis(comparison, "requiredBaselineIds", "comparison-baselines", fail)
    surface_ids = _comparison_axis(comparison, "requiredSurfaceIds", "comparison-surfaces", fail)
    expected = {(baseline, surface) for baseline in baseline_ids for surface in surface_ids}
    by_cell = _comparison_rows(comparison, fail)
    extra = sorted(set(by_cell) - expected)
    if extra:
        fail("comparison-extra-cell", f"undeclared comparison cells: {extra}")
    open_cells: list[str] = []
    measured_cells = 0
    for key in sorted(expected):
        row = by_cell.get(key)
        status = row.get("status") if row is not None else None
        if row is None or (isinstance(status, str) and status in {"diagnostic", "unmeasured"}):
            open_cells.append(f"{key[0]}:{key[1]}")
        elif not isinstance(status, str) or status not in CELL_STATUSES:
            fail("comparison-cell-status", f"{key} has invalid status")
        elif _measured_cell_valid(row, key, root, fail):
            measured_cells += 1
    return len(expected), measured_cells, open_cells


def evaluate(document: dict[str, Any], root: Path) -> dict[str, Any]:
    findings: list[dict[str, str]] = []

    def fail(code: str, message: str) -> None:
        findings.append({"status": "FAIL", "code": code, "message": message})

    root = root.resolve()
    if not isinstance(document, dict):
        fail("invalid-document", "claim contract must be a JSON object")
        document = {}
    if type(document.get("schemaVersion")) is not int or document.get("schemaVersion") != 1:
        fail("schema-version", "schemaVersion must be 1")
    claim_status = document.get("claimStatus")
    if not isinstance(claim_status, str) or claim_status not in CLAIM_STATUSES:
        fail("claim-status", "claimStatus must be verified or unmeasured")
    if PRIVATE_PATTERN.search(json.dumps(document, ensure_ascii=False)):
        fail("private-data", "contract contains a private absolute or Skill path")
    sources = _validate_sources(document, fail)
    flows, open_stages = _validate_flows(document, root, fail)
    _validate_adapter_contract(document, flows, fail)
    total_cells, measured_cells, open_cells = _validate_comparison(document, root, fail)

    claim_closed = not open_stages and not open_cells and not findings
    if claim_status == "verified" and not claim_closed:
        fail("false-verified-claim", "claimStatus is verified while required workflow stages or comparison cells remain open")
        claim_closed = False
    if claim_status == "unmeasured" and (not isinstance(document.get("nextExperiment"), str) or not document["nextExperiment"].strip()):
        fail("claim-next-experiment", "unmeasured claim needs nextExperiment")

    return {
        "schemaVersion": 1,
        "instrumentStatus": "BLOCK" if findings else "GREEN",
        "claimStatus": claim_status,
        "claimClosure": "GREEN" if claim_closed else "BLOCK",
        "sources": len(sources),
        "flows": len(flows),
        "openStages": open_stages,
        "comparisonCells": total_cells,
        "measuredCells": measured_cells,
        "openCells": open_cells,
        "findings": findings or [{"status": "PASS", "code": "honest-claim-contract", "message": "instrument and claim state agree"}],
    }


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="claim-matrix-") as raw:
        root = Path(raw)
        proof = root / "proof.json"
        proof.write_text("{}", encoding="utf-8")
        evidence = [{"kind": "file", "value": "proof.json", "sha256": hashlib.sha256(proof.read_bytes()).hexdigest()}]
        document = {
            "schemaVersion": 1,
            "claimId": "fixture",
            "claimStatus": "verified",
            "requiredSourceIds": ["planner", "executor"],
            "sources": [
                {"id": "planner", "revision": 4, "sha256": "a" * 64},
                {"id": "executor", "revision": "1.0.0", "sha256": "b" * 64},
            ],
            "requiredFlowIds": ["shorts"],
            "flows": [{
                "id": "shorts", "requiredStageIds": ["plan", "execute", "review"],
                "contractSchema": "fixture.plan/v2",
                "stages": [
                    {"id": "plan", "status": "verified", "evidence": evidence},
                    {"id": "execute", "status": "verified", "evidence": evidence},
                    {"id": "review", "status": "verified", "evidence": evidence},
                ],
            }],
            "adapterContract": {
                "currentSchema": "fixture.plan/v2",
                "legacySchemas": ["fixture.plan/v1"],
                "requiredCurrentFlowIds": ["shorts"],
            },
            "comparison": {
                "requiredBaselineIds": ["baseline"], "requiredSurfaceIds": ["quality"],
                "results": [{"baselineId": "baseline", "surfaceId": "quality", "status": "measured", "independentGroundTruth": True, "datasetId": "holdout-v1", "sampleCount": 3, "evidence": evidence}],
            },
        }
        assert evaluate(document, root)["claimClosure"] == "GREEN"
        mutations = [
            lambda d: d.update(schemaVersion=True),
            lambda d: d.update(schemaVersion=1.0),
            lambda d: d.update(claimStatus=[]),
            lambda d: d["sources"][0].update(revision=True),
            lambda d: d["comparison"]["results"][0].update(sampleCount=True),
            lambda d: d["comparison"]["results"][0].update(baselineId=[]),
            lambda d: d["comparison"]["results"][0].update(status=[]),
            lambda d: d["flows"][0]["stages"][0].update(status=[]),
            lambda d: d["flows"][0]["stages"][0].update(evidence=[{"kind":"file","value":"proof.json"}]),
            lambda d: d["flows"][0]["stages"][0].update(evidence=[{"kind":"file","value":"proof.json","sha256":"0"*64}]),
        ]
        for mutate in mutations:
            invalid = json.loads(json.dumps(document)); mutate(invalid)
            assert evaluate(invalid, root)["instrumentStatus"] == "BLOCK"
        assert evaluate([], root)["instrumentStatus"] == "BLOCK"
        honest_open = json.loads(json.dumps(document))
        honest_open["claimStatus"] = "unmeasured"
        honest_open["nextExperiment"] = "run the missing cell"
        honest_open["comparison"]["results"] = []
        report = evaluate(honest_open, root)
        assert report["instrumentStatus"] == "GREEN" and report["claimClosure"] == "BLOCK"
        false_claim = json.loads(json.dumps(honest_open))
        false_claim["claimStatus"] = "verified"
        report = evaluate(false_claim, root)
        assert report["instrumentStatus"] == "BLOCK" and any(item["code"] == "false-verified-claim" for item in report["findings"])
        candidate_truth = json.loads(json.dumps(document))
        candidate_truth["comparison"]["results"][0]["independentGroundTruth"] = False
        report = evaluate(candidate_truth, root)
        assert any(item["code"] == "comparison-provenance" for item in report["findings"])
        legacy_flow = json.loads(json.dumps(document))
        legacy_flow["flows"][0]["contractSchema"] = "fixture.plan/v1"
        report = evaluate(legacy_flow, root)
        assert any(item["code"] == "adapter-legacy-flow" for item in report["findings"])


def load_document(path: Path) -> Any:
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    with path.open("rb") as handle:
        payload = handle.read(8 * 1024 * 1024 + 1)
    if len(payload) > 8 * 1024 * 1024:
        raise ValueError("claim metadata exceeds 8 MiB")
    return json.loads(payload.decode("utf-8-sig"), object_pairs_hook=unique_keys,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON value: {value}")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", nargs="?")
    parser.add_argument("--root")
    parser.add_argument("--output")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--require-claim-closed", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        print("claim matrix gate self-test passed")
        return 0
    if not args.contract:
        parser.error("contract is required unless --self-test is used")
    contract_path = Path(args.contract).resolve()
    root = Path(args.root).resolve() if args.root else contract_path.parent
    try:
        report = evaluate(load_document(contract_path), root)
    except (OSError, ValueError, UnicodeError) as error:
        report = evaluate({}, root)
        report["findings"].append({"status":"FAIL", "code":"invalid-contract-json", "message":str(error)})
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).resolve().write_text(payload, encoding="utf-8")
    if not args.quiet:
        print(payload, end="")
    if report["instrumentStatus"] != "GREEN" or (args.require_claim_closed and report["claimClosure"] != "GREEN"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
