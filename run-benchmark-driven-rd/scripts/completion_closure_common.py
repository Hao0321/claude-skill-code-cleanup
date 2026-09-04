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


SKILL_ROOT = Path(os.path.abspath(__file__)).parents[1]
SCOPES = {"internal", "public", "parity"}
CHECK_KINDS = {
    "cleanup-promotion",
    "delivery-contract",
    "capability-ledger",
    "build-receipt",
    "file-identity",
    "json-evidence",
    "security-assessment",
    "route-receipt",
}
SECURITY_CONTROL_IDS = (
    "security.scan-scope",
    "security.scan-coverage",
    "security.scanner-provenance",
    "security.finding-normalization",
    "security.engine-admission",
    "security.adapter-integrity",
)
SECURITY_CAPABILITY_IDS = frozenset(SECURITY_CONTROL_IDS)
SECURITY_SNAPSHOT_PROFILE = "cleanup-security-input/v1"
SECURITY_TARGET_IDENTITY_PROFILE = "cleanup-security-target-identity/v1"
SECURITY_CONTROL_PROFILE = "cleanup-security-control-coverage/v1"
PUBLIC_EXACTLY_ONE_CHECK_KINDS = frozenset({
    "route-receipt",
    "capability-ledger",
    "security-assessment",
    "cleanup-promotion",
    "delivery-contract",
    "build-receipt",
})
PUBLIC_AT_LEAST_ONE_CHECK_KINDS = frozenset({"file-identity"})
TARGET_PRODUCT_MAX_CHARS = 200
TARGET_PRODUCT_MAX_UTF8_BYTES = 512
TARGET_VERSION_MAX_CHARS = 128
TARGET_VERSION_MAX_UTF8_BYTES = 256
MAX_COMPLETION_SECURITY_AGE_SECONDS = 24 * 60 * 60
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SENSITIVE_IDENTITY_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|bearer)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(?:[a-z]:\\Users\\|/Users/|/home/)[^\s\"']+"),
)
MAX_JSON_BYTES = 5 * 1024 * 1024
MIN_JSON_INT = -(1 << 63)
MAX_JSON_INT = (1 << 63) - 1
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100_000
MAX_PORTABLE_PATH_CHARS = 4096
MAX_PORTABLE_COMPONENT_CHARS = 255
READ_CHUNK_BYTES = 1024 * 1024
WINDOWS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul", "clock$", "conin$", "conout$",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
    "com¹", "com²", "com³", "lpt¹", "lpt²", "lpt³",
}
REQUIRED_NEGATIVE_CONTROLS = {
    "missing-required-check",
    "duplicate-check-id",
    "unsafe-path",
    "stale-file-identity",
    "cleanup-not-fresh",
    "cleanup-not-strict",
    "delivery-block",
    "capability-block",
    "capability-obligation-floor",
    "build-receipt-block",
    "evidence-assertion",
    "security-assessment-block",
    "security-assessment-floor",
    "security-assessment-schema",
    "security-assessment-stale",
    "security-assessment-binding",
    "security-assessment-plan",
    "security-assessment-grant",
    "security-assessment-subject",
    "security-capability-binding",
    "security-control-coverage",
    "route-receipt-required",
    "route-receipt-stale",
    "route-profile-stale",
    "route-reference-stale",
    "route-capability-floor",
    "public-route-floor",
    "public-check-kind-floor",
    "public-check-subject",
    "public-artifact-binding",
    "target-identity",
    "legacy-unbound-completion-contract",
}

FailureSink = Callable[..., None]
CleanupVerifier = Callable[[Path], dict[str, Any]]
DeliveryEvaluator = Callable[[dict[str, Any], Path], dict[str, Any]]
CapabilityEvaluator = Callable[[dict[str, Any], Path, dict[str, Any], str], dict[str, Any]]
ReceiptVerifier = Callable[[Path, str], dict[str, Any]]
SecurityVerifier = Callable[[Path, str], dict[str, Any]]


class DuplicateJsonKey(ValueError):
    """Raised when one JSON object repeats an exact key."""


def _valid_target_identity(value: Any, *, max_chars: int, max_utf8_bytes: int) -> bool:
    return bool(
        isinstance(value, str)
        and value
        and value == value.strip()
        and unicodedata.normalize("NFC", value) == value
        and len(value) <= max_chars
        and len(value.encode("utf-8")) <= max_utf8_bytes
        and not any(unicodedata.category(character).startswith("C") for character in value)
        and not any(pattern.search(value) for pattern in SENSITIVE_IDENTITY_PATTERNS)
    )


def _target_identity_sha256(product: str, version: str) -> str:
    return sha256_json({
        "profile": SECURITY_TARGET_IDENTITY_PROFILE,
        "product": product,
        "version": version,
    })


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _lexically_contained(root: Path, candidate: Path) -> bool:
    try:
        common = os.path.commonpath((os.fspath(root), os.fspath(candidate)))
    except ValueError:
        return False
    return os.path.normcase(common) == os.path.normcase(os.fspath(root))


def _portable_parts(
    value: Any, *, allow_one_leading_parent: bool = False,
) -> tuple[tuple[str, ...] | None, str | None]:
    if not isinstance(value, str) or not value or len(value) > MAX_PORTABLE_PATH_CHARS:
        return None, "path must be a bounded non-empty string"
    if "\\" in value or ":" in value or value.startswith("/"):
        return None, "path must be a root-relative POSIX path without ADS or drive syntax"
    if any(unicodedata.category(character).startswith("C") for character in value):
        return None, "path contains control characters"
    parts = tuple(value.split("/"))
    if any(not part or part == "." for part in parts):
        return None, "path contains an empty or dot component"
    parents = [index for index, part in enumerate(parts) if part == ".."]
    if parents and not (allow_one_leading_parent and parents == [0]):
        return None, "path must remain inside its allowed root"
    for part in parts:
        if part == "..":
            continue
        if len(part) > MAX_PORTABLE_COMPONENT_CHARS or part.endswith((".", " ")):
            return None, "path has an overlong or trailing dot/space component"
        device_stem = part.split(".", 1)[0].rstrip(" .").casefold()
        if device_stem in WINDOWS_RESERVED_NAMES:
            return None, "path contains a Windows reserved device name"
    return parts, None


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & reparse_flag
    )


def _path_chain_error(path: Path, *, directory: bool = False) -> str | None:
    candidate = _lexical_absolute(path)
    if not candidate.is_absolute() or not candidate.anchor:
        return "path is not absolute"
    current = Path(candidate.anchor)
    components = candidate.parts[1:]
    for component in components:
        current /= component
        try:
            metadata = os.lstat(current)
        except OSError:
            return "path component is missing or unreadable"
        if _is_link_or_reparse(metadata):
            return "symlink or reparse-point components are not accepted"
    try:
        final_metadata = os.lstat(candidate)
    except OSError:
        return "path is missing or unreadable"
    if _is_link_or_reparse(final_metadata):
        return "symlink or reparse-point paths are not accepted"
    if directory and not stat.S_ISDIR(final_metadata.st_mode):
        return "path is not a directory"
    if not directory and not stat.S_ISREG(final_metadata.st_mode):
        return "path is not a regular file"
    return None


def _stable_stat(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        getattr(metadata, "st_mtime_ns", int(metadata.st_mtime * 1_000_000_000)),
        getattr(metadata, "st_ctime_ns", int(metadata.st_ctime * 1_000_000_000)),
    )


def _stream_file(
    path: Path, *, max_bytes: int | None = None, capture: bool = False,
) -> tuple[bytes | None, dict[str, Any]]:
    path_error = _path_chain_error(path)
    if path_error:
        raise ValueError(path_error)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    chunks: list[bytes] | None = [] if capture else None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or _is_link_or_reparse(before):
            raise ValueError("path is not a regular non-reparse file")
        if max_bytes is not None and before.st_size > max_bytes:
            raise ValueError("file exceeds the byte ceiling")
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            while True:
                chunk = handle.read(READ_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if max_bytes is not None and size > max_bytes:
                    raise ValueError("file exceeds the byte ceiling")
                digest.update(chunk)
                if chunks is not None:
                    chunks.append(chunk)
        after = os.fstat(descriptor)
        if _stable_stat(before) != _stable_stat(after) or size != before.st_size:
            raise ValueError("file changed while it was being read")
        path_metadata = os.lstat(path)
        if _is_link_or_reparse(path_metadata) or (
            path_metadata.st_dev,
            path_metadata.st_ino,
        ) != (after.st_dev, after.st_ino):
            raise ValueError("path identity changed while it was being read")
        path_error = _path_chain_error(path)
        if path_error:
            raise ValueError(path_error)
        payload = b"".join(chunks) if chunks is not None else None
        return payload, {"bytes": size, "sha256": digest.hexdigest()}
    finally:
        os.close(descriptor)


def file_identity(path: Path) -> dict[str, Any]:
    _, identity = _stream_file(path)
    return identity


def _closed_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _bounded_json_int(raw: str) -> int:
    digits = raw[1:] if raw.startswith("-") else raw
    if not digits or len(digits) > 19 or not digits.isascii() or not digits.isdigit():
        raise ValueError("JSON integer token exceeds the signed 64-bit ceiling")
    value = int(raw)
    if not MIN_JSON_INT <= value <= MAX_JSON_INT:
        raise ValueError("JSON integer exceeds the signed 64-bit ceiling")
    return value


def _reject_json_number(_raw: str) -> Any:
    raise ValueError("JSON floats and non-finite numbers are not accepted")


def _validate_json_model(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise ValueError("JSON exceeds the structure ceiling")
        if current is None or isinstance(current, (str, bool)):
            continue
        if isinstance(current, int):
            if not MIN_JSON_INT <= current <= MAX_JSON_INT:
                raise ValueError("JSON integer exceeds the signed 64-bit ceiling")
            continue
        if isinstance(current, float):
            raise ValueError("JSON floats are not accepted")
        if isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
            continue
        if isinstance(current, dict):
            if any(not isinstance(key, str) for key in current):
                raise ValueError("JSON object keys must be strings")
            stack.extend((item, depth + 1) for item in current.values())
            continue
        raise ValueError("value is not in the JSON data model")


def _parse_json_bytes(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("JSON exceeds the byte ceiling")
    value = json.loads(
        raw.decode("utf-8-sig"),
        object_pairs_hook=_closed_json_object,
        parse_int=_bounded_json_int,
        parse_float=_reject_json_number,
        parse_constant=_reject_json_number,
    )
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    _validate_json_model(value)
    return value


def _read_json_with_identity(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw, identity = _stream_file(path, max_bytes=MAX_JSON_BYTES, capture=True)
    assert raw is not None
    return _parse_json_bytes(raw), identity


def _resolve(root: Path, value: Any, *, directory: bool = False) -> tuple[Path | None, str | None]:
    parts, error = _portable_parts(value)
    if error or parts is None:
        return None, error
    lexical_root = _lexical_absolute(root)
    candidate = _lexical_absolute(lexical_root.joinpath(*parts))
    if not _lexically_contained(lexical_root, candidate):
        return None, "path escapes the closure root"
    error = _path_chain_error(candidate, directory=directory)
    if error:
        return None, error
    return candidate, None


def _existing_cli_path(
    root: Path, value: Path, *, directory: bool = False,
) -> tuple[Path | None, str | None]:
    lexical_root = _lexical_absolute(root)
    candidate = _lexical_absolute(value)
    if not _lexically_contained(lexical_root, candidate):
        return None, "path escapes the closure root"
    relative = Path(os.path.relpath(candidate, lexical_root)).as_posix()
    _parts, error = _portable_parts(relative)
    if error:
        return None, error
    error = _path_chain_error(candidate, directory=directory)
    if error:
        return None, error
    return candidate, None


def _prepare_output_path(root: Path, value: Path) -> tuple[Path | None, str | None]:
    lexical_root = _lexical_absolute(root)
    candidate = _lexical_absolute(value)
    if not _lexically_contained(lexical_root, candidate):
        return None, "output escapes the closure root"
    relative = Path(os.path.relpath(candidate, lexical_root)).as_posix()
    parts, error = _portable_parts(relative)
    if error or parts is None:
        return None, error
    current = lexical_root
    for component in parts[:-1]:
        current /= component
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            try:
                os.mkdir(current)
                metadata = os.lstat(current)
            except OSError:
                return None, "output directory cannot be created safely"
        except OSError:
            return None, "output directory is unreadable"
        if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
            return None, "output traverses a non-directory, symlink, or reparse point"
    try:
        final_metadata = os.lstat(candidate)
    except FileNotFoundError:
        return candidate, None
    except OSError:
        return None, "output path is unreadable"
    if _is_link_or_reparse(final_metadata) or not stat.S_ISREG(final_metadata.st_mode):
        return None, "output is not a regular non-reparse file"
    return candidate, None


def _read_json(path: Path) -> dict[str, Any]:
    value, _identity = _read_json_with_identity(path)
    return value


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
