#!/usr/bin/env python3
"""Verify a no-loss router migration without loading archived prose at runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_file(root: Path, raw_path: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
        raise ValueError(f"invalid POSIX relative path: {raw_path!r}")
    rel = Path(raw_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"path escapes root: {raw_path!r}")
    candidate = (root / rel).resolve()
    resolved_root = root.resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"path escapes root: {raw_path!r}") from exc
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError(f"missing or symlinked file: {raw_path!r}")
    return candidate


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def verify(manifest_path: Path, skills_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    files: list[dict[str, Any]] = []
    try:
        manifest = _require_dict(
            json.loads(manifest_path.read_text(encoding="utf-8")), "manifest"
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {"schemaVersion": 1, "status": "BLOCK", "errors": [str(exc)], "files": []}

    if manifest.get("schemaVersion") != 1:
        errors.append("schemaVersion must equal 1")

    seen_ids: set[str] = set()
    resolved_by_id: dict[str, Path] = {}
    for kind, root, entries in (
        ("source", manifest_path.parent, manifest.get("sources")),
        ("current", skills_root, manifest.get("current")),
    ):
        if not isinstance(entries, list) or not entries:
            errors.append(f"{kind}s must be a non-empty array")
            continue
        for index, raw in enumerate(entries):
            try:
                entry = _require_dict(raw, f"{kind}[{index}]")
                identity = entry.get("id")
                if not isinstance(identity, str) or not identity or identity in seen_ids:
                    raise ValueError(f"invalid or duplicate id: {identity!r}")
                seen_ids.add(identity)
                path = _safe_file(root, entry.get("path"))
                data = path.read_bytes()
                actual = _sha256(data)
                expected = entry.get("sha256")
                if not isinstance(expected, str) or actual != expected.lower():
                    raise ValueError(f"sha256 mismatch for {identity}: {actual}")
                text = data.decode("utf-8")
                needles = entry.get("requiredNeedles", [])
                if not isinstance(needles, list) or any(not isinstance(x, str) or not x for x in needles):
                    raise ValueError(f"requiredNeedles invalid for {identity}")
                missing = [needle for needle in needles if needle not in text]
                if missing:
                    raise ValueError(f"missing required needles for {identity}: {missing}")
                resolved_by_id[identity] = path
                files.append(
                    {
                        "id": identity,
                        "kind": kind,
                        "path": path.as_posix(),
                        "bytes": len(data),
                        "sha256": actual,
                    }
                )
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append(str(exc))

    mappings = manifest.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        errors.append("mappings must be a non-empty array")
    else:
        covered_sources: set[str] = set()
        for index, raw in enumerate(mappings):
            try:
                mapping = _require_dict(raw, f"mappings[{index}]")
                source = mapping.get("source")
                destinations = mapping.get("destinations")
                if source not in resolved_by_id:
                    raise ValueError(f"mapping references unknown source: {source!r}")
                if not isinstance(destinations, list) or not destinations:
                    raise ValueError(f"mapping destinations invalid for {source!r}")
                unknown = [item for item in destinations if item not in resolved_by_id]
                if unknown:
                    raise ValueError(f"mapping references unknown destinations: {unknown}")
                covered_sources.add(source)
            except ValueError as exc:
                errors.append(str(exc))
        source_ids = {item["id"] for item in files if item["kind"] == "source"}
        if source_ids - covered_sources:
            errors.append(f"unmapped sources: {sorted(source_ids - covered_sources)}")

    return {
        "schemaVersion": 1,
        "status": "GREEN" if not errors else "BLOCK",
        "manifestSha256": _sha256(manifest_path.read_bytes()),
        "skillsRoot": skills_root.resolve().as_posix(),
        "files": files,
        "errors": errors,
    }


def self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="router-migration-test-") as raw:
        root = Path(raw)
        skills = root / "skills"
        migration = root / "migration"
        (skills / "one").mkdir(parents=True)
        (migration / "source").mkdir(parents=True)
        source = migration / "source" / "old.md"
        current = skills / "one" / "SKILL.md"
        source.write_text("old complete bytes", encoding="utf-8")
        current.write_text("critical rule", encoding="utf-8")
        payload = {
            "schemaVersion": 1,
            "sources": [
                {"id": "old", "path": "source/old.md", "sha256": _sha256(source.read_bytes())}
            ],
            "current": [
                {
                    "id": "new",
                    "path": "one/SKILL.md",
                    "sha256": _sha256(current.read_bytes()),
                    "requiredNeedles": ["critical rule"],
                }
            ],
            "mappings": [{"source": "old", "destinations": ["new"]}],
        }
        manifest = migration / "migration.json"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        green = verify(manifest, skills)["status"] == "GREEN"
        payload["current"][0]["requiredNeedles"] = ["missing"]
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        missing = verify(manifest, skills)["status"] == "BLOCK"
        payload["current"][0]["path"] = "../escape"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        traversal = verify(manifest, skills)["status"] == "BLOCK"
        status = "GREEN" if green and missing and traversal else "BLOCK"
        return {
            "schemaVersion": 1,
            "status": status,
            "cases": {"green": green, "missingNeedle": missing, "traversal": traversal},
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--skills-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        result = self_test()
    else:
        if args.manifest is None:
            parser.error("--manifest is required unless --self-test is used")
        default_root = Path(__file__).resolve().parents[2]
        result = verify(args.manifest.resolve(), (args.skills_root or default_root).resolve())

    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    if not args.quiet:
        sys.stdout.write(rendered)
    return 0 if result["status"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
