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


REPORT_SCHEMA_VERSION = 1
SUPPORTED_DOCUMENT_SCHEMAS = {1, 2}
STRICT_PROMOTION_STATES = {"promoted", "active", "core"}
KNOWN_PROMOTION_STATES = STRICT_PROMOTION_STATES | {
    "raw",
    "provisional",
    "candidate",
    "rejected",
    "retired",
}
SHARED_SCOPES = {"cross-project", "shared-core"}
SHARED_PRIVACY = {"sanitized", "public", "public-safe"}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_PRIVATE_VALUE = re.compile(
    r"(?:[A-Za-z]:[\\/]+Users[\\/]|/(?:Users|home)/|private://|<private>|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\.ssh[\\/])",
    re.IGNORECASE,
)
_PRIVATE_KEYS = {
    "secret",
    "secrets",
    "password",
    "credentials",
    "credential",
    "apikey",
    "accesstoken",
    "refreshtoken",
    "privatepath",
    "rawprivate",
    "useridentity",
}


Error = dict[str, str]


def _add_error(errors: list[Error], code: str, location: str, message: str) -> None:
    errors.append({"code": code, "location": location, "message": message})


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, object], str]:
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("document root must be a JSON object")
    return value, _sha256_bytes(payload)


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def _string_list(
    value: object,
    location: str,
    errors: list[Error],
    *,
    required: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        _add_error(errors, "STRING_LIST_INVALID", location, "expected an array of unique strings")
        return []
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            _add_error(errors, "STRING_LIST_INVALID", f"{location}[{index}]", "expected a non-empty string")
            continue
        item = item.strip()
        if item in seen:
            _add_error(errors, "STRING_LIST_DUPLICATE", f"{location}[{index}]", "duplicate value")
            continue
        seen.add(item)
        result.append(item)
    if required and not result:
        _add_error(errors, "STRING_LIST_EMPTY", location, "at least one value is required")
    return result


def _fixture_groups(
    container: dict[str, object], location: str, errors: list[Error]
) -> tuple[list[str], list[str]]:
    fixture_ids = container.get("fixtureIds")
    if isinstance(fixture_ids, dict):
        positive_value = fixture_ids.get("positive", [])
        negative_value = fixture_ids.get("negative", [])
    else:
        if "fixtureIds" in container and fixture_ids is not None:
            _add_error(
                errors,
                "FIXTURE_IDS_INVALID",
                f"{location}.fixtureIds",
                "fixtureIds must be an object with positive/negative arrays",
            )
        positive_value = container.get("positiveFixtureIds", [])
        negative_value = container.get("negativeFixtureIds", [])
    positive = _string_list(positive_value, f"{location}.positiveFixtureIds", errors)
    negative = _string_list(negative_value, f"{location}.negativeFixtureIds", errors)
    return positive, negative


def _private_markers(value: object, location: str = "$") -> list[Error]:
    errors: list[Error] = []
    if isinstance(value, dict):
        for key in sorted(value):
            item = value[key]
            normalized_key = re.sub(r"[^a-z0-9]", "", key.casefold())
            child = f"{location}.{key}"
            if normalized_key in _PRIVATE_KEYS:
                _add_error(errors, "PRIVATE_MARKER", child, "private credential/path key is forbidden")
            if normalized_key == "privacy" and isinstance(item, str) and item.casefold() in {
                "private",
                "project-private",
                "raw-private",
            }:
                _add_error(errors, "PRIVATE_MARKER", child, "shared material cannot declare private privacy")
            errors.extend(_private_markers(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(_private_markers(item, f"{location}[{index}]"))
    elif isinstance(value, str) and _PRIVATE_VALUE.search(value):
        _add_error(errors, "PRIVATE_MARKER", location, "private path/key marker is forbidden")
    return errors


def _safe_relative_path(root: Path, raw: object) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    raw = raw.strip()
    if PurePosixPath(raw).is_absolute() or PureWindowsPath(raw).is_absolute():
        return None
    normalized = raw.replace("\\", "/")
    if any(part in {"", ".", ".."} for part in PurePosixPath(normalized).parts):
        return None
    candidate = (root / Path(*PurePosixPath(normalized).parts)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _token_counter(index: dict[str, object], errors: list[Error]):
    identity = index.get("tokenizer")
    if identity is None:
        return None
    if not isinstance(identity, dict):
        _add_error(errors, "TOKENIZER_INVALID", "$.tokenizer", "tokenizer must be an identity object")
        return None
    name, version = identity.get("id"), identity.get("version")
    if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
        _add_error(errors, "TOKENIZER_INVALID", "$.tokenizer", "tokenizer id and version are required")
        return None
    try:
        import tiktoken

        installed = importlib.metadata.version("tiktoken")
        encoder = tiktoken.get_encoding(name)
    except (ImportError, importlib.metadata.PackageNotFoundError, ValueError):
        _add_error(errors, "TOKENIZER_UNAVAILABLE", "$.tokenizer", "declared tokenizer is unavailable")
        return None
    if installed != version:
        _add_error(errors, "TOKENIZER_VERSION_MISMATCH", "$.tokenizer.version", "installed tokenizer version differs")
        return None
    return lambda text: len(encoder.encode(text))


def _validate_topics(
    index: dict[str, object], topic_root: Path, errors: list[Error], token_counter=None
) -> tuple[dict[str, dict[str, object]], dict[str, list[str]]]:
    topics_value = index.get("topics")
    if not isinstance(topics_value, list):
        _add_error(errors, "TOPICS_INVALID", "$.topics", "topics must be an array")
        return {}, {}
    topics: dict[str, dict[str, object]] = {}
    owners: dict[str, list[str]] = defaultdict(list)
    seen_paths: set[str] = set()
    for position, value in enumerate(topics_value):
        location = f"$.topics[{position}]"
        if not isinstance(value, dict):
            _add_error(errors, "TOPIC_INVALID", location, "topic must be an object")
            continue
        topic_id = value.get("id")
        if not _valid_id(topic_id):
            _add_error(errors, "TOPIC_ID_INVALID", f"{location}.id", "invalid topic id")
            continue
        assert isinstance(topic_id, str)
        if topic_id in topics:
            _add_error(errors, "TOPIC_ID_DUPLICATE", f"{location}.id", "topic id must be unique")
            continue
        topics[topic_id] = value

        topic_path = _safe_relative_path(topic_root, value.get("path"))
        if topic_path is None:
            _add_error(errors, "TOPIC_PATH_INVALID", f"{location}.path", "path must be a safe relative topic file")
        else:
            folded = str(topic_path).casefold()
            if folded in seen_paths:
                _add_error(errors, "TOPIC_PATH_DUPLICATE", f"{location}.path", "topic paths must be unique")
            seen_paths.add(folded)
            if not topic_path.is_file():
                _add_error(errors, "TOPIC_PATH_MISSING", f"{location}.path", "topic file does not exist")
            else:
                payload = topic_path.read_bytes()
                declared_hash = value.get("sha256", value.get("contentSha256"))
                if not isinstance(declared_hash, str) or not _SHA256.fullmatch(declared_hash):
                    _add_error(errors, "TOPIC_HASH_INVALID", f"{location}.sha256", "sha256 must be 64 hexadecimal characters")
                elif _sha256_bytes(payload) != declared_hash.casefold():
                    _add_error(errors, "TOPIC_HASH_MISMATCH", f"{location}.sha256", "topic hash does not match live bytes")
                try:
                    topic_text = payload.decode("utf-8")
                except UnicodeDecodeError:
                    _add_error(errors, "TOPIC_UTF8_INVALID", f"{location}.path", "topic must be UTF-8")
                else:
                    errors.extend(_private_markers(topic_text, f"{location}.content"))
                    if token_counter is not None and token_counter(topic_text) != value.get(
                        "tokenCost", value.get("estimatedTokens")
                    ):
                        _add_error(errors, "TOPIC_TOKEN_COST_MISMATCH", f"{location}.tokenCost", "token cost does not match live topic bytes")

        token_cost = value.get("tokenCost", value.get("estimatedTokens"))
        if isinstance(token_cost, bool) or not isinstance(token_cost, int) or token_cost <= 0:
            _add_error(errors, "TOPIC_TOKEN_COST_INVALID", f"{location}.tokenCost", "token cost must be a positive integer")
        if value.get("privacy") not in SHARED_PRIVACY:
            _add_error(errors, "TOPIC_PRIVACY_INVALID", f"{location}.privacy", "shared topic must be sanitized or public")

        rule_ids = _string_list(value.get("ruleIds", []), f"{location}.ruleIds", errors)
        for rule_id in rule_ids:
            owners[rule_id].append(topic_id)
    return topics, owners


def _validate_rules(
    index: dict[str, object],
    topics: dict[str, dict[str, object]],
    owners: dict[str, list[str]],
    errors: list[Error],
) -> dict[str, dict[str, object]]:
    rules_value = index.get("rules")
    if not isinstance(rules_value, list):
        _add_error(errors, "RULES_INVALID", "$.rules", "rules must be an array")
        return {}
    rules: dict[str, dict[str, object]] = {}
    for position, value in enumerate(rules_value):
        location = f"$.rules[{position}]"
        if not isinstance(value, dict):
            _add_error(errors, "RULE_INVALID", location, "rule must be an object")
            continue
        rule_id = value.get("id")
        if not _valid_id(rule_id):
            _add_error(errors, "RULE_ID_INVALID", f"{location}.id", "invalid rule id")
            continue
        assert isinstance(rule_id, str)
        if rule_id in rules:
            _add_error(errors, "RULE_ID_DUPLICATE", f"{location}.id", "rule id must be unique")
            continue

        owner = value.get("ownerTopic", value.get("topicId"))
        owner_list = owners.get(rule_id, [])
        if len(owner_list) != 1:
            _add_error(errors, "RULE_OWNER_COUNT", f"{location}.ownerTopic", "rule must appear in exactly one topic ruleIds list")
        if not isinstance(owner, str) or owner not in topics:
            _add_error(errors, "RULE_OWNER_INVALID", f"{location}.ownerTopic", "ownerTopic must name an existing topic")
        elif owner_list and owner_list != [owner]:
            _add_error(errors, "RULE_OWNER_MISMATCH", f"{location}.ownerTopic", "declared owner and topic ruleIds disagree")

        state = value.get("promotionState", "provisional")
        if state not in KNOWN_PROMOTION_STATES:
            _add_error(errors, "RULE_PROMOTION_STATE_INVALID", f"{location}.promotionState", "unknown promotion state")
            state = "provisional"
        evidence_state = value.get("evidenceState", "unmeasured")
        experiment_ids = _string_list(value.get("experimentIds", []), f"{location}.experimentIds", errors)
        positive, negative = _fixture_groups(value, location, errors)
        normalized = dict(value)
        normalized.update(
            {
                "id": rule_id,
                "ownerTopic": owner,
                "promotionState": state,
                "evidenceState": evidence_state,
                "experimentIds": experiment_ids,
                "positiveFixtureIds": positive,
                "negativeFixtureIds": negative,
            }
        )
        rules[rule_id] = normalized
        if state in STRICT_PROMOTION_STATES:
            if evidence_state != "verified":
                _add_error(errors, "RULE_EVIDENCE_NOT_VERIFIED", f"{location}.evidenceState", "active/core/promoted rules require verified evidence")
            if value.get("privacy") not in SHARED_PRIVACY:
                _add_error(errors, "RULE_PRIVACY_INVALID", f"{location}.privacy", "promoted rule must be sanitized or public")
            if not experiment_ids:
                _add_error(errors, "RULE_EXPERIMENT_REQUIRED", f"{location}.experimentIds", "promoted rule requires an experiment link")
            if not positive:
                _add_error(errors, "RULE_POSITIVE_FIXTURE_REQUIRED", f"{location}.positiveFixtureIds", "promoted rule requires a positive fixture")
            if not negative:
                _add_error(errors, "RULE_NEGATIVE_FIXTURE_REQUIRED", f"{location}.negativeFixtureIds", "promoted rule requires a negative fixture")

    for rule_id in sorted(owners):
        if rule_id not in rules:
            _add_error(errors, "TOPIC_RULE_UNKNOWN", "$.topics", "topic owns a rule absent from the rule registry")
    return rules


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


def run_self_test() -> None:
    # record_experiment runs a real 32-process writer fixture.
    run_record_self_test()
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        project, shared, topic_hash, index, receipt = _set_up_positive_fixture(root)
        _test_project_local_provisional(root, shared, topic_hash)
        _test_malformed_documents(project, shared, index, receipt)


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
