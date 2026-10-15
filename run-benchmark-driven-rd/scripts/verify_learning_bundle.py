#!/usr/bin/env python3
"""Replay the bundled sanitized learning record without importing private histories."""
from __future__ import annotations
import hashlib
import copy
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
from learning_gate import validate_learning
from record_experiment import append_entry
from run_cleanup_gate import resolve_cleanup_root


ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict:
    index_path = ROOT / "topic-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    sources = index.get("experimentRecordSources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("sanitized learning record sources are missing")
    cleanup = resolve_cleanup_root()
    sys.path.insert(0, str(cleanup / "scripts"))
    import exposure_regression
    from sync_safety import safe_path
    if Path(exposure_regression.__file__).resolve() != (cleanup / "scripts/exposure_regression.py").resolve():
        raise ValueError("learning replay provider differs from the active provider")
    replay = exposure_regression.run_self_test()
    replay_hash = hashlib.sha256(Path(exposure_regression.__file__).read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="rd-shared-learning-") as raw:
        project = Path(raw)
        for row in sources:
            relative = PurePosixPath(row["path"])
            if relative.is_absolute() or ".." in relative.parts or "\\" in row["path"]:
                raise ValueError("unsafe learning record source")
            path = safe_path(ROOT, row["path"])
            if path.is_symlink() or path.stat().st_size > 100_000:
                raise ValueError("learning record source exceeds bounds")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError("sanitized learning record identity drifted")
            record = json.loads(data.decode("utf-8"))
            if record["id"] != row["id"] or record["datasetIdentity"]["sha256"] != replay_hash:
                raise ValueError("learning record differs from current replay")
            if record["fixtureIds"]["positive"] != replay["positiveFixtureIds"] or record["fixtureIds"]["negative"] != replay["negativeFixtureIds"]:
                raise ValueError("learning fixture ledger differs from executed controls")
            append_entry(project, record)
        report = validate_learning(project, index_path, topic_root=ROOT.parent)
    return {"status": report["status"], "counts": report["counts"], "errors": report["errors"],
            "replay": replay, "scope": "bundled sanitized records only; historical project claims are not replayed"}


def run_self_test() -> None:
    global ROOT
    original = ROOT
    assert verify()["status"] == "PASS", "bundled learning is not replayable"
    source_index = json.loads((original / "topic-index.json").read_text(encoding="utf-8"))
    row = source_index["experimentRecordSources"][0]
    record = json.loads((original / row["path"]).read_text(encoding="utf-8"))
    try:
        with tempfile.TemporaryDirectory(prefix="rd-learning-negatives-") as raw:
            ROOT = Path(raw)
            (ROOT / "profiles").mkdir()
            for mutation in ("traversal", "hash", "identity", "fixture-ledger"):
                index, changed = copy.deepcopy(source_index), copy.deepcopy(record)
                current = index["experimentRecordSources"][0]
                if mutation == "traversal":
                    current["path"] = "../outside.json"
                elif mutation == "hash":
                    current["sha256"] = "0" * 64
                elif mutation == "identity":
                    current["id"] = "different-record"
                else:
                    changed["fixtureIds"]["negative"] = []
                data = (json.dumps(changed, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                (ROOT / row["path"]).write_bytes(data)
                if mutation != "hash":
                    current["sha256"] = hashlib.sha256(data).hexdigest()
                (ROOT / "topic-index.json").write_text(json.dumps(index), encoding="utf-8")
                try:
                    verify()
                except ValueError:
                    pass
                else:
                    raise AssertionError("learning bundle accepted " + mutation)
    finally:
        ROOT = original


def main() -> int:
    try:
        report = verify()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report = {"status": "BLOCK", "error": type(exc).__name__}
    sys.stdout.buffer.write((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
