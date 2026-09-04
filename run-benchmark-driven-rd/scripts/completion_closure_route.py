"""Route-receipt and external verifier adapters for completion closure."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from project_profile_gate import DEFAULT_PROFILE, compose_route, sha256_json, validate_profile
from run_cleanup_gate import resolve_cleanup_root

from completion_closure_common import *  # noqa: F403


def _check_route_receipt(
    check: dict[str, Any], path: Path, root: Path, check_id: str, fail: FailureSink,
) -> dict[str, Any] | None:
    route, route_identity = _read_json_with_identity(path)
    _check_observed_identity(route_identity, check, check_id, fail)
    if (
        route.get("schemaVersion") != 2
        or route.get("routerVersion") != "2.0"
        or route.get("decision") != "ROUTED"
        or route.get("selectionOnly") is not True
        or route.get("evidenceStatus") != "NOT_EVALUATED"
    ):
        fail("route-receipt-stale", "route receipt is not a current selection-only v2 route", check_id)

    project_root, error = _resolve(root, check.get("projectRoot"), directory=True)
    if error or project_root is None:
        fail("unsafe-path", f"route projectRoot: {error}", check_id)
        return None
    route_root = route.get("projectRoot")
    if (
        not isinstance(route_root, str)
        or _lexical_absolute(Path(route_root)) != project_root
    ):
        fail("route-receipt-stale", "route projectRoot differs from the closure projectRoot", check_id)

    profile, profile_identity = _read_json_with_identity(DEFAULT_PROFILE)
    validate_profile(profile)
    profile_hash = profile_identity["sha256"]
    profile_receipt = route.get("profile") if isinstance(route.get("profile"), dict) else {}
    hashes = route.get("hashes") if isinstance(route.get("hashes"), dict) else {}
    if (
        profile_receipt.get("schemaVersion") != profile.get("schemaVersion")
        or profile_receipt.get("sha256") != profile_hash
        or hashes.get("profileSha256") != profile_hash
    ):
        fail("route-profile-stale", "route was not produced from the current routing profile", check_id)

    contract_hash = hashes.get("contractSha256")
    contract_value = check.get("contract")
    contract_path: Path | None = None
    contract_identity: dict[str, Any] | None = None
    if contract_hash is None:
        if contract_value is not None or "contract" in route:
            fail("route-receipt-stale", "route contract provenance is inconsistent", check_id)
    else:
        contract_path, contract_error = _resolve(root, contract_value)
        if contract_error or contract_path is None:
            fail("route-receipt-stale", f"route contract is missing or unsafe: {contract_error}", check_id)
        else:
            _contract_document, contract_identity = _read_json_with_identity(contract_path)
            live_contract_hash = contract_identity["sha256"]
            route_contract = route.get("contract") if isinstance(route.get("contract"), dict) else {}
            if contract_hash != live_contract_hash or route_contract.get("sha256") != live_contract_hash:
                fail("route-receipt-stale", "route contract hash differs from current bytes", check_id)

    topics = route.get("selectedTopicIds")
    task = route.get("task")
    if not isinstance(topics, list) or any(not isinstance(item, str) or not item for item in topics):
        fail("route-receipt-stale", "route selectedTopicIds is invalid", check_id)
        return None
    if len({item.casefold() for item in topics}) != len(topics):
        fail("route-receipt-stale", "route selectedTopicIds contains duplicates", check_id)
    if not isinstance(task, dict):
        fail("route-receipt-stale", "route task is missing", check_id)
        return None

    replayed = compose_route(
        project_root,
        DEFAULT_PROFILE,
        contract_path,
        task_intent=task.get("intent"),
        stage=task.get("stage"),
        artifact=task.get("artifact"),
        risk=task.get("declaredRisk", task.get("risk")),
        context_budget_tokens=task.get("contextBudgetTokens"),
    )
    if file_identity(DEFAULT_PROFILE) != profile_identity:
        fail("route-profile-stale", "routing profile changed during route replay", check_id)
    if (
        contract_path is not None
        and contract_identity is not None
        and file_identity(contract_path) != contract_identity
    ):
        fail("route-receipt-stale", "route contract changed during route replay", check_id)
    _route_reference_bundle(
        route, "references", "selectedReferenceHashes", "selectedReferencesSha256",
        check_id, fail,
    )
    _route_reference_bundle(
        route, "legacyReferences", "legacyReferenceHashes", "legacyReferencesSha256",
        check_id, fail,
    )
    for field in (
        "projectTypes", "selectedModuleIds", "selectedTopicIds", "references",
        "legacyReferences", "gates", "criticalRuleIds", "projectEvidence",
    ):
        if route.get(field) != replayed.get(field):
            fail("route-receipt-stale", f"route {field} differs from a current replay", check_id)
    replayed_task = replayed["task"]
    expected_update = replayed_task["updateObligation"]
    expected_security = replayed_task["securityAssessmentObligation"]
    expected_bare_task = {key: value for key, value in replayed_task.items() if key != "sources"}
    observed_bare_task = {key: value for key, value in task.items() if key != "sources"}
    if observed_bare_task != expected_bare_task:
        fail("route-receipt-stale", "route task differs from a current replay", check_id)
    if task.get("updateObligation") != expected_update:
        fail("route-receipt-stale", "typed update obligation differs from current profile", check_id)
    if task.get("securityAssessmentObligation") != expected_security:
        fail("route-receipt-stale", "typed security obligation differs from current profile", check_id)

    security_policy = profile["routing"]["defaultSecurityAssessmentObligation"]
    if security_policy["requiredCapabilityObligationIds"] != list(SECURITY_CONTROL_IDS):
        fail("route-profile-stale", "current profile security capability floor drifted", check_id)
    if security_policy["requiredSecurityControlIds"] != list(SECURITY_CONTROL_IDS):
        fail("route-profile-stale", "current profile security control floor drifted", check_id)

    expected_floor = _ordered_unique([
        *expected_update["requiredCapabilityObligationIds"],
        *expected_security["requiredCapabilityObligationIds"],
    ])
    if route.get("requiredCapabilityObligationIds") != expected_floor:
        fail("route-capability-floor", "route capability floor differs from typed obligations", check_id)

    task_sources = task.get("sources")
    if not isinstance(task_sources, dict):
        fail("route-receipt-stale", "route task sources are missing", check_id)
        task_sources = {}
    bare_task = observed_bare_task
    routing_input = {
        "profileSha256": profile_hash,
        "contractSha256": contract_hash,
        "projectRoot": route.get("projectRoot"),
        "projectTypes": route.get("projectTypes"),
        "selectedModuleIds": route.get("selectedModuleIds"),
        "task": bare_task,
        "taskSources": task_sources,
        "routingMode": route.get("routingMode"),
        "fallbackReason": route.get("fallbackReason"),
        "selectedTaskIds": route.get("selectedTaskIds"),
        "selectedTopicIds": topics,
        "topicSelectionReasons": route.get("topicSelectionReasons"),
    }
    if hashes.get("routingInputSha256") != sha256_json(routing_input):
        fail("route-receipt-stale", "route routingInputSha256 is inconsistent", check_id)
    if hashes.get("selectedTopicsSha256") != sha256_json(topics):
        fail("route-receipt-stale", "route selectedTopicsSha256 is inconsistent", check_id)
    return {
        "checkId": check_id,
        "projectRoot": project_root,
        "routingInputSha256": hashes.get("routingInputSha256"),
        "requiredCapabilityObligationIds": expected_floor,
        "requiredSecurityControlIdsSha256": sha256_json(
            expected_security["requiredSecurityControlIds"]
        ),
        "updateRequired": expected_update["required"],
        "securityRequired": expected_security["required"],
        "artifact": replayed_task.get("artifact"),
    }


def _json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("JSON pointer must be empty or begin with /")
    current = document
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        elif isinstance(current, dict):
            current = current[token]
        else:
            raise KeyError(token)
    return current


def default_receipt_verifier(project_root: Path, receipt: str) -> dict[str, Any]:
    cleanup_root = resolve_cleanup_root()
    checker = cleanup_root / "scripts" / "check_build_receipt.py"
    completed = subprocess.run(
        [sys.executable, str(checker), str(project_root), "--receipt", receipt, "--format", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env={**os.environ, "PYTHONUTF8": "1"},
        check=False,
    )
    try:
        report = _parse_json_bytes(completed.stdout.encode("utf-8"))
    except Exception as exc:  # normalized below as measurement evidence
        return {"status": "ERROR", "errors": [str(exc), completed.stderr.strip()]}
    if completed.returncode != 0 and report.get("status") == "GREEN":
        return {"status": "ERROR", "errors": ["receipt checker exited nonzero with GREEN JSON"]}
    return report


def default_security_verifier(project_root: Path, receipt: str) -> dict[str, Any]:
    cleanup_root = resolve_cleanup_root()
    checker = cleanup_root / "scripts" / "check_security_assessment.py"
    completed = subprocess.run(
        [
            sys.executable, str(checker), str(project_root), "--receipt", receipt,
            "--format", "json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env={**os.environ, "PYTHONUTF8": "1"},
        check=False,
    )
    try:
        report = _parse_json_bytes(completed.stdout.encode("utf-8"))
    except Exception as exc:  # normalized below as measurement evidence
        return {"status": "ERROR", "errors": [str(exc), completed.stderr.strip()]}
    expected_exit = {"GREEN": 0, "BLOCK": 1, "NOT_CHECKED": 3}.get(report.get("status"))
    if expected_exit is None or completed.returncode != expected_exit:
        return {
            "status": "ERROR",
            "errors": ["security verifier exit/status contract mismatch"],
        }
    return report


__all__ = [
    '_check_route_receipt',
    '_json_pointer',
    'default_receipt_verifier',
    'default_security_verifier'
]
