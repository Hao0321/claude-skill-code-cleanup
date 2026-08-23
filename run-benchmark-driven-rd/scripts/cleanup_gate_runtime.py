#!/usr/bin/env python3
"""Provider discovery and full-Skill revision helpers for the Cleanup adapter."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


class MeasurementError(RuntimeError):
    """An evaluator or revision provider failed its machine contract."""


def normalized_path(value: str | Path) -> str:
    return os.path.normcase(str(Path(value).resolve()))


def resolve_cleanup_root(provider_files: Iterable[str], explicit: Path | None = None) -> Path:
    required = tuple(provider_files)
    if explicit:
        root = explicit.resolve()
        if all((root / "scripts" / name).is_file() for name in required):
            return root
        raise MeasurementError(f"explicit code-cleanup-helper provider is invalid: {root}")
    candidates: list[Path] = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        candidates.append(Path(codex_home) / "skills" / "code-cleanup-helper")
    candidates.extend(
        [
            Path(__file__).resolve().parents[2] / "code-cleanup-helper",
            Path.home() / ".codex" / "skills" / "code-cleanup-helper",
        ]
    )
    for candidate in candidates:
        root = candidate.resolve()
        if all((root / "scripts" / name).is_file() for name in required):
            return root
    checked = ", ".join(str(item.resolve()) for item in candidates)
    raise MeasurementError(f"code-cleanup-helper provider not found; checked: {checked}")


def resolve_active_cleanup_root(provider_files: Iterable[str], explicit: Path | None = None) -> Path:
    active = resolve_cleanup_root(provider_files)
    if explicit and normalized_path(explicit) != normalized_path(active):
        raise MeasurementError(
            "--cleanup-root must resolve to the current active private code-cleanup-helper: "
            f"expected {active}, got {explicit.resolve()}"
        )
    return active


def digest_files(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        if not path.is_file():
            raise MeasurementError(f"evaluator file missing: {path}")
        try:
            label = path.relative_to(root).as_posix()
        except ValueError:
            label = path.name
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate_skill_revision_snapshot(snapshot: Any) -> None:
    expected_fields = {"algorithm", "roots", "files", "bytes", "sha256"}
    if not isinstance(snapshot, dict) or set(snapshot) != expected_fields:
        raise MeasurementError("Skill revision snapshot has an unsupported shape")
    if snapshot.get("algorithm") != "skill-revision-sha256-v1":
        raise MeasurementError("Skill revision snapshot uses an unsupported algorithm")
    roots, files, byte_count, sha256 = (
        snapshot.get("roots"), snapshot.get("files"), snapshot.get("bytes"), snapshot.get("sha256")
    )
    if not isinstance(roots, int) or isinstance(roots, bool) or roots < 1:
        raise MeasurementError("Skill revision snapshot roots must be a positive integer")
    if not isinstance(files, int) or isinstance(files, bool) or files < roots:
        raise MeasurementError("Skill revision snapshot files must cover every root")
    if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
        raise MeasurementError("Skill revision snapshot bytes must be a non-negative integer")
    if not isinstance(sha256, str) or len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise MeasurementError("Skill revision snapshot sha256 is invalid")


def capture_skill_revision(
    cleanup_root: Path, skill_root: Path, expected_sha256: str | None = None
) -> dict[str, Any]:
    gate = cleanup_root / "scripts" / "check_skill_revision.py"
    with tempfile.TemporaryDirectory(prefix="skill-revision-contract-") as raw:
        output = Path(raw) / "revision.json"
        completed = subprocess.run(
            [sys.executable, str(gate), "capture", "--root", str(skill_root.resolve()),
             "--output", str(output), "--quiet"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            env={**os.environ, "PYTHONUTF8": "1"},
            check=False,
        )
        if completed.returncode != 0 or not output.is_file():
            detail = (completed.stderr or completed.stdout).strip()
            raise MeasurementError(f"Skill revision gate failed with exit {completed.returncode}: {detail}")
        try:
            result = json.loads(output.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MeasurementError(f"Skill revision gate returned invalid evidence: {exc}") from exc
    roots = result.get("roots") if isinstance(result, dict) else None
    snapshot = result.get("snapshot") if isinstance(result, dict) else None
    if (
        result.get("schemaVersion") != 1
        or result.get("status") != "CAPTURED"
        or not isinstance(roots, list)
        or len(roots) != 1
        or normalized_path(roots[0].get("root", "")) != normalized_path(skill_root)
    ):
        raise MeasurementError("Skill revision gate returned an unsupported canonical-root contract")
    validate_skill_revision_snapshot(snapshot)
    if expected_sha256 and snapshot.get("sha256") != expected_sha256:
        raise MeasurementError(
            f"Skill revision changed during evaluation: {expected_sha256} -> {snapshot.get('sha256')}"
        )
    return snapshot
