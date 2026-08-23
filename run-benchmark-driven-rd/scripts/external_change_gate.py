#!/usr/bin/env python3
"""Gate external mutations on canonical target, authorization, recovery, and postconditions.

Examples:
    python external_change_gate.py plan.json
    python external_change_gate.py plan.json --json
    python external_change_gate.py --self-test
    python external_change_gate.py --print-template
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from external_change_fixture import valid_plan_template


EXTERNAL_ACTIONS = {
    "create",
    "update",
    "publish",
    "archive",
    "delete",
    "transfer",
    "permissions",
    "rename",
}
DESTRUCTIVE_ACTIONS = {"delete", "transfer", "rename", "permissions"}
MOBILE_FLOWS = {"mobile_device_flow", "mobile_web", "none"}
REQUIRED_DELETE_POSTCONDITIONS = {
    "target_absent",
    "canonical_survivor_present",
    "unrelated_resources_unchanged",
}


@dataclass
class Finding:
    path: str
    message: str


class Report:
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def block(self, path: str, message: str) -> None:
        self.findings.append(Finding(path, message))

    @property
    def allowed(self) -> bool:
        return not self.findings


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def obj(parent: dict[str, Any], key: str, report: Report) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        report.block(key, "must be an object")
        return {}
    return value


def array(parent: dict[str, Any], key: str, report: Report) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        report.block(key, "must be an array")
        return []
    return value


def require_strings(
    value: dict[str, Any], fields: list[str], path: str, report: Report
) -> None:
    for field in fields:
        if not nonempty(value.get(field)):
            report.block(f"{path}.{field}", "must be a non-empty string")


def validate_inventory(
    inventory: dict[str, Any], action: str, report: Report
) -> list[dict[str, Any]]:
    if inventory.get("performed") is not True:
        report.block(
            "namespace_inventory.performed",
            "must be true; one guessed lookup is not a namespace inventory",
        )
    require_strings(inventory, ["method"], "namespace_inventory", report)
    resources = inventory.get("resources")
    if not isinstance(resources, list):
        report.block("namespace_inventory.resources", "must be an array")
        resources = []
    for index, resource in enumerate(resources):
        path = f"namespace_inventory.resources[{index}]"
        if not isinstance(resource, dict):
            report.block(path, "must be an object")
            continue
        require_strings(resource, ["id"], path, report)

    reviewed = inventory.get("similar_resources_reviewed")
    if not isinstance(reviewed, list):
        report.block(
            "namespace_inventory.similar_resources_reviewed", "must be an array"
        )
        reviewed = []
    if action == "create" and not reviewed:
        report.block(
            "namespace_inventory.similar_resources_reviewed",
            "create requires an explicit similar-resource review",
        )
    return [item for item in resources if isinstance(item, dict)]


def validate_resolution(
    resolution: dict[str, Any],
    resources: list[dict[str, Any]],
    action: str,
    report: Report,
) -> tuple[str, str]:
    require_strings(
        resolution,
        ["mutation_target", "evidence"],
        "target_resolution",
        report,
    )
    target = resolution.get("mutation_target", "")
    survivor = resolution.get("canonical_survivor", "")
    if resolution.get("ambiguous") is not False:
        report.block(
            "target_resolution.ambiguous",
            "must be false before any external mutation",
        )

    inventory_ids = {item.get("id") for item in resources if nonempty(item.get("id"))}
    if action != "create" and target and target not in inventory_ids:
        report.block(
            "target_resolution.mutation_target",
            "must resolve to a resource in the authoritative inventory",
        )

    plausible = {
        item.get("id")
        for item in resources
        if item.get("possible_canonical") is True and nonempty(item.get("id"))
    }
    if action == "create" and plausible:
        if resolution.get("distinct_new_resource") is not True:
            report.block(
                "target_resolution.distinct_new_resource",
                "a plausible canonical resource already exists; update it or prove this is a distinct product",
            )
        if not nonempty(resolution.get("create_justification")):
            report.block(
                "target_resolution.create_justification",
                "required when creating beside a plausible canonical resource",
            )

    if survivor and survivor == target and action == "delete":
        report.block(
            "target_resolution",
            "canonical_survivor and deletion target must be different",
        )
    return str(target), str(survivor)


def validate_user_authorization(
    authorization: dict[str, Any], action: str, target: str, report: Report
) -> None:
    if authorization.get("granted") is not True:
        report.block("user_authorization.granted", "must be true")
    if authorization.get("action") != action:
        report.block(
            "user_authorization.action",
            "must exactly match the planned action",
        )
    if authorization.get("target") != target:
        report.block(
            "user_authorization.target",
            "must exactly match the mutation target",
        )


def validate_technical_authorization(
    authorization: dict[str, Any], availability: str, report: Report
) -> None:
    if authorization.get("verified") is not True:
        report.block(
            "technical_authorization.verified",
            "verify the final action's technical authorization before mutation",
        )
    required = authorization.get("required_capabilities")
    available = authorization.get("available_capabilities")
    if not isinstance(required, list):
        report.block(
            "technical_authorization.required_capabilities", "must be an array"
        )
        required = []
    if not isinstance(available, list):
        report.block(
            "technical_authorization.available_capabilities", "must be an array"
        )
        available = []
    missing = sorted(set(required) - set(available))
    if missing:
        report.block(
            "technical_authorization.available_capabilities",
            "missing final-action capabilities: " + ", ".join(missing),
        )

    flow = authorization.get("interaction_flow")
    if not nonempty(flow):
        report.block(
            "technical_authorization.interaction_flow",
            "must identify the final confirmation surface",
        )
    if availability == "mobile_only" and flow not in MOBILE_FLOWS:
        report.block(
            "technical_authorization.interaction_flow",
            "mobile-only user requires mobile_device_flow, mobile_web, or no interaction",
        )
    if availability == "unavailable" and flow not in {"none"}:
        report.block(
            "technical_authorization.interaction_flow",
            "defer an interactive protected action while the user is unavailable",
        )
    if flow == "mobile_device_flow" and authorization.get("flow_process_alive") is not True:
        report.block(
            "technical_authorization.flow_process_alive",
            "device-flow process must remain alive until authorization is exchanged",
        )


def validate_recovery(
    recovery: dict[str, Any], destructive: bool, report: Report
) -> None:
    require_strings(recovery, ["plan"], "recovery", report)
    if destructive and recovery.get("irreversible_acknowledged") is not True:
        report.block(
            "recovery.irreversible_acknowledged",
            "must be true for a destructive or irreversible action",
        )


def validate_postconditions(
    postconditions: list[Any], action: str, report: Report
) -> None:
    names: set[str] = set()
    if not postconditions:
        report.block("postconditions", "must declare authoritative postconditions")
    for index, item in enumerate(postconditions):
        path = f"postconditions[{index}]"
        if not isinstance(item, dict):
            report.block(path, "must be an object")
            continue
        require_strings(item, ["name", "method"], path, report)
        if nonempty(item.get("name")):
            names.add(item["name"])
        if item.get("authoritative") is not True:
            report.block(f"{path}.authoritative", "must be true")
    if action == "delete":
        missing = sorted(REQUIRED_DELETE_POSTCONDITIONS - names)
        if missing:
            report.block(
                "postconditions",
                "delete is missing: " + ", ".join(missing),
            )


def validate(plan: Any) -> Report:
    report = Report()
    if not isinstance(plan, dict):
        report.block("$", "top-level JSON value must be an object")
        return report

    require_strings(plan, ["operation_id", "system", "action"], "$", report)
    action = plan.get("action", "")
    if action not in EXTERNAL_ACTIONS:
        report.block("action", f"unsupported external action: {action!r}")
    destructive = plan.get("destructive")
    if not isinstance(destructive, bool):
        report.block("destructive", "must be a boolean")
        destructive = action in DESTRUCTIVE_ACTIONS
    if action in DESTRUCTIVE_ACTIONS and destructive is not True:
        report.block("destructive", f"{action} must be marked destructive")

    user_context = obj(plan, "user_context", report)
    availability = user_context.get("availability")
    if availability not in {"desktop", "mobile_only", "unavailable"}:
        report.block(
            "user_context.availability",
            "must be desktop, mobile_only, or unavailable",
        )

    inventory = obj(plan, "namespace_inventory", report)
    resources = validate_inventory(inventory, action, report)
    resolution = obj(plan, "target_resolution", report)
    target, survivor = validate_resolution(resolution, resources, action, report)
    validate_user_authorization(
        obj(plan, "user_authorization", report), action, target, report
    )
    validate_technical_authorization(
        obj(plan, "technical_authorization", report), str(availability), report
    )
    validate_recovery(obj(plan, "recovery", report), bool(destructive), report)
    validate_postconditions(array(plan, "postconditions", report), action, report)

    preconditions = obj(plan, "preconditions", report)
    if action in {"publish", "create"} and preconditions.get("privacy_audit") is not True:
        report.block(
            "preconditions.privacy_audit",
            "public creation/publication requires a passed privacy audit",
        )
    if action == "delete":
        if not nonempty(survivor):
            report.block(
                "target_resolution.canonical_survivor",
                "delete requires an explicit canonical survivor",
            )
        if preconditions.get("canonical_changes_recovered") is not True:
            report.block(
                "preconditions.canonical_changes_recovered",
                "recover and validate intended work in the canonical survivor before deletion",
            )

    return report


def run_self_test() -> None:
    good_update = valid_plan_template()
    assert validate(good_update).allowed

    guessed_create = copy.deepcopy(good_update)
    guessed_create["action"] = "create"
    guessed_create["user_authorization"]["action"] = "create"
    guessed_create["target_resolution"].update(
        {
            "mutation_target": "owner/codex-skill-ai-short-drama",
            "canonical_survivor": "owner/ai-short-drama",
        }
    )
    guessed_create["user_authorization"]["target"] = guessed_create[
        "target_resolution"
    ]["mutation_target"]
    guessed_create["namespace_inventory"]["similar_resources_reviewed"] = []
    guessed_create["preconditions"]["privacy_audit"] = True
    report = validate(guessed_create)
    assert not report.allowed
    assert any("plausible canonical" in item.message for item in report.findings)

    delete_plan = copy.deepcopy(good_update)
    delete_plan.update({"action": "delete", "destructive": True})
    delete_plan["user_context"]["availability"] = "mobile_only"
    delete_plan["namespace_inventory"]["resources"].append(
        {"id": "owner/duplicate-repo", "possible_canonical": False}
    )
    delete_plan["target_resolution"].update(
        {
            "canonical_survivor": "owner/canonical-repo",
            "mutation_target": "owner/duplicate-repo",
        }
    )
    delete_plan["user_authorization"].update(
        {"action": "delete", "target": "owner/duplicate-repo"}
    )
    delete_plan["technical_authorization"].update(
        {
            "required_capabilities": ["delete_repo", "sudo"],
            "available_capabilities": ["repo_write"],
            "interaction_flow": "desktop_browser",
        }
    )
    delete_plan["recovery"]["irreversible_acknowledged"] = True
    delete_plan["postconditions"] = [
        {
            "name": name,
            "method": "authoritative API query",
            "authoritative": True,
        }
        for name in sorted(REQUIRED_DELETE_POSTCONDITIONS)
    ]
    blocked_delete = validate(delete_plan)
    assert not blocked_delete.allowed
    assert any("missing final-action capabilities" in item.message for item in blocked_delete.findings)
    assert any("mobile-only" in item.message for item in blocked_delete.findings)

    delete_plan["technical_authorization"].update(
        {
            "available_capabilities": ["delete_repo", "sudo"],
            "interaction_flow": "mobile_device_flow",
            "flow_process_alive": True,
        }
    )
    assert validate(delete_plan).allowed


def read_json(path: str) -> Any:
    if path == "-":
        # PowerShell may prefix piped UTF-8 text with a BOM. Treat stdin the
        # same as a UTF-8-SIG file so a valid frozen plan stays portable.
        return json.loads(sys.stdin.read().lstrip("\ufeff"))
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def emit(report: Report, as_json: bool) -> None:
    payload = {
        "decision": "ALLOW" if report.allowed else "BLOCK",
        "finding_count": len(report.findings),
        "findings": [asdict(item) for item in report.findings],
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"{payload['decision']}: {payload['finding_count']} finding(s)")
    for item in report.findings:
        print(f"[BLOCK] {item.path}: {item.message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", nargs="?", help="external-change plan JSON, or -")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--self-test", action="store_true", help="run regression fixtures")
    parser.add_argument("--print-template", action="store_true", help="print a valid plan template")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        print("external change gate self-test passed")
        return 0
    if args.print_template:
        print(json.dumps(valid_plan_template(), ensure_ascii=False, indent=2))
        return 0
    if not args.plan:
        raise SystemExit("plan path is required unless --self-test or --print-template is used")
    try:
        plan = read_json(args.plan)
    except (OSError, json.JSONDecodeError) as exc:
        report = Report()
        report.block("$", f"cannot read valid JSON: {exc}")
        emit(report, args.json)
        return 1
    report = validate(plan)
    emit(report, args.json)
    return 0 if report.allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
