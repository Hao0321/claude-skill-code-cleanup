#!/usr/bin/env python3
"""Validate live browser evidence, geometry, interaction, and dialog controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable


REQUIRED_NEGATIVE_CONTROLS = {
    "background-scroll-unlocked", "console-error", "dialog-behind-backdrop",
    "dialog-focus-escape", "dialog-initial-focus", "dialog-name-missing",
    "dialog-not-modal", "dialog-not-painted", "dialog-offscreen",
    "escape-close-failed", "focus-not-restored", "horizontal-overflow",
    "input-focus-zoom", "provenance-drift", "task-incomplete", "undersized-control",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
Fail = Callable[..., None]


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("path must be a non-empty repo-relative POSIX string")
    pure = PurePosixPath(value)
    if pure.is_absolute() or "." in pure.parts or ".." in pure.parts or (pure.parts and ":" in pure.parts[0]):
        raise ValueError("path must remain inside the evidence root")
    path = root.joinpath(*pure.parts)
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("path escapes the evidence root") from exc
    return path


def _live_identity(identity: Any, root: Path | None, role: str, fail: Fail, inventory: list[dict[str, Any]]) -> Path | None:
    if root is None:
        fail("evidence-root-missing", "live evidence root is required", role=role)
        return None
    if not isinstance(identity, dict):
        fail("evidence-identity", "evidence identity must be an object", role=role)
        return None
    try:
        path = _safe_path(root, identity.get("path"))
    except ValueError as exc:
        fail("evidence-path", str(exc), role=role)
        return None
    expected_bytes, expected_hash = identity.get("bytes"), identity.get("sha256")
    if not isinstance(expected_bytes, int) or isinstance(expected_bytes, bool) or expected_bytes < 1:
        fail("evidence-identity", "evidence bytes must be a positive integer", role=role, path=identity.get("path"))
        return None
    if not isinstance(expected_hash, str) or not SHA256.fullmatch(expected_hash):
        fail("evidence-identity", "evidence sha256 must be lowercase hexadecimal", role=role, path=identity.get("path"))
        return None
    if path.is_symlink() or not path.is_file():
        fail("evidence-file", "evidence must be a regular non-symlink file", role=role, path=identity.get("path"))
        return None
    actual_bytes, actual_hash = path.stat().st_size, _sha256(path)
    inventory.append({"role": role, "path": identity["path"], "bytes": actual_bytes, "sha256": actual_hash})
    if actual_bytes != expected_bytes or actual_hash != expected_hash:
        fail("evidence-stale", "live evidence identity differs from the contract", role=role, path=identity["path"], expectedBytes=expected_bytes, actualBytes=actual_bytes, expectedSha256=expected_hash, actualSha256=actual_hash)
        return None
    return path


def _validate_header(document: dict[str, Any], fail: Fail) -> tuple[list[str], list[str]]:
    if document.get("schemaVersion") != 2:
        fail("schema-version", "schemaVersion must be 2")
    for field in ("product", "productVersion", "buildId", "datasetId", "browser"):
        if not isinstance(document.get(field), str) or not document[field].strip():
            fail("missing-provenance", f"{field} must be a non-empty string", field=field)
    required_matrix, required_dialogs = document.get("requiredMatrixIds"), document.get("requiredDialogIds")
    for field, value in (("requiredMatrixIds", required_matrix), ("requiredDialogIds", required_dialogs)):
        if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
            fail("closed-world-list", f"{field} must be a non-empty string array", field=field)
        elif len(set(value)) != len(value):
            fail("duplicate-required-id", f"{field} contains duplicates", field=field)
    return required_matrix if isinstance(required_matrix, list) else [], required_dialogs if isinstance(required_dialogs, list) else []


def _validate_control(control: Any, matrix_id: str, fail: Fail) -> str | None:
    if not isinstance(control, dict) or not isinstance(control.get("name"), str) or not control["name"].strip():
        fail("invalid-control", "primaryControls entries need a name", matrixId=matrix_id)
        return None
    if control.get("measured") is not True or not _positive_number(control.get("width")) or not _positive_number(control.get("height")):
        fail("unmeasured-control", "control needs measured positive geometry", matrixId=matrix_id, control=control.get("name"))
        return control["name"]
    if control["width"] < 44 or control["height"] < 44:
        exception = control.get("exception") if isinstance(control.get("exception"), dict) else {}
        if not isinstance(exception.get("reason"), str) or not exception["reason"].strip():
            fail("undersized-control", "custom product controls must be at least 44x44 CSS px or carry an explicit exception", matrixId=matrix_id, control=control["name"], width=control["width"], height=control["height"])
    return control["name"]


def _validate_matrix(item: Any, document: dict[str, Any], fail: Fail) -> str | None:
    if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
        fail("invalid-matrix", "matrix entry is missing id")
        return None
    matrix_id = item["id"]
    if item.get("buildId") != document.get("buildId") or item.get("datasetId") != document.get("datasetId"):
        fail("provenance-drift", "matrix entry does not share the frozen build and dataset", matrixId=matrix_id)
    if not isinstance(item.get("route"), str) or not item["route"].strip():
        fail("route-missing", "matrix entry needs a route", matrixId=matrix_id)
    viewport = item.get("viewport") if isinstance(item.get("viewport"), dict) else {}
    if not _positive_number(viewport.get("width")) or not _positive_number(viewport.get("height")):
        fail("invalid-viewport", "viewport width and height must be positive", matrixId=matrix_id)
    geometry = item.get("document") if isinstance(item.get("document"), dict) else {}
    if not _positive_number(geometry.get("clientWidth")) or not _positive_number(geometry.get("scrollWidth")):
        fail("unmeasured-document", "document geometry must be measured", matrixId=matrix_id)
    elif geometry["scrollWidth"] > geometry["clientWidth"]:
        fail("horizontal-overflow", "document scrollWidth exceeds clientWidth", matrixId=matrix_id, scrollWidth=geometry["scrollWidth"], clientWidth=geometry["clientWidth"])
    errors = item.get("consoleErrors")
    if not isinstance(errors, list):
        fail("console-unmeasured", "consoleErrors must be an array", matrixId=matrix_id)
    elif errors:
        fail("console-error", "browser console contains product errors", matrixId=matrix_id, errors=errors)
    task = item.get("task") if isinstance(item.get("task"), dict) else {}
    if not isinstance(task.get("name"), str) or not task["name"].strip() or task.get("completed") is not True:
        fail("task-incomplete", "primary browser task must complete", matrixId=matrix_id)
    controls = item.get("primaryControls")
    if not isinstance(controls, list) or not controls:
        fail("controls-unmeasured", "primaryControls must contain measured controls", matrixId=matrix_id)
    else:
        names = [name for control in controls if (name := _validate_control(control, matrix_id, fail))]
        if len(set(names)) != len(names):
            fail("duplicate-control", "primary control names must be unique", matrixId=matrix_id)
    inputs = item.get("inputs", [])
    if not isinstance(inputs, list):
        fail("inputs-unmeasured", "inputs must be an array", matrixId=matrix_id)
    elif _positive_number(viewport.get("width")) and viewport["width"] <= 560:
        for input_item in inputs:
            font_size = input_item.get("fontSizePx") if isinstance(input_item, dict) else None
            if not _positive_number(font_size) or font_size < 16:
                fail("input-focus-zoom", "compact-layout inputs need measured font size >= 16px", matrixId=matrix_id, input=(input_item or {}).get("name") if isinstance(input_item, dict) else None)
    return matrix_id


def _validate_dialog(item: Any, matrix_ids: set[str], fail: Fail) -> str | None:
    if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
        fail("invalid-dialog", "dialog entry is missing id")
        return None
    dialog_id = item["id"]
    if item.get("matrixId") not in matrix_ids:
        fail("dialog-matrix-missing", "dialog references an unknown matrix", dialogId=dialog_id)
    viewport = item.get("viewport") if isinstance(item.get("viewport"), dict) else {}
    box = item.get("boundingBox") if isinstance(item.get("boundingBox"), dict) else {}
    measured = all(_positive_number(viewport.get(key)) for key in ("width", "height")) and all(isinstance(box.get(key), (int, float)) and not isinstance(box.get(key), bool) for key in ("x", "y", "width", "height"))
    if not measured or box.get("width", 0) <= 0 or box.get("height", 0) <= 0:
        fail("dialog-unmeasured", "dialog needs positive viewport and bounding-box evidence", dialogId=dialog_id)
    elif box["x"] < 0 or box["y"] < 0 or box["x"] + box["width"] > viewport["width"] or box["y"] + box["height"] > viewport["height"]:
        fail("dialog-offscreen", "dialog bounding box escapes the viewport", dialogId=dialog_id)
    if item.get("visible") is not True or item.get("paintSettled") is not True:
        fail("dialog-not-painted", "dialog must be visible after a settled paint", dialogId=dialog_id)
    if not isinstance(item.get("dialogZ"), (int, float)) or not isinstance(item.get("backdropZ"), (int, float)) or item["dialogZ"] <= item["backdropZ"]:
        fail("dialog-behind-backdrop", "dialog z-index must be above its backdrop", dialogId=dialog_id)
    required_true = (
        ("backgroundScrollLocked", "background-scroll-unlocked"), ("escapeCloses", "escape-close-failed"),
        ("focusRestored", "focus-not-restored"), ("accessibleName", "dialog-name-missing"),
        ("tabContained", "dialog-focus-escape"), ("initialFocusInside", "dialog-initial-focus"),
        ("modalSemantics", "dialog-not-modal"),
    )
    for field, code in required_true:
        if item.get(field) is not True:
            fail(code, f"dialog {field} must be true", dialogId=dialog_id)
    return dialog_id


def _measurement_findings(document: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    findings: list[dict[str, Any]] = []
    fail = lambda code, message, **details: findings.append({"status": "FAIL", "code": code, "message": message, **details})
    required_matrix, required_dialogs = _validate_header(document, fail)
    matrices = document.get("matrices")
    if not isinstance(matrices, list):
        fail("matrices", "matrices must be an array")
        matrices = []
    matrix_ids = [value for item in matrices if (value := _validate_matrix(item, document, fail))]
    if len(set(matrix_ids)) != len(matrix_ids):
        fail("duplicate-matrix-id", "matrices contains duplicate ids")
    if set(matrix_ids) != set(required_matrix):
        fail("matrix-not-closed-world", "requiredMatrixIds and measured matrices differ", required=sorted(set(required_matrix)), actual=sorted(set(matrix_ids)))
    dialogs = document.get("dialogs")
    if not isinstance(dialogs, list):
        fail("dialogs", "dialogs must be an array")
        dialogs = []
    dialog_ids = [value for item in dialogs if (value := _validate_dialog(item, set(matrix_ids), fail))]
    if len(set(dialog_ids)) != len(dialog_ids):
        fail("duplicate-dialog-id", "dialogs contains duplicate ids")
    if set(dialog_ids) != set(required_dialogs):
        fail("dialog-not-closed-world", "requiredDialogIds and measured dialogs differ", required=sorted(set(required_dialogs)), actual=sorted(set(dialog_ids)))
    return findings, matrix_ids, dialog_ids


def _validate_collector(document: dict[str, Any], root: Path | None, fail: Fail, inventory: list[dict[str, Any]]) -> None:
    collector = document.get("collector")
    if not isinstance(collector, dict):
        fail("collector-identity", "collector must be an object")
        return
    for field in ("name", "version"):
        if not isinstance(collector.get(field), str) or not collector[field].strip():
            fail("collector-identity", f"collector {field} must be a non-empty string", field=field)
    command = collector.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(item, str) or not item for item in command):
        fail("collector-identity", "collector command must be a non-empty string array")
    captured_at = collector.get("capturedAt")
    try:
        parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00")) if isinstance(captured_at, str) else None
        if parsed is None or parsed.tzinfo is None:
            raise ValueError
    except ValueError:
        fail("collector-identity", "collector capturedAt must be timezone-aware ISO-8601")
    _live_identity(collector.get("implementation"), root, "collector-implementation", fail, inventory)
    _live_identity(collector.get("rawEvidence"), root, "browser-raw-evidence", fail, inventory)


def _validate_negative_controls(document: dict[str, Any], root: Path | None, fail: Fail, inventory: list[dict[str, Any]]) -> None:
    controls = document.get("negativeControls")
    if not isinstance(controls, list):
        fail("negative-controls", "negativeControls must be an evidence-object array")
        return
    ids = [item.get("id") for item in controls if isinstance(item, dict) and isinstance(item.get("id"), str)]
    if len(ids) != len(controls) or len(set(ids)) != len(ids):
        fail("negative-controls", "negativeControls need unique string ids")
    if set(ids) != REQUIRED_NEGATIVE_CONTROLS:
        fail("missing-negative-control", "browser failure controls are not closed-world", missing=sorted(REQUIRED_NEGATIVE_CONTROLS - set(ids)), unexpected=sorted(set(ids) - REQUIRED_NEGATIVE_CONTROLS))
    for item in controls:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        control_id = item["id"]
        path = _live_identity(item.get("report"), root, f"negative-control:{control_id}", fail, inventory)
        if path is None:
            continue
        try:
            negative = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            fail("negative-control-report", "negative control report is not valid UTF-8 JSON", control=control_id, error=str(exc))
            continue
        if not isinstance(negative, dict):
            fail("negative-control-report", "negative control report must be an object", control=control_id)
            continue
        codes = {finding["code"] for finding in _measurement_findings(negative)[0]}
        if control_id not in codes:
            fail("negative-control-not-detected", "calibration report did not trigger its required failure", control=control_id, observed=sorted(codes))


def evaluate(document: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    findings, matrix_ids, dialog_ids = _measurement_findings(document)
    inventory: list[dict[str, Any]] = []
    fail = lambda code, message, **details: findings.append({"status": "FAIL", "code": code, "message": message, **details})
    _validate_collector(document, root, fail, inventory)
    _validate_negative_controls(document, root, fail, inventory)
    unmeasured = document.get("unmeasuredClaims")
    if not isinstance(unmeasured, list) or not unmeasured or any(not isinstance(item, str) or not item for item in unmeasured):
        fail("unmeasured-claims", "unmeasuredClaims must be a non-empty string array")
    return {
        "schemaVersion": 2, "status": "BLOCK" if findings else "GREEN",
        "product": document.get("product"), "productVersion": document.get("productVersion"),
        "buildId": document.get("buildId"), "matrixCount": len(matrix_ids), "dialogCount": len(dialog_ids),
        "evaluatorSha256": _sha256(Path(__file__)),
        "evidenceInventory": sorted(inventory, key=lambda item: (item["role"], item["path"].casefold())),
        "findings": findings or [{"status": "PASS", "code": "web-acceptance-closed", "message": "live same-build browser evidence and calibrated dialog journeys are closed"}],
    }


def _identity(root: Path, relative: str, data: bytes) -> dict[str, Any]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _fixture_measurement() -> dict[str, Any]:
    matrix_id = "store-390x844"
    return {
        "schemaVersion": 2, "product": "Fixture Shop", "productVersion": "1.0.0",
        "buildId": "fixture-build-1", "datasetId": "fixture-products-v1", "browser": "Chromium fixture 1",
        "requiredMatrixIds": [matrix_id], "requiredDialogIds": ["product-detail-mobile"],
        "matrices": [{
            "id": matrix_id, "buildId": "fixture-build-1", "datasetId": "fixture-products-v1", "route": "/#shop",
            "viewport": {"width": 390, "height": 844}, "document": {"clientWidth": 390, "scrollWidth": 390},
            "consoleErrors": [], "task": {"name": "open-product-detail", "completed": True},
            "primaryControls": [{"name": "open detail", "width": 44, "height": 44, "measured": True}],
            "inputs": [{"name": "search", "fontSizePx": 16}],
        }],
        "dialogs": [{
            "id": "product-detail-mobile", "matrixId": matrix_id, "viewport": {"width": 390, "height": 844},
            "boundingBox": {"x": 12, "y": 32, "width": 366, "height": 780}, "visible": True,
            "paintSettled": True, "dialogZ": 91, "backdropZ": 90, "backgroundScrollLocked": True,
            "escapeCloses": True, "focusRestored": True, "accessibleName": True, "tabContained": True,
            "initialFocusInside": True, "modalSemantics": True,
        }],
    }


def _negative_mutations() -> dict[str, Callable[[dict[str, Any]], None]]:
    return {
        "horizontal-overflow": lambda d: d["matrices"][0]["document"].update({"scrollWidth": 391}),
        "undersized-control": lambda d: d["matrices"][0]["primaryControls"][0].update({"width": 30}),
        "console-error": lambda d: d["matrices"][0]["consoleErrors"].append("boom"),
        "dialog-behind-backdrop": lambda d: d["dialogs"][0].update({"dialogZ": 89}),
        "dialog-offscreen": lambda d: d["dialogs"][0]["boundingBox"].update({"width": 400}),
        "focus-not-restored": lambda d: d["dialogs"][0].update({"focusRestored": False}),
        "input-focus-zoom": lambda d: d["matrices"][0]["inputs"][0].update({"fontSizePx": 14}),
        "background-scroll-unlocked": lambda d: d["dialogs"][0].update({"backgroundScrollLocked": False}),
        "escape-close-failed": lambda d: d["dialogs"][0].update({"escapeCloses": False}),
        "dialog-name-missing": lambda d: d["dialogs"][0].update({"accessibleName": False}),
        "dialog-focus-escape": lambda d: d["dialogs"][0].update({"tabContained": False}),
        "dialog-initial-focus": lambda d: d["dialogs"][0].update({"initialFocusInside": False}),
        "dialog-not-modal": lambda d: d["dialogs"][0].update({"modalSemantics": False}),
        "dialog-not-painted": lambda d: d["dialogs"][0].update({"paintSettled": False}),
        "task-incomplete": lambda d: d["matrices"][0]["task"].update({"completed": False}),
        "provenance-drift": lambda d: d["matrices"][0].update({"buildId": "stale-build"}),
    }


def fixture_document(root: Path) -> dict[str, Any]:
    document = _fixture_measurement()
    implementation = _identity(root, "collector/collect-browser.mjs", b"export const version = 'fixture-1';\n")
    raw = _identity(root, "evidence/browser-raw.json", b'{"captured":true}\n')
    controls = []
    for control_id, mutate in sorted(_negative_mutations().items()):
        negative = json.loads(json.dumps(document))
        mutate(negative)
        encoded = (json.dumps(negative, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        controls.append({"id": control_id, "report": _identity(root, f"evidence/controls/{control_id}.json", encoded)})
    document["collector"] = {
        "name": "fixture-browser-collector", "version": "1.0.0", "capturedAt": "2026-08-22T04:00:00Z",
        "command": ["node", "collector/collect-browser.mjs"], "implementation": implementation, "rawEvidence": raw,
    }
    document["negativeControls"] = controls
    document["unmeasuredClaims"] = ["real-device safe area", "virtual keyboard", "field p75 INP", "human task completion"]
    return document


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="rd-web-acceptance-") as raw:
        root = Path(raw)
        valid = fixture_document(root)
        assert evaluate(valid, root)["status"] == "GREEN"
        assert evaluate(valid)["status"] == "BLOCK"
        stale = json.loads(json.dumps(valid))
        (root / stale["collector"]["rawEvidence"]["path"]).write_bytes(b"changed\n")
        assert any(item["code"] == "evidence-stale" for item in evaluate(stale, root)["findings"])
        valid = fixture_document(root)
        missing = json.loads(json.dumps(valid))
        missing["negativeControls"].pop()
        assert any(item["code"] == "missing-negative-control" for item in evaluate(missing, root)["findings"])
        fake = json.loads(json.dumps(valid))
        target = fake["negativeControls"][0]
        positive = (json.dumps(_fixture_measurement(), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        target["report"] = _identity(root, target["report"]["path"], positive)
        assert any(item["code"] == "negative-control-not-detected" for item in evaluate(fake, root)["findings"])
        traversal = json.loads(json.dumps(valid))
        traversal["collector"]["rawEvidence"]["path"] = "../outside.json"
        assert any(item["code"] == "evidence-path" for item in evaluate(traversal, root)["findings"])
        valid = fixture_document(root)
        output = root / "evidence" / "web-gate-report.json"
        write_report(evaluate(valid, root), output, quiet=True)
        if json.loads(output.read_text(encoding="utf-8"))["status"] != "GREEN":
            raise AssertionError("quiet web gate evidence output was not retained")


def write_report(report: dict[str, Any], output: Path | None, quiet: bool = False) -> None:
    payload = json.dumps(report, ensure_ascii=False) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    if not quiet:
        print(payload, end="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        print("web acceptance gate self-test passed")
        return 0
    if not args.report:
        parser.error("report is required unless --self-test is used")
    if args.quiet and not args.output:
        parser.error("--quiet requires --output so gate evidence cannot be discarded")
    with open(args.report, "r", encoding="utf-8-sig") as handle:
        document = json.load(handle)
    report = evaluate(document, args.root.resolve() if args.root else None)
    write_report(report, args.output.resolve() if args.output else None, args.quiet)
    return 0 if report["status"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
