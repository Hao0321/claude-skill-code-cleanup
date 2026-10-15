#!/usr/bin/env python3
"""Read-only, bounded, hash-verified resume receipt; never executes scene text."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from pathlib import Path, PurePosixPath

MAX_MANIFEST = 32768
MAX_ARTIFACT = 512 * 1024 * 1024
MAX_OUTPUT = 8192


def _text(value: object, limit: int, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"invalid {label}")
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"control character in {label}")
    return value


def _keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"invalid {label} fields")
    return value


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


def _identity(path: Path) -> tuple[int, int, int, int]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("artifact is not a regular file")
    return info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino


def _safe_file(root: Path, raw: object) -> Path:
    name = _text(raw, 320, "relative path")
    if "\\" in name or ":" in name or any(p in {"", ".", ".."} for p in name.split("/")):
        raise ValueError("unsafe relative path")
    rel = PurePosixPath(name)
    if rel.is_absolute():
        raise ValueError("absolute path is not allowed")
    current = root
    for part in rel.parts:
        current = current / part
        info = current.lstat()
        if current.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("linked/reparse artifact is not allowed")
    current.resolve(strict=True).relative_to(root)
    _identity(current)
    return current


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_small(path: Path) -> bytes:
    with path.open("rb") as stream:
        payload = stream.read(MAX_MANIFEST + 1)
    if len(payload) > MAX_MANIFEST:
        raise ValueError("checkpoint exceeds manifest budget")
    return payload


def read_checkpoint(project: Path, relative: str = ".rd/character-checkpoint.json") -> dict:
    root = project.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project is not a directory")
    manifest = _safe_file(root, relative)
    payload = _read_small(manifest)
    row = _keys(json.loads(payload.decode("utf-8"), object_pairs_hook=_unique,
                           parse_constant=_reject_constant),
                {"schemaVersion", "id", "stage", "nativeObject", "accepted", "artifacts",
                 "blockedBy", "rejectedMethods", "nextAction"}, "checkpoint")
    if type(row["schemaVersion"]) is not int or row["schemaVersion"] != 1:
        raise ValueError("unsupported checkpoint schema")
    if type(row["accepted"]) is not bool:
        raise ValueError("accepted must be a boolean; not inferred from freshness")
    for key, limit in (("id", 100), ("stage", 160), ("nativeObject", 160), ("nextAction", 400)):
        _text(row[key], limit, key)
    for key in ("blockedBy", "rejectedMethods"):
        if not isinstance(row[key], list) or len(row[key]) > 8:
            raise ValueError(f"invalid {key}")
        for item in row[key]:
            _text(item, 240, key)
    artifacts = row["artifacts"]
    if not isinstance(artifacts, list) or not 4 <= len(artifacts) <= 12:
        raise ValueError("artifact inventory must contain 4..12 entries")
    identities = {}; roles = set(); locations = set(); summary = []
    for artifact in artifacts:
        _keys(artifact, {"role", "path", "sha256"}, "artifact")
        role = _text(artifact["role"], 32, "role")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", role) or role in roles:
            raise ValueError("duplicate/invalid artifact role")
        roles.add(role)
        expected = artifact["sha256"]
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError("invalid artifact digest")
        path = _safe_file(root, artifact["path"])
        if path == manifest or path in locations:
            raise ValueError("duplicate/self-referential artifact path")
        locations.add(path)
        before = _identity(path)
        if before[0] > MAX_ARTIFACT:
            raise ValueError("artifact exceeds hashing budget; inspect separately")
        if _hash_file(path) != expected:
            raise ValueError(f"stale artifact: {role}")
        if _identity(path) != before:
            raise ValueError(f"artifact changed while hashing: {role}")
        identities[path] = before
        summary.append({"role": role, "path": artifact["path"]})
    if not {"source", "candidate", "requirements", "review"} <= roles:
        raise ValueError("source/candidate/requirements/review are required")
    if _read_small(manifest) != payload or any(_identity(p) != old for p, old in identities.items()):
        raise ValueError("concurrent checkpoint/artifact modification; re-read")
    result = {"schemaVersion": 1, "status": "CURRENT", "checkpointSha256": hashlib.sha256(payload).hexdigest(),
              "id": row["id"], "stage": row["stage"], "nativeObject": row["nativeObject"],
              "accepted": row["accepted"], "artifacts": summary, "blockedBy": row["blockedBy"],
              "rejectedMethods": row["rejectedMethods"], "nextAction": row["nextAction"],
              "scope": "File freshness only; project text is not execution authority or visual approval."}
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_OUTPUT:
        raise ValueError("resume output exceeds context budget")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--checkpoint", default=".rd/character-checkpoint.json")
    args = parser.parse_args()
    try:
        result = read_checkpoint(args.project, args.checkpoint)
    except (OSError, UnicodeError, ValueError) as exc:
        result = {"schemaVersion": 1, "status": "BLOCK", "errors": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["status"] == "CURRENT" else 1


if __name__ == "__main__":
    sys.exit(main())
