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
LEDGER_REPLACE_TIMEOUT_SECONDS = 2.0
RESULTS = ("pass", "fail", "inconclusive", "blocked")
FAILURE_TYPES = (
    "algorithm",
    "data",
    "runtime",
    "integration",
    "measurement",
    "product",
    "target-resolution",
    "authorization",
)
PROMOTION_STATES = (
    "raw",
    "provisional",
    "candidate",
    "promoted",
    "active",
    "core",
    "rejected",
    "retired",
)
EVIDENCE_STATES = ("raw", "unmeasured", "diagnostic", "measured", "verified")
SCOPES = ("project-local", "cross-project", "shared-core")
PRIVACY_LEVELS = ("private", "sanitized", "public")
_RECORD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _windows_sharing_error(error: OSError) -> bool:
    return (
        os.name == "nt"
        and isinstance(error, PermissionError)
        and (
            getattr(error, "winerror", None) in {5, 32}
            or error.errno in {errno.EACCES, errno.EPERM}
        )
    )


class LedgerLockTimeout(TimeoutError):
    """Raised when the bounded generated-view lock cannot be acquired."""


class LedgerLock(AbstractContextManager["LedgerLock"]):
    """A bounded advisory byte lock implemented with Python's platform APIs.

    The lock file is intentionally persistent. The operating system releases the
    byte lock if a writer exits unexpectedly, avoiding unsafe stale-file deletion.
    """

    def __init__(self, path: Path, timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS) -> None:
        if timeout <= 0:
            raise ValueError("lock timeout must be positive")
        self.path = path
        self.timeout = timeout
        self._handle: BinaryIO | None = None
        self._locked = False
        self._owner_token: str | None = None

    def __enter__(self) -> "LedgerLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = self.path.open("x+b")
        except FileExistsError:
            handle = self.path.open("r+b")
        self._handle = handle
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
            os.fsync(handle.fileno())

        deadline = time.monotonic() + self.timeout
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._locked = True
                self._owner_token = f"{os.getpid()}:{uuid4().hex}"
                handle.seek(1)
                handle.truncate()
                handle.write(self._owner_token.encode("ascii"))
                handle.flush()
                os.fsync(handle.fileno())
                self.assert_owned()
                return self
            except OSError as error:
                if time.monotonic() >= deadline:
                    handle.close()
                    self._handle = None
                    raise LedgerLockTimeout(
                        f"timed out after {self.timeout:g}s waiting for {self.path}"
                    ) from error
                time.sleep(0.01)

    def assert_owned(self) -> None:
        handle, token = self._handle, self._owner_token
        if handle is None or not self._locked or token is None:
            raise RuntimeError(f"ledger lock is not owned: {self.path}")
        handle.seek(1)
        if handle.read().decode("ascii", errors="replace") != token:
            raise RuntimeError(f"ledger lock ownership changed unexpectedly: {self.path}")

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        handle = self._handle
        try:
            if handle is not None and self._locked:
                self.assert_owned()
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._locked = False
            self._owner_token = None
            if handle is not None:
                handle.close()
            self._handle = None


def experiment_id(now: datetime, nonce: str | None = None) -> str:
    """Return a sortable, collision-resistant experiment identifier."""
    token = nonce or uuid4().hex
    return f"{now.strftime('exp-%Y%m%dT%H%M%S%fZ')}-{token}"


def experiments_dir(project: str | Path) -> Path:
    return Path(project).resolve() / ".rd" / "experiments"


def records_dir(project: str | Path) -> Path:
    return experiments_dir(project) / "records"


def ledger_path(project: str | Path) -> Path:
    return experiments_dir(project) / "ledger.jsonl"


def ledger_lock_path(project: str | Path) -> Path:
    return experiments_dir(project) / ".ledger.lock"


def _validate_record_id(value: object) -> str:
    if not isinstance(value, str) or not _RECORD_ID.fullmatch(value):
        raise ValueError("experiment id must be a path-safe 1-160 character string")
    return value


def _json_bytes(value: object) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"experiment record is not canonical JSON: {error}") from error
    return (text + "\n").encode("utf-8")


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY)
        os.fsync(descriptor)
    except OSError:
        # The record and view files were already fsynced. Some filesystems do not
        # permit directory fsync, so this best-effort durability step is optional.
        pass
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _publish_record_exclusive(directory: Path, entry: dict[str, object]) -> Path:
    """Atomically publish a complete record without ever replacing an ID."""
    record_id = _validate_record_id(entry.get("id"))
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{record_id}.json"
    temporary = directory / f".{record_id}.{uuid4().hex}.tmp"
    payload = _json_bytes(entry)

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
        try:
            # A hard-link publish is atomic and fails if the canonical ID exists.
            # Unlike os.replace/os.rename on POSIX, it can never overwrite a record.
            os.link(temporary, target)
        except FileExistsError:
            raise FileExistsError(f"immutable experiment record already exists: {target}")
        except OSError as error:
            if target.exists():
                raise FileExistsError(f"immutable experiment record already exists: {target}") from error
            raise OSError(
                f"filesystem cannot atomically publish immutable record {target}: {error}"
            ) from error
        _fsync_directory(directory)
        return target
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid experiment record {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"experiment record must be an object: {path}")
    return value


def load_records(project: str | Path) -> list[dict[str, object]]:
    """Read the immutable authority in deterministic ledger order."""
    directory = records_dir(project)
    if not directory.exists():
        return []
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.json"), key=lambda item: item.name.casefold()):
        entry = _read_json_object(path)
        record_id = _validate_record_id(entry.get("id"))
        if path.name != f"{record_id}.json":
            raise ValueError(f"record filename/id mismatch: {path}")
        folded = record_id.casefold()
        if folded in seen:
            raise ValueError(f"case-insensitive duplicate experiment id: {record_id}")
        seen.add(folded)
        records.append(entry)

    def sort_key(entry: dict[str, object]) -> tuple[str, str]:
        recorded_at = entry.get("recordedAt")
        return (
            recorded_at if isinstance(recorded_at, str) else "",
            str(entry["id"]),
        )

    return sorted(records, key=sort_key)


def _migrate_legacy_view(project: str | Path) -> None:
    """Import pre-v2 JSONL rows once, without rewriting or discarding them."""
    path = ledger_path(project)
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError(f"cannot read legacy ledger {path}: {error}") from error
    directory = records_dir(project)
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid legacy ledger row {path}:{line_number}: {error}") from error
        if not isinstance(entry, dict):
            raise ValueError(f"legacy ledger row must be an object: {path}:{line_number}")
        record_id = _validate_record_id(entry.get("id"))
        target = directory / f"{record_id}.json"
        if target.exists():
            canonical = _read_json_object(target)
            if canonical != entry:
                raise ValueError(
                    f"legacy ledger conflicts with immutable record {record_id} at line {line_number}"
                )
            continue
        _publish_record_exclusive(directory, entry)


def _atomic_write_ledger(project: str | Path, entries: list[dict[str, object]]) -> Path:
    path = ledger_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    payload = b"".join(_json_bytes(entry) for entry in entries)
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
        _replace_ledger_view(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return path


def _replace_ledger_view(source: Path, target: Path) -> None:
    """Atomically replace a Windows view despite short reader sharing windows."""
    deadline = time.monotonic() + LEDGER_REPLACE_TIMEOUT_SECONDS
    delay = 0.002
    while True:
        try:
            os.replace(source, target)
            return
        except OSError as error:
            if not _windows_sharing_error(error):
                raise
            if time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.05)


def append_entry(
    project: str | Path,
    entry: dict[str, object],
    *,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> Path:
    """Publish one immutable record and atomically regenerate ledger.jsonl.

    The function keeps its original return contract (the JSONL path) and accepts
    legacy-shaped dictionaries. CLI-created records always use schema v2.
    """
    if not isinstance(entry, dict):
        raise TypeError("entry must be a JSON object")
    _validate_record_id(entry.get("id"))
    # Validate serializability before taking the cross-process lock.
    _json_bytes(entry)
    with LedgerLock(ledger_lock_path(project), timeout=lock_timeout) as lock:
        lock.assert_owned()
        _migrate_legacy_view(project)
        lock.assert_owned()
        _publish_record_exclusive(records_dir(project), entry)
        lock.assert_owned()
        return _atomic_write_ledger(project, load_records(project))


def rebuild_ledger(
    project: str | Path,
    *,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> Path:
    """Import any legacy rows and reproduce the JSONL view from authority."""
    with LedgerLock(ledger_lock_path(project), timeout=lock_timeout) as lock:
        lock.assert_owned()
        _migrate_legacy_view(project)
        lock.assert_owned()
        return _atomic_write_ledger(project, load_records(project))
