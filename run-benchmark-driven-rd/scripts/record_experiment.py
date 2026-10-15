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

def _unique_strings(values: Iterable[str], option: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            raise SystemExit(f"{option} values must be non-empty")
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _parse_metrics(value: str) -> dict[str, object]:
    try:
        metrics = json.loads(value)
    except json.JSONDecodeError as error:
        raise SystemExit(f"--metrics must be valid JSON: {error}") from error
    if not isinstance(metrics, dict):
        raise SystemExit("--metrics must be a JSON object")
    return metrics


def _identity(identity: str, digest: str | None, option: str) -> dict[str, str]:
    value = identity.strip()
    if not value:
        raise SystemExit(f"{option} must be non-empty")
    result = {"id": value}
    if digest:
        if not _SHA256.fullmatch(digest):
            raise SystemExit(f"{option}-sha256 must be exactly 64 hexadecimal characters")
        result["sha256"] = digest.lower()
    return result


def _expires_on(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise SystemExit("--expires-on must use YYYY-MM-DD") from error


def build_entry(args: argparse.Namespace, now: datetime | None = None) -> dict[str, object]:
    recorded_at = now or datetime.now(timezone.utc)
    fixture_ids = {
        "positive": _unique_strings(args.positive_fixture_id, "--positive-fixture-id"),
        "negative": _unique_strings(args.negative_fixture_id, "--negative-fixture-id"),
        "other": _unique_strings(args.fixture_id, "--fixture-id"),
    }
    entry: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "id": experiment_id(recorded_at),
        "recordedAt": recorded_at.isoformat(),
        "hypothesis": args.hypothesis,
        "change": args.change,
        "result": args.result,
        "evidence": args.evidence,
        "metrics": _parse_metrics(args.metrics),
        "learning": args.learning,
        "topic": args.topic,
        "scope": args.scope,
        "privacy": args.privacy,
        "applicability": _unique_strings(args.applicability, "--applicability"),
        "exclusions": _unique_strings(args.exclusion, "--exclusion"),
        "ruleIds": _unique_strings(args.rule_id, "--rule-id"),
        "fixtureIds": fixture_ids,
        "promotionState": args.promotion_state,
        "evidenceState": args.evidence_state,
        "expiresOn": _expires_on(args.expires_on),
        "nextDecision": args.next_decision,
        "environmentIdentity": _identity(
            args.environment_id, args.environment_sha256, "--environment-id"
        ),
        "datasetIdentity": _identity(args.dataset_id, args.dataset_sha256, "--dataset-id"),
    }
    if args.failure_type:
        entry["failureType"] = args.failure_type
    return entry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".")
    # These remain optional to argparse so --self-test can stand alone. main()
    # enforces the same required old CLI contract for normal writes.
    parser.add_argument("--hypothesis")
    parser.add_argument("--change")
    parser.add_argument("--result", choices=RESULTS)
    parser.add_argument("--evidence")
    parser.add_argument("--metrics", default="{}", help="JSON object")
    parser.add_argument("--learning")
    parser.add_argument("--failure-type", choices=FAILURE_TYPES)
    parser.add_argument("--topic", default="general")
    parser.add_argument("--scope", choices=SCOPES, default="project-local")
    parser.add_argument("--privacy", choices=PRIVACY_LEVELS, default="private")
    parser.add_argument("--applicability", action="append", default=[])
    parser.add_argument("--exclusion", action="append", default=[])
    parser.add_argument("--rule-id", action="append", default=[])
    parser.add_argument("--fixture-id", action="append", default=[])
    parser.add_argument("--positive-fixture-id", action="append", default=[])
    parser.add_argument("--negative-fixture-id", action="append", default=[])
    parser.add_argument("--promotion-state", choices=PROMOTION_STATES, default="raw")
    parser.add_argument("--evidence-state", choices=EVIDENCE_STATES, default="diagnostic")
    parser.add_argument("--expires-on")
    parser.add_argument("--next-decision", default="review")
    parser.add_argument("--environment-id", default="unmeasured")
    parser.add_argument("--environment-sha256")
    parser.add_argument("--dataset-id", default="unmeasured")
    parser.add_argument("--dataset-sha256")
    parser.add_argument("--lock-timeout", type=float, default=DEFAULT_LOCK_TIMEOUT_SECONDS)
    parser.add_argument("--self-test", action="store_true")
    return parser


def _require_old_cli_fields(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    missing = [
        name
        for name in ("hypothesis", "change", "result", "evidence", "learning")
        if not getattr(args, name)
    ]
    if missing:
        options = ", ".join(f"--{name.replace('_', '-')}" for name in missing)
        parser.error("the following arguments are required: " + options)

def run_self_test() -> None:
    from record_experiment_selftest import run_self_test as replay
    replay()

def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        print("record_experiment self-test passed (32 concurrent writers)")
        return 0
    _require_old_cli_fields(parser, args)
    entry = build_entry(args)
    append_entry(args.project, entry, lock_timeout=args.lock_timeout)
    print(entry["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
