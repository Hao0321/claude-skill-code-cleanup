#!/usr/bin/env python3
"""Compose a project-specific R&D route from reusable product modules."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "profiles" / "project-modules.json"
MODE_ORDER = {"a": 0, "b": 1, "architecture": 2, "all": 3}


class ProfileError(ValueError):
    """Raised when a project composition contract is invalid."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProfileError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProfileError(f"JSON root must be an object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_profile(profile: dict[str, Any]) -> None:
    if profile.get("schemaVersion") != 1:
        raise ProfileError("unsupported project module schema")
    project_types = profile.get("projectTypes")
    overlays = profile.get("overlayModules")
    modules = profile.get("modules")
    if not isinstance(project_types, list) or not all(isinstance(item, str) for item in project_types):
        raise ProfileError("projectTypes must be a string list")
    if not isinstance(overlays, list) or not all(isinstance(item, str) for item in overlays):
        raise ProfileError("overlayModules must be a string list")
    if not isinstance(modules, dict) or "core" not in modules or "cleanup" not in modules:
        raise ProfileError("modules must contain core and cleanup")
    allowed = {"core", "cleanup", *project_types, *overlays}
    if set(modules) != allowed:
        raise ProfileError("module registry and declared project/overlay names must match exactly")
    for name, module in modules.items():
        if not isinstance(module, dict):
            raise ProfileError(f"module {name} must be an object")
        if module.get("cleanupMode") not in MODE_ORDER:
            raise ProfileError(f"module {name} has invalid cleanupMode")
        for field in ("references", "gates"):
            values = module.get(field)
            if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
                raise ProfileError(f"module {name}.{field} must be a non-empty string list")


def package_dependencies(root: Path) -> set[str]:
    path = root / "package.json"
    if not path.is_file():
        return set()
    try:
        package = load_json(path)
    except ProfileError:
        return set()
    names: set[str] = set()
    for field in ("dependencies", "devDependencies"):
        values = package.get(field, {})
        if isinstance(values, dict):
            names.update(str(name).lower() for name in values)
    return names


def detect_project_types(root: Path) -> tuple[list[str], dict[str, list[str]]]:
    evidence: dict[str, list[str]] = {}

    def mark(kind: str, markers: list[str]) -> None:
        present = [marker for marker in markers if (root / marker).exists()]
        if present:
            evidence[kind] = present

    mark("skill", ["SKILL.md"])
    mark("game", ["project.godot", "ProjectSettings", "Config/DefaultEngine.ini"])
    mark("database", ["prisma/schema.prisma", "migrations", "schema.sql", "alembic.ini"])
    mark("software", ["pyproject.toml", "setup.py", "Cargo.toml", "CMakeLists.txt"])
    web_markers = ["index.html", "vite.config.js", "vite.config.ts", "next.config.js", "next.config.mjs"]
    web_deps = {"next", "react", "vue", "svelte", "@angular/core", "vite"}
    present_web = [marker for marker in web_markers if (root / marker).exists()]
    dependencies = package_dependencies(root)
    if present_web or dependencies.intersection(web_deps):
        evidence["web"] = present_web + sorted(dependencies.intersection(web_deps))
    if not evidence:
        evidence["software"] = ["fallback:no-specialized-marker"]
    ordered = [kind for kind in ("skill", "web", "database", "game", "software") if kind in evidence]
    return ordered, evidence


def validate_contract(contract: dict[str, Any], profile: dict[str, Any]) -> None:
    if contract.get("schemaVersion") != 1:
        raise ProfileError("unsupported project contract schema")
    if not isinstance(contract.get("autoDetect", True), bool):
        raise ProfileError("autoDetect must be boolean")
    allowed_types = set(profile["projectTypes"])
    allowed_overlays = set(profile["overlayModules"])
    for field, allowed in (("projectTypes", allowed_types), ("modules", allowed_overlays)):
        values = contract.get(field, [])
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ProfileError(f"{field} must be a string list")
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ProfileError(f"unknown {field}: {', '.join(unknown)}")


def unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def compose_route(
    root: Path,
    profile_path: Path = DEFAULT_PROFILE,
    contract_path: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ProfileError(f"project root is not a directory: {root}")
    profile = load_json(profile_path)
    validate_profile(profile)
    contract = {"schemaVersion": 1, "autoDetect": True, "projectTypes": [], "modules": []}
    if contract_path:
        contract = load_json(contract_path)
    validate_contract(contract, profile)
    detected, detection_evidence = detect_project_types(root)
    project_types = list(contract.get("projectTypes", []))
    if contract.get("autoDetect", True):
        project_types = unique(project_types + detected)
    if not project_types:
        project_types = ["software"]
    selected = unique(["core", "cleanup", *project_types, *contract.get("modules", [])])
    modules = profile["modules"]
    references = unique([item for name in selected for item in modules[name]["references"]])
    gates = unique([item for name in selected for item in modules[name]["gates"]])
    cleanup_mode = max((modules[name]["cleanupMode"] for name in selected), key=MODE_ORDER.get)
    return {
        "schemaVersion": 1,
        "decision": "ROUTED",
        "projectRoot": str(root),
        "projectTypes": project_types,
        "selectedModules": selected,
        "detectionEvidence": detection_evidence,
        "cleanup": {
            "provider": "code-cleanup-helper",
            "adapter": "scripts/run_cleanup_gate.py",
            "mode": cleanup_mode,
            "promotionReviewPolicy": "block"
        },
        "references": references,
        "gates": gates,
        "memory": {
            "projectLocal": ".rd/experiments/ledger.jsonl",
            "sharedPromotionRule": "Only anonymized, replayable, cross-project learning may change the shared Skills."
        },
        "profile": {
            "schemaVersion": profile["schemaVersion"],
            "sha256": sha256(profile_path)
        }
    }


def run_self_test() -> None:
    profile = load_json(DEFAULT_PROFILE)
    validate_profile(profile)
    fixtures = {
        "skill": ("SKILL.md", "---\nname: fixture\n---\n"),
        "web": ("package.json", '{"dependencies":{"next":"1"}}'),
        "database": ("schema.sql", "create table t(id int);"),
        "game": ("project.godot", "[application]"),
        "software": ("pyproject.toml", "[project]\nname='fixture'\n")
    }
    with tempfile.TemporaryDirectory(prefix="project-profile-gate-") as raw:
        base = Path(raw)
        for kind, (relative, content) in fixtures.items():
            root = base / kind
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            route = compose_route(root)
            assert kind in route["projectTypes"]
            assert kind in route["selectedModules"]
            assert route["cleanup"]["provider"] == "code-cleanup-helper"
        combined = base / "combined"
        combined.mkdir()
        contract = combined / "project.json"
        contract.write_text(json.dumps({
            "schemaVersion": 1,
            "autoDetect": False,
            "projectTypes": ["web", "database"],
            "modules": ["public-release", "security"]
        }), encoding="utf-8")
        route = compose_route(combined, contract_path=contract)
        assert route["cleanup"]["mode"] == "all"
        assert route["selectedModules"] == ["core", "cleanup", "web", "database", "public-release", "security"]
        invalid = combined / "invalid.json"
        invalid.write_text(json.dumps({
            "schemaVersion": 1,
            "projectTypes": ["unknown"],
            "modules": []
        }), encoding="utf-8")
        try:
            compose_route(combined, contract_path=invalid)
        except ProfileError:
            pass
        else:
            raise AssertionError("unknown project type was accepted")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        print("project profile gate self-test passed")
        return 0
    if args.quiet and not args.output:
        raise SystemExit("--quiet requires --output")
    route = compose_route(args.project, args.profile, args.contract)
    payload = json.dumps(route, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    if not args.quiet:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
