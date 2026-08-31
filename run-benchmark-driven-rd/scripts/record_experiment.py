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


def _test_legacy_compatibility() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        # Preserve the old direct-Python API and prove the JSONL file is a view.
        entries = [{"id": "exp-one"}, {"id": "exp-two"}]
        for entry in entries:
            path = append_entry(temp_dir, entry)
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert rows == entries
        assert len(list(records_dir(temp_dir).glob("*.json"))) == 2
        try:
            append_entry(temp_dir, {"id": "exp-one"})
        except FileExistsError:
            pass
        else:
            raise AssertionError("immutable experiment id was overwritten")
        assert [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] == entries

    with tempfile.TemporaryDirectory() as temp_dir:
        # A first v2 writer must migrate, not forget, the pre-v2 JSONL authority.
        old = {"id": "exp-legacy", "learning": "preserve me"}
        old_path = ledger_path(temp_dir)
        old_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.write_bytes(_json_bytes(old))
        append_entry(temp_dir, {"id": "exp-current"})
        migrated = [json.loads(line) for line in old_path.read_text(encoding="utf-8").splitlines()]
        assert migrated == [{"id": "exp-current"}, old]
        assert len(list(records_dir(temp_dir).glob("*.json"))) == 2


def _writer_command(temp_dir: str, index: int) -> list[str]:
    return [
        sys.executable,
        "-X",
        "utf8",
        str(Path(__file__).resolve()),
        "--project",
        temp_dir,
        "--hypothesis",
        f"writer-{index}",
        "--change",
        "old-cli-compatible",
        "--result",
        "pass",
        "--evidence",
        f"evidence-{index}.json",
        "--learning",
        f"learning-{index}",
    ]


def _test_concurrent_writers() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        processes: list[subprocess.Popen[str]] = []
        for index in range(32):
            processes.append(
                subprocess.Popen(
                    _writer_command(temp_dir, index),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
            )
        deadline = time.monotonic() + 60.0
        failures: list[str] = []
        snapshots = 0
        try:
            while any(process.poll() is None for process in processes):
                live_view = ledger_path(temp_dir)
                if live_view.exists():
                    try:
                        live_text = live_view.read_text(encoding="utf-8")
                    except OSError as error:
                        if _windows_sharing_error(error):
                            if time.monotonic() >= deadline:
                                raise TimeoutError("reader sharing retry exceeded 60 seconds") from error
                            time.sleep(0.002)
                            continue
                        raise
                    live_rows = [json.loads(line) for line in live_text.splitlines() if line.strip()]
                    live_ids = [row["id"] for row in live_rows]
                    assert len(live_ids) == len(set(live_ids))
                    snapshots += 1
                if time.monotonic() >= deadline:
                    raise TimeoutError("32-writer fixture exceeded 60 seconds")
                time.sleep(0.002)
            for process in processes:
                remaining = max(0.1, deadline - time.monotonic())
                stdout, stderr = process.communicate(timeout=remaining)
                if process.returncode != 0:
                    failures.append(f"exit={process.returncode} stdout={stdout!r} stderr={stderr!r}")
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        assert not failures, failures

        canonical = load_records(temp_dir)
        ledger_rows = [
            json.loads(line)
            for line in ledger_path(temp_dir).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        record_ids = [str(row["id"]) for row in canonical]
        required_v2_fields = {
            "schemaVersion",
            "topic",
            "scope",
            "privacy",
            "applicability",
            "exclusions",
            "ruleIds",
            "fixtureIds",
            "promotionState",
            "evidenceState",
            "expiresOn",
            "nextDecision",
            "environmentIdentity",
            "datasetIdentity",
        }
        assert len(canonical) == 32
        assert snapshots > 0
        assert len(set(record_ids)) == 32
        assert ledger_rows == canonical
        assert all(row.get("schemaVersion") == SCHEMA_VERSION for row in canonical)
        assert all(required_v2_fields.issubset(row) for row in canonical)
        assert {"target-resolution", "authorization"}.issubset(FAILURE_TYPES)
        assert not list(records_dir(temp_dir).glob(".*.tmp"))


def run_self_test() -> None:
    fixed = datetime(2026, 8, 13, 3, 5, 59, 123456, tzinfo=timezone.utc)
    assert experiment_id(fixed, "first") != experiment_id(fixed, "second")
    _test_legacy_compatibility()
    _test_concurrent_writers()


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
