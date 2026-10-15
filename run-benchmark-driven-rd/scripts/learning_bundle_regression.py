"""Bounded-source and isolated-calibration provenance controls."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import os
import tempfile
from unittest.mock import patch
from learning_bundle_replay import MAX_SOURCES, isolated_replay, read_document, source_rows, validate_replay


def rejected(action) -> None:
    try:
        action()
    except (ValueError, KeyError, TypeError):
        return
    raise AssertionError("malformed learning bundle or replay identity was accepted")


def source_controls() -> None:
    row = {"path": "profiles/owned.json", "id": "owned-record", "sha256": "a" * 64}
    assert source_rows({"experimentRecordSources": [row]}) == [row]
    invalids = [None, [], [None], [{**row, "sha256": "x"}], [{**row, "id": True}],
                [row, row], [row, {**row, "id": "different", "path": row["path"].upper()}],
                [row] * (MAX_SOURCES + 1), [{**row, "path": "../escape.json"}]]
    for value in invalids:
        rejected(lambda: source_rows({"experimentRecordSources": value}))
    with tempfile.TemporaryDirectory(prefix="rd-bundle-documents-") as raw:
        path = Path(raw) / "owned.json"
        path.write_bytes(b'{"id":"first","id":"shadow"}')
        rejected(lambda: read_document(path, 100))
        path.write_bytes(b" " * 101)
        rejected(lambda: read_document(path, 100))
        path.write_bytes(b"[]")
        rejected(lambda: read_document(path, 100))


def replay_controls(cleanup: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="rd-poisoned-pythonpath-") as raw:
        root = Path(raw)
        (root / "exposure_regression.py").write_text("raise RuntimeError('foreign provider imported')\n", encoding="utf-8")
        with patch.dict(os.environ, {"PYTHONPATH": str(root), "PYTHONOPTIMIZE": "2"}):
            report = isolated_replay(cleanup)
    entry = hashlib.sha256((cleanup / "scripts/replay_exposure.py").read_bytes()).hexdigest()
    validate_replay(report, cleanup, entry)
    for kind in ("membership", "source-digest", "aggregate", "runtime", "entry-drift"):
        changed = copy.deepcopy(report)
        expected_entry = entry
        if kind == "membership":
            changed["codeIdentity"]["files"].pop()
        elif kind == "source-digest":
            changed["codeIdentity"]["files"][0]["sha256"] = "0" * 64
            changed["codeIdentity"]["sha256"] = hashlib.sha256(json.dumps(
                changed["codeIdentity"]["files"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        elif kind == "aggregate":
            changed["codeIdentity"]["sha256"] = "0" * 64
        elif kind == "runtime":
            changed["environment"]["executableSha256"] = "0" * 64
        else:
            expected_entry = "0" * 64
        rejected(lambda: validate_replay(changed, cleanup, expected_entry))


def run_self_test(cleanup: Path) -> None:
    source_controls()
    replay_controls(cleanup)
