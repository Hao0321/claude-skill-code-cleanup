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
