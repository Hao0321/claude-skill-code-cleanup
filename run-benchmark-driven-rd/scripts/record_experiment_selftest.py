#!/usr/bin/env python3
"""Write one immutable R&D experiment record and rebuild its JSONL view."""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from contextlib import AbstractContextManager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterable
from uuid import uuid4


SCHEMA_VERSION = 2
DEFAULT_LOCK_TIMEOUT_SECONDS = 30.0
from record_experiment_store import (
    SCHEMA_VERSION,
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    LEDGER_REPLACE_TIMEOUT_SECONDS,
    RESULTS,
    FAILURE_TYPES,
    PROMOTION_STATES,
    EVIDENCE_STATES,
    SCOPES,
    PRIVACY_LEVELS,
    _RECORD_ID,
    _SHA256,
    _windows_sharing_error,
    LedgerLockTimeout,
    LedgerLock,
    experiment_id,
    experiments_dir,
    records_dir,
    ledger_path,
    ledger_lock_path,
    _validate_record_id,
    _json_bytes,
    _fsync_directory,
    _publish_record_exclusive,
    _read_json_object,
    load_records,
    _migrate_legacy_view,
    _atomic_write_ledger,
    _replace_ledger_view,
    append_entry,
    rebuild_ledger,
)

def _test_legacy_compatibility() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        # Preserve the old direct-Python API and prove the JSONL file is a view.
        entries = [{"id": "exp-one"}, {"id": "exp-two"}]
        for entry in entries:
            path = append_entry(temp_dir, entry)
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert rows == entries
        assert len(list(records_dir(temp_dir).glob("*.json"))) == 2
        try:
            append_entry(temp_dir, {"id": "exp-one"})
        except FileExistsError:
            pass
        else:
            raise AssertionError("immutable experiment id was overwritten")
        assert [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] == entries

    with tempfile.TemporaryDirectory() as temp_dir:
        # A first v2 writer must migrate, not forget, the pre-v2 JSONL authority.
        old = {"id": "exp-legacy", "learning": "preserve me"}
        old_path = ledger_path(temp_dir)
        old_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.write_bytes(_json_bytes(old))
        append_entry(temp_dir, {"id": "exp-current"})
        migrated = [json.loads(line) for line in old_path.read_text(encoding="utf-8").splitlines()]
        assert migrated == [{"id": "exp-current"}, old]
        assert len(list(records_dir(temp_dir).glob("*.json"))) == 2


def _writer_command(temp_dir: str, index: int) -> list[str]:
    return [
        sys.executable,
        "-X",
        "utf8",
        str(Path(__file__).with_name('record_experiment.py').resolve()),
        "--project",
        temp_dir,
        "--hypothesis",
        f"writer-{index}",
        "--change",
        "old-cli-compatible",
        "--result",
        "pass",
        "--evidence",
        f"evidence-{index}.json",
        "--learning",
        f"learning-{index}",
    ]


def _test_concurrent_writers() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        processes: list[subprocess.Popen[str]] = []
        for index in range(32):
            processes.append(
                subprocess.Popen(
                    _writer_command(temp_dir, index),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
            )
        deadline = time.monotonic() + 60.0
        failures: list[str] = []
        snapshots = 0
        try:
            while any(process.poll() is None for process in processes):
                live_view = ledger_path(temp_dir)
                if live_view.exists():
                    try:
                        live_text = live_view.read_text(encoding="utf-8")
                    except OSError as error:
                        if _windows_sharing_error(error):
                            if time.monotonic() >= deadline:
                                raise TimeoutError("reader sharing retry exceeded 60 seconds") from error
                            time.sleep(0.002)
                            continue
                        raise
                    live_rows = [json.loads(line) for line in live_text.splitlines() if line.strip()]
                    live_ids = [row["id"] for row in live_rows]
                    assert len(live_ids) == len(set(live_ids))
                    snapshots += 1
                if time.monotonic() >= deadline:
                    raise TimeoutError("32-writer fixture exceeded 60 seconds")
                time.sleep(0.002)
            for process in processes:
                remaining = max(0.1, deadline - time.monotonic())
                stdout, stderr = process.communicate(timeout=remaining)
                if process.returncode != 0:
                    failures.append(f"exit={process.returncode} stdout={stdout!r} stderr={stderr!r}")
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        assert not failures, failures

        canonical = load_records(temp_dir)
        ledger_rows = [
            json.loads(line)
            for line in ledger_path(temp_dir).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        record_ids = [str(row["id"]) for row in canonical]
        required_v2_fields = {
            "schemaVersion",
            "topic",
            "scope",
            "privacy",
            "applicability",
            "exclusions",
            "ruleIds",
            "fixtureIds",
            "promotionState",
            "evidenceState",
            "expiresOn",
            "nextDecision",
            "environmentIdentity",
            "datasetIdentity",
        }
        assert len(canonical) == 32
        assert snapshots > 0
        assert len(set(record_ids)) == 32
        assert ledger_rows == canonical
        assert all(row.get("schemaVersion") == SCHEMA_VERSION for row in canonical)
        assert all(required_v2_fields.issubset(row) for row in canonical)
        assert {"target-resolution", "authorization"}.issubset(FAILURE_TYPES)
        assert not list(records_dir(temp_dir).glob(".*.tmp"))


def run_self_test() -> None:
    fixed = datetime(2026, 8, 13, 3, 5, 59, 123456, tzinfo=timezone.utc)
    assert experiment_id(fixed, "first") != experiment_id(fixed, "second")
    _test_legacy_compatibility()
    _test_concurrent_writers()
