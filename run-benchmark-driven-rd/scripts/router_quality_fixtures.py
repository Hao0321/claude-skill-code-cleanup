#!/usr/bin/env python3
"""Run deterministic task-routing quality fixtures against Router v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import project_profile_gate as router
from router_quality_catalog import (
    BASE_RULES,
    BASE_TOPICS,
    CLASS_SPECS,
    SECURITY_CAPABILITY_IDS,
    UPDATER_SPECS,
    VARIANTS,
    CaseSpec,
    ClassSpec,
)


ROOT = Path(__file__).resolve().parents[1]
ROUTER_PATH = ROOT / "scripts" / "project_profile_gate.py"
PROFILE_PATH = ROOT / "profiles" / "project-modules.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def unique(items: list[str] | tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(items))

def make_contract(spec: ClassSpec, variant: str) -> dict[str, Any]:
    intent = spec.intent
    if spec.task_class == "ambiguous-legacy-fallback" and variant == "near-miss-negative":
        intent = None
    contract: dict[str, Any] = {
        "schemaVersion": 2,
        "autoDetect": variant != "direct-positive",
        "projectTypes": list(spec.project_types),
        "modules": [],
        "stage": spec.stage,
        "artifact": spec.artifact,
        "risk": spec.risk,
        "contextBudgetTokens": 100000,
        "evidenceBindings": {
            "authorization": "audit-only:no-external-or-destructive-mutation",
            "fixture": f"router-quality-corpus:{spec.task_class}:{variant}",
        },
    }
    if intent is not None:
        contract["taskIntent"] = intent
    return contract

def _updater_contracts():
    updater_contracts = (
        {
            "schemaVersion": 2,
            "autoDetect": False,
            "projectTypes": ["software"],
            "modules": [],
            "taskIntent": "secure-self-update",
            "stage": "discovery",
            "artifact": "updater",
            "risk": "low",
            "contextBudgetTokens": 100000,
            "evidenceBindings": {
                "authorization": "discovery-only:no-download-or-execution",
                "fixture": "router-quality-corpus:updater-discovery",
            },
        },
        {
            "schemaVersion": 2,
            "autoDetect": False,
            "projectTypes": ["software"],
            "modules": [],
            "taskIntent": "secure-self-update",
            "stage": "promotion",
            "artifact": "updater",
            "risk": "low",
            "contextBudgetTokens": 100000,
            "evidenceBindings": {
                "authorization": "local-implementation-only:no-external-promotion",
                "fixture": "router-quality-corpus:updater-promotion-floor",
            },
        },
        {
            "schemaVersion": 2,
            "autoDetect": False,
            "projectTypes": ["software"],
            "modules": [],
            "taskIntent": "secure-self-update",
            "stage": "completion",
            "artifact": "updater",
            "risk": "low",
            "contextBudgetTokens": 100000,
            "evidenceBindings": {
                "authorization": "verification-only:retirement-requires-current-user-authorization",
                "fixture": "router-quality-corpus:updater-completion",
            },
        },
    )
    return updater_contracts


def expand_cases() -> list[CaseSpec]:
    cases: list[CaseSpec] = []
    for spec in CLASS_SPECS:
        for variant in VARIANTS:
            fallback_reason = None
            if spec.task_class == "ambiguous-legacy-fallback":
                fallback_reason = (
                    "task-intent-missing"
                    if variant == "near-miss-negative"
                    else "task-intent-ambiguous:mixed"
                )
            cases.append(CaseSpec(
                case_id=f"{spec.task_class}.{variant}",
                task_class=spec.task_class,
                variant=variant,
                contract=make_contract(spec, variant),
                expected_mode=(
                    "legacy-compatible-fallback"
                    if spec.task_class == "ambiguous-legacy-fallback"
                    else "task-aware-v2"
                ),
                expected_fallback_reason=fallback_reason,
                expected_topics=spec.expected_topics,
                required_rules=spec.required_rules,
                forbidden_topics=spec.forbidden_topics,
                expected_effective_risk=(
                    "critical"
                    if "default-updater" in spec.flags and spec.stage == "completion"
                    else "high"
                    if "default-updater" in spec.flags
                    and spec.stage in ("implementation", "promotion")
                    else spec.risk
                ),
                expected_adjustment_rules=(
                    ("rd.updater.safe-client",)
                    if "default-updater" in spec.flags
                    and spec.stage in ("implementation", "promotion", "completion")
                    and spec.risk not in ("high", "critical")
                    else ()
                ),
                max_selected_topics=spec.max_selected_topics,
                cap_policy=spec.cap_policy,
                flags=spec.flags,
            ))
    updater_contracts = _updater_contracts()
    for template, contract in zip(UPDATER_SPECS, updater_contracts):
        cases.append(CaseSpec(**{**template.__dict__, "contract": contract}))
    return cases

def write_fixture_files(project: Path, case: CaseSpec) -> None:
    files: dict[str, str] = {}
    if case.task_class == "mixed-ts-rust-audit":
        files.update({
            "package.json": '{"name":"mixed-fixture","private":true}',
            "Cargo.toml": '[package]\nname = "mixed_fixture"\nversion = "0.0.0"\n',
            "src/index.ts": "export const fixture = true;\n",
            "src/lib.rs": "pub fn fixture() -> bool { true }\n",
        })
    if case.task_class == "mcp-session-ai-skill":
        files.update({
            "SKILL.md": "---\nname: fixture\ndescription: MCP fixture.\n---\n",
            "mcp.fixture.json": '{"transport":"stdio","fixture":true}',
        })
    if case.variant == "near-miss-negative":
        files.update({
            "near-miss/index.html.example": "not a web project marker\n",
            "near-miss/timeline.media.json": '{"kind":"distractor"}',
            "near-miss/benchmark-metrics.old": "stale and irrelevant\n",
        })
    if case.variant == "stale-or-distractor":
        files[".rd/cache/stale-route-receipt.json"] = json.dumps({
            "schemaVersion": 2,
            "profileSha256": "0" * 64,
            "selectedTopicIds": ["media-evidence", "benchmark-metrics"],
            "status": "STALE_FIXTURE_DO_NOT_TRUST",
        }, indent=2)
    for relative, content in files.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

def assertion(
    assertion_id: str,
    passed: bool,
    *,
    expected: Any = None,
    observed: Any = None,
    detail: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": assertion_id,
        "status": "PASS" if passed else "FAIL",
    }
    if expected is not None:
        item["expected"] = expected
    if observed is not None:
        item["observed"] = observed
    if detail:
        item["detail"] = detail
    return item

def not_checked(assertion_id: str, detail: str) -> dict[str, Any]:
    return {"id": assertion_id, "status": "NOT_CHECKED", "detail": detail}

def reference_hashes_are_fresh(route_value: dict[str, Any]) -> tuple[bool, list[str]]:
    mismatches: list[str] = []
    for reference, expected_hash in route_value.get("selectedReferenceHashes", {}).items():
        path = (ROOT / reference).resolve()
        if not path.is_file() or sha256(path) != expected_hash:
            mismatches.append(reference)
    return not mismatches, mismatches

def irrelevant_reference_fragments(case: CaseSpec) -> list[str]:
    if case.expected_mode != "task-aware-v2":
        return []
    fragments = ["references/tooling-and-architecture-gates.md"]
    topics = set(case.expected_topics)
    if "media-evidence" not in topics:
        fragments.append("references/media-artifact-evidence.md")
    if "benchmark-metrics" not in topics:
        fragments.append("references/metrics.md")
    if "completion-detail" not in topics:
        fragments.extend([
            "references/capability-obligations.md",
            "references/completion-closure.md",
        ])
    return fragments

def prepare_case(workspace: Path, case: CaseSpec) -> tuple[Path, Path]:
    project = workspace / "projects" / case.case_id
    project.mkdir(parents=True, exist_ok=True)
    write_fixture_files(project, case)
    contract_path = workspace / "contracts" / f"{case.case_id}.json"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(
        json.dumps(case.contract, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return project, contract_path
