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

def _load_record_snapshot(
    project: Path, errors: list[Error], lock_timeout: float
) -> dict[str, dict[str, object]]:
    try:
        with LedgerLock(ledger_lock_path(project), timeout=lock_timeout):
            records = load_records(project)
            path = ledger_path(project)
            if records and not path.is_file():
                _add_error(errors, "LEDGER_VIEW_MISSING", "$.records", "generated ledger view is missing")
            elif records:
                try:
                    rows = [
                        json.loads(line)
                        for line in path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                except (OSError, UnicodeError, json.JSONDecodeError):
                    _add_error(errors, "LEDGER_VIEW_INVALID", "$.records", "generated ledger view is invalid JSONL")
                else:
                    if rows != records:
                        _add_error(errors, "LEDGER_VIEW_STALE", "$.records", "generated ledger view differs from immutable records")
    except (OSError, ValueError, TimeoutError) as error:
        _add_error(errors, "RECORD_AUTHORITY_INVALID", "$.records", str(error))
        return {}
    return {str(record["id"]): record for record in records}


def _validate_strict_records(records: dict[str, dict[str, object]], errors: list[Error]) -> None:
    for record_id in sorted(records):
        record = records[record_id]
        state = record.get("promotionState", "raw")
        if state not in STRICT_PROMOTION_STATES:
            # Raw/provisional knowledge deliberately stays private and project-local.
            continue
        location = f"$.records[{record_id}]"
        if record.get("schemaVersion") != 2:
            _add_error(errors, "RECORD_SCHEMA_INVALID", f"{location}.schemaVersion", "promoted records require schemaVersion 2")
        if record.get("privacy") not in SHARED_PRIVACY:
            _add_error(errors, "RECORD_PRIVACY_INVALID", f"{location}.privacy", "promoted record must be sanitized or public")
        if record.get("scope") not in SHARED_SCOPES:
            _add_error(errors, "RECORD_SCOPE_INVALID", f"{location}.scope", "promoted record must use a shared scope")
        if record.get("evidenceState") != "verified":
            _add_error(errors, "RECORD_EVIDENCE_NOT_VERIFIED", f"{location}.evidenceState", "promoted record requires verified evidence")
        _string_list(record.get("applicability"), f"{location}.applicability", errors)
        _string_list(record.get("exclusions"), f"{location}.exclusions", errors)
        _string_list(record.get("ruleIds"), f"{location}.ruleIds", errors, required=True)
        positive, negative = _fixture_groups(record, location, errors)
        if not positive:
            _add_error(errors, "RECORD_POSITIVE_FIXTURE_REQUIRED", f"{location}.fixtureIds", "promoted record requires a positive fixture")
        if not negative:
            _add_error(errors, "RECORD_NEGATIVE_FIXTURE_REQUIRED", f"{location}.fixtureIds", "promoted record requires a negative fixture")
        for field in ("environmentIdentity", "datasetIdentity"):
            identity = record.get(field)
            if not isinstance(identity, dict) or not isinstance(identity.get("id"), str) or identity.get("id") in {"", "unmeasured"}:
                _add_error(errors, "RECORD_IDENTITY_INVALID", f"{location}.{field}", "promoted record requires a measured identity")
            elif "sha256" in identity and (
                not isinstance(identity["sha256"], str)
                or not _SHA256.fullmatch(identity["sha256"])
            ):
                _add_error(errors, "RECORD_IDENTITY_HASH_INVALID", f"{location}.{field}.sha256", "identity hash must be SHA-256")
        if not isinstance(record.get("topic"), str) or not record.get("topic"):
            _add_error(errors, "RECORD_TOPIC_INVALID", f"{location}.topic", "promoted record requires a topic")
        if not isinstance(record.get("nextDecision"), str) or not record.get("nextDecision"):
            _add_error(errors, "RECORD_NEXT_DECISION_INVALID", f"{location}.nextDecision", "nextDecision must be non-empty")
        failure_type = record.get("failureType")
        if failure_type is not None and failure_type not in FAILURE_TYPES:
            _add_error(errors, "RECORD_FAILURE_TYPE_INVALID", f"{location}.failureType", "unknown failure type")
        errors.extend(_private_markers(record, location))


def _receipt_paths(
    index: dict[str, object], index_path: Path, explicit: Iterable[Path], errors: list[Error]
) -> list[Path]:
    paths = [path.resolve() for path in explicit]
    declared = index.get("promotionReceipts", [])
    if not isinstance(declared, list):
        _add_error(errors, "RECEIPT_LIST_INVALID", "$.promotionReceipts", "promotionReceipts must be an array")
    else:
        for position, raw in enumerate(declared):
            path = _safe_relative_path(index_path.parent, raw)
            if path is None:
                _add_error(errors, "RECEIPT_PATH_INVALID", f"$.promotionReceipts[{position}]", "receipt path must be safe and relative")
            else:
                paths.append(path)
    unique = {str(path).casefold(): path for path in paths}
    return [unique[key] for key in sorted(unique)]


def _validate_receipts(
    paths: list[Path],
    index_hash: str,
    rules: dict[str, dict[str, object]],
    records: dict[str, dict[str, object]],
    errors: list[Error],
) -> tuple[list[dict[str, str]], dict[str, set[tuple[str, str]]]]:
    identities: list[dict[str, str]] = []
    links: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for position, path in enumerate(paths):
        location = f"$.receipts[{position}]"
        try:
            receipt, digest = _read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            _add_error(errors, "RECEIPT_INVALID", location, "receipt is missing or invalid JSON")
            continue
        identities.append({"path": str(path), "sha256": digest})
        errors.extend(_private_markers(receipt, location))
        if receipt.get("schemaVersion") not in SUPPORTED_DOCUMENT_SCHEMAS:
            _add_error(errors, "RECEIPT_SCHEMA_INVALID", f"{location}.schemaVersion", "unsupported receipt schema")
        if receipt.get("topicIndexSha256") != index_hash:
            _add_error(errors, "RECEIPT_INDEX_HASH_MISMATCH", f"{location}.topicIndexSha256", "receipt is not bound to the live topic index")
        state = receipt.get("promotionState", "promoted")
        if state not in STRICT_PROMOTION_STATES:
            _add_error(errors, "RECEIPT_PROMOTION_STATE_INVALID", f"{location}.promotionState", "promotion receipt must be promoted, active, or core")
        if "privacy" in receipt and receipt.get("privacy") not in SHARED_PRIVACY:
            _add_error(errors, "RECEIPT_PRIVACY_INVALID", f"{location}.privacy", "promotion receipt must be sanitized or public")
        experiment_id = receipt.get("experimentId")
        if not _valid_id(experiment_id):
            _add_error(errors, "RECEIPT_EXPERIMENT_INVALID", f"{location}.experimentId", "invalid experiment id")
            experiment_id = ""
        rule_ids = _string_list(receipt.get("ruleIds"), f"{location}.ruleIds", errors, required=True)
        positive, negative = _fixture_groups(receipt, location, errors)
        if not positive:
            _add_error(errors, "RECEIPT_POSITIVE_FIXTURE_REQUIRED", f"{location}.positiveFixtureIds", "promotion receipt requires a positive fixture")
        if not negative:
            _add_error(errors, "RECEIPT_NEGATIVE_FIXTURE_REQUIRED", f"{location}.negativeFixtureIds", "promotion receipt requires a negative fixture")
        record = records.get(str(experiment_id))
        if experiment_id and record is None:
            _add_error(errors, "RECEIPT_EXPERIMENT_MISSING", f"{location}.experimentId", "immutable experiment record is missing")
        record_rules = set(record.get("ruleIds", [])) if isinstance(record, dict) and isinstance(record.get("ruleIds"), list) else set()
        record_positive, record_negative = _fixture_groups(record, location, errors) if isinstance(record, dict) else ([], [])
        for rule_id in rule_ids:
            rule = rules.get(rule_id)
            if rule is None:
                _add_error(errors, "RECEIPT_RULE_UNKNOWN", f"{location}.ruleIds", "receipt names an unknown rule")
                continue
            links[rule_id].add((str(experiment_id), digest))
            if rule.get("promotionState") not in STRICT_PROMOTION_STATES:
                _add_error(errors, "RECEIPT_RULE_NOT_PROMOTED", f"{location}.ruleIds", "receipt rule is not in a strict promotion state")
            if experiment_id not in rule.get("experimentIds", []):
                _add_error(errors, "RECEIPT_RULE_EXPERIMENT_MISMATCH", f"{location}.experimentId", "rule does not link back to receipt experiment")
            if rule_id not in record_rules:
                _add_error(errors, "RECEIPT_EXPERIMENT_RULE_MISMATCH", f"{location}.ruleIds", "experiment does not link back to receipt rule")
            if not set(positive).issubset(set(rule.get("positiveFixtureIds", []))) or not set(negative).issubset(set(rule.get("negativeFixtureIds", []))):
                _add_error(errors, "RECEIPT_RULE_FIXTURE_MISMATCH", f"{location}.fixtureIds", "receipt fixtures are not owned by the rule")
            if not set(positive).issubset(set(record_positive)) or not set(negative).issubset(set(record_negative)):
                _add_error(errors, "RECEIPT_EXPERIMENT_FIXTURE_MISMATCH", f"{location}.fixtureIds", "receipt fixtures are not linked by the experiment")
    return sorted(identities, key=lambda item: item["path"].casefold()), links


def _validate_reciprocity(
    rules: dict[str, dict[str, object]],
    records: dict[str, dict[str, object]],
    receipt_links: dict[str, set[tuple[str, str]]],
    errors: list[Error],
) -> None:
    for rule_id in sorted(rules):
        rule = rules[rule_id]
        if rule.get("promotionState") not in STRICT_PROMOTION_STATES:
            continue
        location = f"$.rules[{rule_id}]"
        expected_experiments = set(rule.get("experimentIds", []))
        for experiment_id in sorted(expected_experiments):
            record = records.get(experiment_id)
            if record is None:
                _add_error(errors, "RULE_EXPERIMENT_MISSING", f"{location}.experimentIds", "linked immutable experiment is missing")
                continue
            if rule_id not in record.get("ruleIds", []):
                _add_error(errors, "RULE_EXPERIMENT_NOT_RECIPROCAL", f"{location}.experimentIds", "experiment does not link back to rule")
            if record.get("promotionState") not in STRICT_PROMOTION_STATES:
                _add_error(errors, "RULE_EXPERIMENT_NOT_PROMOTED", f"{location}.experimentIds", "linked experiment is not promoted/active/core")
        linked_experiments = {experiment_id for experiment_id, _ in receipt_links.get(rule_id, set())}
        if not expected_experiments.intersection(linked_experiments):
            _add_error(errors, "RULE_PROMOTION_RECEIPT_MISSING", location, "strict rule needs a matching promotion receipt")

    for experiment_id in sorted(records):
        record = records[experiment_id]
        if record.get("promotionState") not in STRICT_PROMOTION_STATES:
            continue
        for rule_id in record.get("ruleIds", []):
            rule = rules.get(rule_id)
            if rule is None:
                _add_error(errors, "EXPERIMENT_RULE_UNKNOWN", f"$.records[{experiment_id}].ruleIds", "promoted experiment names an unknown rule")
            elif experiment_id not in rule.get("experimentIds", []):
                _add_error(errors, "EXPERIMENT_RULE_NOT_RECIPROCAL", f"$.records[{experiment_id}].ruleIds", "rule does not link back to experiment")
            elif not any(
                linked_experiment == experiment_id
                for linked_experiment, _ in receipt_links.get(rule_id, set())
            ):
                _add_error(
                    errors,
                    "EXPERIMENT_RULE_RECEIPT_MISSING",
                    f"$.records[{experiment_id}].ruleIds",
                    "promoted experiment/rule pair needs a receipt",
                )
