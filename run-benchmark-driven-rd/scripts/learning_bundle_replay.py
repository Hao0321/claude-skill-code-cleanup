"""Validate bounded source declarations and isolate the owned calibration provider."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

MAX_SOURCES = 32


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate learning document key")
        result[name] = value
    return result


def read_document(path: Path, limit: int) -> tuple[dict, bytes]:
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("learning document exceeds bounds")
    value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError("learning document is not an object")
    return value, data


def source_rows(index: dict) -> list[dict]:
    sources = index.get("experimentRecordSources")
    if not isinstance(sources, list) or not sources or len(sources) > MAX_SOURCES:
        raise ValueError("sanitized learning record sources are missing or exceed bounds")
    names, identities = set(), set()
    for row in sources:
        if not isinstance(row, dict) or any(not isinstance(row.get(k), str) for k in ("path", "id", "sha256")):
            raise ValueError("invalid learning record source declaration")
        relative = PurePosixPath(row["path"])
        if not row["id"] or len(row["id"]) > 256 or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise ValueError("invalid learning record source identity")
        if relative.is_absolute() or ".." in relative.parts or "\\" in row["path"] or ":" in row["path"]:
            raise ValueError("unsafe learning record source")
        if row["path"].casefold() in names or row["id"] in identities:
            raise ValueError("duplicate learning record source")
        names.add(row["path"].casefold())
        identities.add(row["id"])
    return sources


def isolated_replay(cleanup: Path) -> dict:
    script = cleanup / "scripts/replay_exposure.py"
    before = hashlib.sha256(script.read_bytes()).hexdigest()
    child = subprocess.run([sys.executable, "-I", "-B", str(script)], capture_output=True,
                           timeout=60, check=False)
    if len(child.stdout) > 100_000 or child.returncode != 0 or child.stderr:
        raise ValueError("isolated learning calibration did not complete cleanly")
    result = json.loads(child.stdout.decode("utf-8"), object_pairs_hook=unique_object)
    validate_replay(result, cleanup, before)
    return result


def validate_replay(result: dict, cleanup: Path, entry_hash: str) -> None:
    if not isinstance(result, dict) or result.get("schemaVersion") != 1 or result.get("status") != "PASS":
        raise ValueError("isolated learning calibration was not PASS")
    rows = result["codeIdentity"]["files"]
    expected = {"replay_exposure.py", "exposure_regression.py", "exposure_formats_regression.py",
                "exposure_scope_regression.py", "check_release_exposure.py", "exposure_formats.py", "sync_safety.py"}
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError("invalid learning replay code rows")
    if {r.get("path") for r in rows} != {"scripts/" + p for p in expected} or len(rows) != len(expected):
        raise ValueError("learning replay code membership differs")
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if digest != result["codeIdentity"]["sha256"]:
        raise ValueError("learning replay aggregate identity differs")
    for row in rows:
        if hashlib.sha256((cleanup / row["path"]).read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("learning replay source identity drifted")
        if row["path"] == "scripts/replay_exposure.py" and row["sha256"] != entry_hash:
            raise ValueError("learning replay entry changed during measurement")
    runtime = hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
    if result["environment"]["executableSha256"] != runtime:
        raise ValueError("learning replay interpreter identity differs")
