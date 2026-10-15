#!/usr/bin/env python3
"""Validate shared learning topics and evidence-backed promotion receipts."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import os
import re
import tempfile
from collections import defaultdict
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable
from uuid import uuid4

from record_experiment import (
    FAILURE_TYPES,
    LedgerLock,
    append_entry,
    ledger_lock_path,
    ledger_path,
    load_records,
    run_self_test as run_record_self_test,
)

from learning_documents import (
    REPORT_SCHEMA_VERSION,
    SUPPORTED_DOCUMENT_SCHEMAS,
    STRICT_PROMOTION_STATES,
    KNOWN_PROMOTION_STATES,
    SHARED_SCOPES,
    SHARED_PRIVACY,
    _ID,
    _SHA256,
    _PRIVATE_VALUE,
    _PRIVATE_KEYS,
    Error,
    _add_error,
    _sha256_bytes,
    _read_json,
    _canonical_json,
    _atomic_write,
    _valid_id,
    _string_list,
    _fixture_groups,
    _private_markers,
    _safe_relative_path,
    _token_counter,
    _validate_topics,
    _validate_rules,
)

from learning_receipts import (
    _load_record_snapshot,
    _validate_strict_records,
    _receipt_paths,
    _validate_receipts,
    _validate_reciprocity,
)

def validate_learning(
    project: str | Path,
    topic_index: str | Path,
    receipts: Iterable[str | Path] = (),
    *,
    topic_root: str | Path | None = None,
    lock_timeout: float = 30.0,
) -> dict[str, object]:
    project_path = Path(project).resolve()
    index_path = Path(topic_index).resolve()
    errors: list[Error] = []
    try:
        index, index_hash = _read_json(index_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        index = {}
        index_hash = "unavailable"
        _add_error(errors, "INDEX_INVALID", "$.index", "topic index is missing or invalid JSON")

    errors.extend(_private_markers(index))
    if index.get("schemaVersion") not in SUPPORTED_DOCUMENT_SCHEMAS:
        _add_error(errors, "INDEX_SCHEMA_INVALID", "$.schemaVersion", "unsupported topic-index schema")
    resolved_topic_root = Path(topic_root).resolve() if topic_root is not None else index_path.parent
    topics, owners = _validate_topics(index, resolved_topic_root, errors, _token_counter(index, errors))
    rules = _validate_rules(index, topics, owners, errors)
    records = _load_record_snapshot(project_path, errors, lock_timeout)
    _validate_strict_records(records, errors)
    paths = _receipt_paths(index, index_path, [Path(path) for path in receipts], errors)
    receipt_identities, receipt_links = _validate_receipts(paths, index_hash, rules, records, errors)
    _validate_reciprocity(rules, records, receipt_links, errors)

    errors.sort(key=lambda item: (item["code"], item["location"], item["message"]))
    strict_rule_count = sum(
        1 for rule in rules.values() if rule.get("promotionState") in STRICT_PROMOTION_STATES
    )
    strict_record_count = sum(
        1 for record in records.values() if record.get("promotionState") in STRICT_PROMOTION_STATES
    )
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "gate": "learning-promotion-v2",
        "status": "PASS" if not errors else "BLOCK",
        "project": str(project_path),
        "index": {"path": str(index_path), "sha256": index_hash},
        "receipts": receipt_identities,
        "counts": {
            "topics": len(topics),
            "rules": len(rules),
            "strictRules": strict_rule_count,
            "records": len(records),
            "strictRecords": strict_record_count,
            "receipts": len(receipt_identities),
            "errors": len(errors),
        },
        "errors": errors,
    }

def run_self_test() -> None:
    from learning_selftest import run_self_test as replay
    import sys
    replay(sys.modules[__name__])

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".")
    parser.add_argument("--topic-index", "--index", dest="topic_index")
    parser.add_argument("--topic-root")
    parser.add_argument("--receipt", action="append", default=[])
    parser.add_argument("--lock-timeout", type=float, default=30.0)
    parser.add_argument("--output")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        print("learning_gate self-test passed (32 writers + promotion/index negatives)")
        return 0
    if not args.topic_index:
        parser.error("--topic-index is required unless --self-test is used")
    if args.quiet and not args.output:
        parser.error("--quiet requires --output")
    report = validate_learning(
        args.project,
        args.topic_index,
        args.receipt,
        topic_root=args.topic_root,
        lock_timeout=args.lock_timeout,
    )
    payload = _canonical_json(report)
    if args.output:
        _atomic_write(Path(args.output).resolve(), payload)
    if not args.quiet:
        print(payload.decode("utf-8"), end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
