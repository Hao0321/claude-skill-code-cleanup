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


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json(value))


def _self_test_record(experiment_id: str, state: str, privacy: str, scope: str) -> dict[str, object]:
    return {
        "schemaVersion": 2,
        "id": experiment_id,
        "recordedAt": "2026-08-30T00:00:00+00:00",
        "hypothesis": "typed learning survives routing",
        "change": "immutable record",
        "result": "pass",
        "evidence": "evidence/self-test.json",
        "metrics": {"writers": 32},
        "learning": "promote only with reciprocal fixtures",
        "topic": "architecture",
        "scope": scope,
        "privacy": privacy,
        "applicability": ["skills"],
        "exclusions": ["unmeasured claims"],
        "ruleIds": ["rule.atomic-learning"] if state in STRICT_PROMOTION_STATES else [],
        "fixtureIds": {
            "positive": ["fixture.concurrent-positive"] if state in STRICT_PROMOTION_STATES else [],
            "negative": ["fixture.torn-negative"] if state in STRICT_PROMOTION_STATES else [],
            "other": [],
        },
        "promotionState": state,
        "evidenceState": "verified" if state in STRICT_PROMOTION_STATES else "raw",
        "expiresOn": None,
        "nextDecision": "retain",
        "environmentIdentity": {"id": "python-3.10-windows"},
        "datasetIdentity": {"id": "learning-gate-self-test-v1"},
    }


def _assert_negative(
    project: Path,
    root: Path,
    name: str,
    index: dict[str, object],
    receipt: dict[str, object],
    expected_code: str,
    *,
    preserve_bad_index_hash: bool = False,
) -> None:
    index_path = root / f"{name}-index.json"
    receipt_path = root / f"{name}-receipt.json"
    _write_json(index_path, index)
    if not preserve_bad_index_hash:
        receipt["topicIndexSha256"] = _sha256_bytes(index_path.read_bytes())
    _write_json(receipt_path, receipt)
    report = validate_learning(project, index_path, [receipt_path], topic_root=root)
    codes = {error["code"] for error in report["errors"]}
    assert report["status"] == "BLOCK", report
    assert expected_code in codes, (expected_code, codes, report)


def _base_self_test_documents(
    topic_hash: str,
    promoted_id: str,
    topic_cost: int,
    tokenizer: dict[str, str],
) -> tuple[dict[str, object], dict[str, object]]:
    index: dict[str, object] = {
        "schemaVersion": 1,
        "tokenizer": tokenizer,
        "topics": [
            {
                "id": "architecture",
                "path": "architecture.md",
                "sha256": topic_hash,
                "tokenCost": topic_cost,
                "privacy": "sanitized",
                "ruleIds": ["rule.atomic-learning"],
            }
        ],
        "rules": [
            {
                "id": "rule.atomic-learning",
                "ownerTopic": "architecture",
                "experimentIds": [promoted_id],
                "positiveFixtureIds": ["fixture.concurrent-positive"],
                "negativeFixtureIds": ["fixture.torn-negative"],
                "promotionState": "active",
                "evidenceState": "verified",
                "privacy": "sanitized",
            }
        ],
    }
    receipt: dict[str, object] = {
        "schemaVersion": 1,
        "promotionState": "active",
        "experimentId": promoted_id,
        "ruleIds": ["rule.atomic-learning"],
        "positiveFixtureIds": ["fixture.concurrent-positive"],
        "negativeFixtureIds": ["fixture.torn-negative"],
        "topicIndexSha256": "pending",
    }
    return index, receipt


def _set_up_positive_fixture(
    root: Path,
) -> tuple[Path, Path, str, dict[str, object], dict[str, object]]:
    project, shared = root / "project", root / "shared"
    project.mkdir()
    shared.mkdir()
    promoted_id = "exp-learning-promoted"
    append_entry(project, _self_test_record(promoted_id, "active", "sanitized", "cross-project"))
    raw = _self_test_record("exp-learning-raw", "raw", "private", "project-local")
    raw["learning"] = "private://project-only"
    append_entry(project, raw)
    topic_path = shared / "architecture.md"
    topic_text = "# Architecture\n\nAtomic learning rule.\n"
    topic_path.write_text(topic_text, encoding="utf-8")
    topic_hash = _sha256_bytes(topic_path.read_bytes())
    import tiktoken

    tokenizer_id = "o200k_base"
    tokenizer = {"id": tokenizer_id, "version": importlib.metadata.version("tiktoken")}
    topic_cost = len(tiktoken.get_encoding(tokenizer_id).encode(topic_text))
    index, receipt = _base_self_test_documents(topic_hash, promoted_id, topic_cost, tokenizer)
    index_path, receipt_path = shared / "topic-index.json", shared / "promotion-receipt.json"
    _write_json(index_path, index)
    receipt["topicIndexSha256"] = _sha256_bytes(index_path.read_bytes())
    _write_json(receipt_path, receipt)
    report = validate_learning(project, index_path, [receipt_path], topic_root=shared)
    assert report["status"] == "PASS", report
    assert report["counts"] == {
        "topics": 1,
        "rules": 1,
        "strictRules": 1,
        "records": 2,
        "strictRecords": 1,
        "receipts": 1,
        "errors": 0,
    }
    return project, shared, topic_hash, index, receipt


def _test_project_local_provisional(root: Path, shared: Path, topic_hash: str) -> None:
    project = root / "local-project"
    project.mkdir()
    record = _self_test_record("exp-local-provisional", "provisional", "private", "project-local")
    record["learning"] = "private://allowed-while-project-local"
    append_entry(project, record)
    index = {
        "schemaVersion": 1,
        "topics": [{
            "id": "architecture", "path": "architecture.md", "sha256": topic_hash,
            "tokenCost": 12, "privacy": "sanitized", "ruleIds": ["rule.project-only"],
        }],
        "rules": [{
            "id": "rule.project-only", "ownerTopic": "architecture", "experimentIds": [],
            "positiveFixtureIds": [], "negativeFixtureIds": [],
            "promotionState": "provisional", "evidenceState": "diagnostic", "privacy": "sanitized",
        }],
    }
    path = shared / "provisional-index.json"
    _write_json(path, index)
    report = validate_learning(project, path, [], topic_root=shared)
    assert report["status"] == "PASS", report


def _test_malformed_documents(
    project: Path,
    shared: Path,
    base_index: dict[str, object],
    base_receipt: dict[str, object],
) -> None:
    second_topic = shared / "second.md"
    second_topic.write_text("# Second\n", encoding="utf-8")
    duplicate_owner = copy.deepcopy(base_index)
    duplicate_owner["topics"].append({
        "id": "second", "path": "second.md", "sha256": _sha256_bytes(second_topic.read_bytes()),
        "tokenCost": 3, "privacy": "sanitized", "ruleIds": ["rule.atomic-learning"],
    })
    cases: list[tuple[str, dict[str, object], dict[str, object], str]] = []
    bad_path = copy.deepcopy(base_index)
    bad_path["topics"][0]["path"] = "../outside.md"
    cases.append(("bad-path", bad_path, copy.deepcopy(base_receipt), "TOPIC_PATH_INVALID"))
    bad_hash = copy.deepcopy(base_index)
    bad_hash["topics"][0]["sha256"] = "0" * 64
    cases.append(("bad-hash", bad_hash, copy.deepcopy(base_receipt), "TOPIC_HASH_MISMATCH"))
    bad_tokens = copy.deepcopy(base_index)
    bad_tokens["topics"][0]["tokenCost"] += 1
    cases.append(("bad-tokens", bad_tokens, copy.deepcopy(base_receipt), "TOPIC_TOKEN_COST_MISMATCH"))
    private_index = copy.deepcopy(base_index)
    private_index["notes"] = "private://owner-only"
    cases.append(("private-index", private_index, copy.deepcopy(base_receipt), "PRIVATE_MARKER"))
    missing_negative = copy.deepcopy(base_index)
    missing_negative["rules"][0]["negativeFixtureIds"] = []
    cases.append(("missing-rule-negative", missing_negative, copy.deepcopy(base_receipt), "RULE_NEGATIVE_FIXTURE_REQUIRED"))
    missing_reciprocal = copy.deepcopy(base_index)
    missing_reciprocal["rules"][0]["experimentIds"] = []
    cases.append(("missing-reciprocal", missing_reciprocal, copy.deepcopy(base_receipt), "RULE_EXPERIMENT_REQUIRED"))
    bad_receipt = copy.deepcopy(base_receipt)
    bad_receipt["negativeFixtureIds"] = []
    cases.append(("bad-receipt-fixture", copy.deepcopy(base_index), bad_receipt, "RECEIPT_NEGATIVE_FIXTURE_REQUIRED"))
    _assert_negative(project, shared, "duplicate-owner", duplicate_owner, copy.deepcopy(base_receipt), "RULE_OWNER_COUNT")
    for name, index, receipt, code in cases:
        _assert_negative(project, shared, name, index, receipt, code)
    stale_receipt = copy.deepcopy(base_receipt)
    stale_receipt["topicIndexSha256"] = "f" * 64
    _assert_negative(
        project, shared, "stale-receipt", copy.deepcopy(base_index), stale_receipt,
        "RECEIPT_INDEX_HASH_MISMATCH", preserve_bad_index_hash=True,
    )


def run_self_test(api) -> None:
    globals().update({name: getattr(api, name) for name in ('validate_learning',)})
    # record_experiment runs a real 32-process writer fixture.
    run_record_self_test()
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        project, shared, topic_hash, index, receipt = _set_up_positive_fixture(root)
        _test_project_local_provisional(root, shared, topic_hash)
        _test_malformed_documents(project, shared, index, receipt)
