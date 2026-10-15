"""Shared bounded-I/O and identity primitives for completion closure."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from pathlib import Path
from typing import Any, Callable

from evidence_identity import valid_identity
from project_profile_gate import sha256_json
from completion_closure_io import (
    SKILL_ROOT,
    SCOPES,
    CHECK_KINDS,
    SECURITY_CONTROL_IDS,
    SECURITY_CAPABILITY_IDS,
    SECURITY_SNAPSHOT_PROFILE,
    SECURITY_TARGET_IDENTITY_PROFILE,
    SECURITY_CONTROL_PROFILE,
    PUBLIC_EXACTLY_ONE_CHECK_KINDS,
    PUBLIC_AT_LEAST_ONE_CHECK_KINDS,
    TARGET_PRODUCT_MAX_CHARS,
    TARGET_PRODUCT_MAX_UTF8_BYTES,
    TARGET_VERSION_MAX_CHARS,
    TARGET_VERSION_MAX_UTF8_BYTES,
    MAX_COMPLETION_SECURITY_AGE_SECONDS,
    SHA256_RE,
    SENSITIVE_IDENTITY_PATTERNS,
    MAX_JSON_BYTES,
    MIN_JSON_INT,
    MAX_JSON_INT,
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    MAX_PORTABLE_PATH_CHARS,
    MAX_PORTABLE_COMPONENT_CHARS,
    READ_CHUNK_BYTES,
    WINDOWS_RESERVED_NAMES,
    REQUIRED_NEGATIVE_CONTROLS,
    FailureSink,
    CleanupVerifier,
    DeliveryEvaluator,
    CapabilityEvaluator,
    ReceiptVerifier,
    SecurityVerifier,
    DuplicateJsonKey,
    _valid_target_identity,
    _target_identity_sha256,
    _lexical_absolute,
    _lexically_contained,
    _portable_parts,
    _is_link_or_reparse,
    _path_chain_error,
    _stable_stat,
    _stream_file,
    file_identity,
    _closed_json_object,
    _bounded_json_int,
    _reject_json_number,
    _validate_json_model,
    _parse_json_bytes,
    _read_json_with_identity,
    _resolve,
    _existing_cli_path,
    _prepare_output_path,
    _read_json,
)

def _check_observed_identity(
    observed: dict[str, Any], check: dict[str, Any], check_id: str, fail: FailureSink,
) -> None:
    if not valid_identity(check):
        fail("invalid-file-identity", "check needs positive bytes and lowercase SHA-256", check_id)
        return
    if observed != {"bytes": check["bytes"], "sha256": check["sha256"]}:
        fail("stale-file-identity", "live file no longer matches the closure contract", check_id, path=check.get("path"))


def _check_identity(
    path: Path, check: dict[str, Any], root: Path, check_id: str, fail: FailureSink,
) -> dict[str, Any] | None:
    identity = file_identity(path)
    _check_observed_identity(identity, check, check_id, fail)
    project_root, error = _resolve(root, check.get("projectRoot"), directory=True)
    role = check.get("role")
    if error or project_root is None or not _lexically_contained(project_root, path):
        fail("public-check-subject", "file identity is outside its declared project", check_id)
        return None
    if role not in {"release-artifact", "supporting-artifact"}:
        fail("public-artifact-binding", "file identity needs a typed artifact role", check_id)
        return None
    return {
        "kind": "file-identity",
        "projectRoot": project_root,
        "role": role,
        "identity": identity,
    }


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _resolve_route_reference(value: Any) -> tuple[Path | None, str | None]:
    parts, error = _portable_parts(value, allow_one_leading_parent=True)
    if error or parts is None:
        return None, error
    if parts[0] == ".." and (
        len(parts) < 2 or parts[1].casefold() != "code-cleanup-helper"
    ):
        return None, "route reference may leave R&D only for code-cleanup-helper"
    candidate = _lexical_absolute(SKILL_ROOT.joinpath(*parts))
    allowed_roots = (
        _lexical_absolute(SKILL_ROOT),
        _lexical_absolute(SKILL_ROOT.parent / "code-cleanup-helper"),
    )
    if not any(_lexically_contained(base, candidate) for base in allowed_roots):
        return None, "route reference escapes the two canonical Skills"
    error = _path_chain_error(candidate)
    if error:
        return None, error
    return candidate, None


def _route_reference_bundle(
    route: dict[str, Any], list_field: str, identity_field: str, hash_field: str,
    check_id: str, fail: FailureSink,
) -> None:
    references = route.get(list_field)
    identities = route.get(identity_field)
    hashes = route.get("hashes") if isinstance(route.get("hashes"), dict) else {}
    if not isinstance(references, list) or any(
        not isinstance(item, str) or not item or "\\" in item for item in references
    ):
        fail("route-reference-stale", f"route {list_field} must be a string array", check_id)
        return
    folded = [item.casefold() for item in references]
    if len(folded) != len(set(folded)):
        fail("route-reference-stale", f"route {list_field} contains duplicate paths", check_id)
    if not isinstance(identities, dict) or set(identities) != set(references):
        fail(
            "route-reference-stale",
            f"route {identity_field} must exactly cover {list_field}",
            check_id,
        )
        return

    current: list[dict[str, Any]] = []
    for reference in references:
        candidate, error = _resolve_route_reference(reference)
        if error or candidate is None:
            fail("route-reference-stale", f"unsafe route reference: {error}", check_id, reference=reference)
            continue
        identity = file_identity(candidate)
        current.append({"reference": reference, **identity})
        if identities.get(reference) != identity["sha256"]:
            fail("route-reference-stale", "route reference hash differs from current bytes", check_id, reference=reference)
    if len(current) == len(references) and hashes.get(hash_field) != sha256_json(current):
        fail("route-reference-stale", f"route hashes.{hash_field} is stale", check_id)


__all__ = [
    'SKILL_ROOT',
    'SCOPES',
    'CHECK_KINDS',
    'SECURITY_CONTROL_IDS',
    'SECURITY_CAPABILITY_IDS',
    'SECURITY_SNAPSHOT_PROFILE',
    'SECURITY_TARGET_IDENTITY_PROFILE',
    'SECURITY_CONTROL_PROFILE',
    'PUBLIC_EXACTLY_ONE_CHECK_KINDS',
    'PUBLIC_AT_LEAST_ONE_CHECK_KINDS',
    'TARGET_PRODUCT_MAX_CHARS',
    'TARGET_PRODUCT_MAX_UTF8_BYTES',
    'TARGET_VERSION_MAX_CHARS',
    'TARGET_VERSION_MAX_UTF8_BYTES',
    'MAX_COMPLETION_SECURITY_AGE_SECONDS',
    'SHA256_RE',
    'SENSITIVE_IDENTITY_PATTERNS',
    'MAX_JSON_BYTES',
    'MIN_JSON_INT',
    'MAX_JSON_INT',
    'MAX_JSON_DEPTH',
    'MAX_JSON_NODES',
    'MAX_PORTABLE_PATH_CHARS',
    'MAX_PORTABLE_COMPONENT_CHARS',
    'READ_CHUNK_BYTES',
    'WINDOWS_RESERVED_NAMES',
    'REQUIRED_NEGATIVE_CONTROLS',
    'FailureSink',
    'CleanupVerifier',
    'DeliveryEvaluator',
    'CapabilityEvaluator',
    'ReceiptVerifier',
    'SecurityVerifier',
    'DuplicateJsonKey',
    '_valid_target_identity',
    '_target_identity_sha256',
    '_lexical_absolute',
    '_lexically_contained',
    '_portable_parts',
    '_is_link_or_reparse',
    '_path_chain_error',
    '_stable_stat',
    '_stream_file',
    'file_identity',
    '_closed_json_object',
    '_bounded_json_int',
    '_reject_json_number',
    '_validate_json_model',
    '_parse_json_bytes',
    '_read_json_with_identity',
    '_resolve',
    '_existing_cli_path',
    '_prepare_output_path',
    '_read_json',
    '_check_observed_identity',
    '_check_identity',
    '_ordered_unique',
    '_resolve_route_reference',
    '_route_reference_bundle'
]
