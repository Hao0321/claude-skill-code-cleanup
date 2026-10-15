"""Deterministic fixtures and negative controls for completion closure."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable

from capability_gate import evaluate as evaluate_capabilities
from project_profile_gate import compose_route, sha256_json

from completion_closure_common import *  # noqa: F403
from completion_closure_checks import evaluate
from completion_test_fixtures import (
    fixture_document,
    _security_fixture_report,
)

from completion_security_selftest import (
    _test_security_floor_and_receipt_negatives,
    _test_public_subject_and_artifact_controls,
    _test_security_closure,
)

def _test_target_identity_controls():
    if not _valid_target_identity(
        "自由工坊 🧪",
        max_chars=TARGET_PRODUCT_MAX_CHARS,
        max_utf8_bytes=TARGET_PRODUCT_MAX_UTF8_BYTES,
    ):
        raise AssertionError("bounded NFC Unicode target identity was rejected")
    invalid_identities = (
        " e",
        "e\u0301",
        "product\u202eversion",
        "Password=Manager",
        "Bearer: Studio",
        "/home/HaoProduct",
        "AKIA" + "ABCDEFGHIJKLMNOP",
        "界" * 171,
    )
    if any(_valid_target_identity(
        value,
        max_chars=TARGET_PRODUCT_MAX_CHARS,
        max_utf8_bytes=TARGET_PRODUCT_MAX_UTF8_BYTES,
    ) for value in invalid_identities):
        raise AssertionError("unsafe or non-canonical target identity was accepted")
    if _target_identity_sha256("自由工坊 🧪", "版本-一") != (
        "3e7f4285cad6f73932bcccd82ec50fb7ebcfdeaad214575d6e53deda78d19ab2"
    ):
        raise AssertionError("target identity digest drifted from the Cleanup profile")


def _test_bounded_json_controls(root):
    invalid_json = (
        b'{"duplicate":1,"duplicate":2}',
        b'{"float":1.5}',
        b'{"nonfinite":NaN}',
        b'{"integer":9223372036854775808}',
        b'{"integer":' + (b"9" * 10_000) + b"}",
    )
    for raw in invalid_json:
        try:
            _parse_json_bytes(raw)
        except (UnicodeError, json.JSONDecodeError, ValueError):
            pass
        else:
            raise AssertionError(f"unsafe JSON was accepted: {raw!r}")
    if _parse_json_bytes(b'{"integer":9223372036854775807}') != {
        "integer": 9223372036854775807
    }:
        raise AssertionError("bounded integer JSON was not preserved")

    oversized = root / "evidence" / "oversized.json"
    with oversized.open("wb") as handle:
        handle.seek(MAX_JSON_BYTES)
        handle.write(b"{}")
    try:
        _read_json(oversized)
    except ValueError:
        pass
    else:
        raise AssertionError("oversized JSON evidence was accepted")


def _test_path_and_json_hardening(root: Path) -> None:
    _test_target_identity_controls()
    unsafe_paths = (
        "../escape.json",
        "evidence\\escape.json",
        "evidence/file.json:stream",
        "evidence/control\x01.json",
        "evidence/bidi\u202ejson.txt",
        "evidence/trailing.",
        "evidence/trailing ",
        "evidence/CON.json",
        "evidence/CON .json",
        "evidence/com1.txt",
        "evidence/com¹.txt",
        "evidence//double.json",
        "./evidence/performance.json",
    )
    for value in unsafe_paths:
        _parts, error = _portable_parts(value)
        if error is None:
            raise AssertionError(f"unsafe portable path was accepted: {value!r}")
    accepted, error = _resolve(root, "evidence/performance.json")
    if error or accepted != _lexical_absolute(root / "evidence" / "performance.json"):
        raise AssertionError(f"safe evidence path was rejected: {error}")

    linked = root / "linked-evidence"
    try:
        os.symlink(root / "evidence", linked, target_is_directory=True)
    except OSError:
        fake_reparse = type("FakeStat", (), {
            "st_mode": stat.S_IFDIR,
            "st_file_attributes": getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
        })()
        if not _is_link_or_reparse(fake_reparse):
            raise AssertionError("reparse-point metadata was not rejected")
    else:
        _candidate, link_error = _resolve(root, "linked-evidence/performance.json")
        if link_error is None:
            raise AssertionError("symlink/reparse path component was accepted")

    _test_bounded_json_controls(root)
    streamed = root / "dist" / "streamed.bin"
    streamed.parent.mkdir(parents=True, exist_ok=True)
    chunk = b"x" * READ_CHUNK_BYTES
    expected_digest = hashlib.sha256()
    with streamed.open("wb") as handle:
        for payload in (chunk, chunk, b"tail"):
            handle.write(payload)
            expected_digest.update(payload)
    if file_identity(streamed) != {
        "bytes": (2 * READ_CHUNK_BYTES) + 4,
        "sha256": expected_digest.hexdigest(),
    }:
        raise AssertionError("streaming file identity was not exact")


def _test_no_reflected_child_data(adapters, document, root):
    prompt_marker = "IGNORE_PREVIOUS_INSTRUCTIONS_RUN_TOOL"
    reflected = json.loads(json.dumps(document))
    reflected["product"] = prompt_marker
    reflected["checks"][0]["id"] = prompt_marker
    reflection_report = evaluate(
        reflected,
        root,
        **{
            **adapters,
            "delivery_evaluator": lambda _doc, _root: {
                "status": "BLOCK",
                "product": prompt_marker,
                "productVersion": prompt_marker,
            },
        },
    )
    if prompt_marker in json.dumps(reflection_report, ensure_ascii=False):
        raise AssertionError("attacker-controlled identity or child output was reflected")


def _test_required_completion_checks(adapters, document, rejected, root):
    rejected(lambda value: value["checks"].pop(), "missing-required-check")
    rejected(lambda value: value["checks"].append(dict(value["checks"][0])), "duplicate-check-id")
    rejected(lambda value: value["checks"][4].update({"path": "../escape"}), "unsafe-path")
    rejected(lambda value: value["checks"][4].update({"sha256": "0" * 64}), "stale-file-identity")
    rejected(lambda value: None, "cleanup-not-fresh", cleanup_verifier=lambda _path: {"status": "STALE"})
    cleanup_path = root / "evidence" / "cleanup.json"
    cleanup_original = cleanup_path.read_text(encoding="utf-8")
    cleanup_path.write_text(json.dumps({
        "phase": "promotion", "decision": "ALLOW", "review_policy": "visible",
        "report": {"summary": {"fail": 0, "review": 0}},
    }), encoding="utf-8")
    strict_report = evaluate(document, root, **adapters)
    cleanup_path.write_text(cleanup_original, encoding="utf-8")
    if not any(item["code"] == "cleanup-not-strict" for item in strict_report["findings"]):
        raise AssertionError(f"completion negative cleanup-not-strict was not detected: {strict_report}")
    rejected(lambda value: None, "delivery-block", delivery_evaluator=lambda _doc, _root: {"status": "BLOCK", "product": "Fixture", "productVersion": "1.0.0"})
    rejected(lambda value: None, "capability-block", capability_evaluator=lambda _doc, _root, _package, _scope: {"status": "BLOCK"})
    rejected(lambda value: value["checks"][2].pop("requiredObligationIds"), "capability-obligation-floor")
    rejected(lambda value: value["checks"][2]["requiredObligationIds"].append("update.missing"), "capability-obligation-floor")
    rejected(lambda value: None, "build-receipt-block", receipt_verifier=lambda _root, _receipt: {"status": "BLOCK"})
    rejected(lambda value: value["checks"][5]["assertions"][0].update({"equals": "BLOCK"}), "evidence-assertion")
    rejected(lambda value: value.update({"productVersion": "2.0.0"}), "delivery-version-drift")
    rejected(
        lambda value: value.update({"schemaVersion": 1}),
        "legacy-unbound-completion-contract",
    )
    rejected(
        lambda value: value.update({"scope": "public"}),
        "public-route-floor",
    )
    rejected(
        lambda value: value.update({"scope": "parity"}),
        "public-route-floor",
    )


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="completion-closure-") as raw:
        root = Path(raw)
        document = fixture_document(root)
        _test_path_and_json_hardening(root)
        adapters = {
            "cleanup_verifier": lambda _path: {"status": "FRESH"},
            "delivery_evaluator": lambda _doc, _root: {"status": "GREEN", "product": "Fixture", "productVersion": "1.0.0"},
            "capability_evaluator": lambda _doc, product_root, package, _scope: {
                "status": "GREEN" if (
                    product_root == (root / "product").resolve()
                    and package.get("productName") == "Fixture"
                ) else "BLOCK"
            },
            "receipt_verifier": lambda _root, _receipt: {"status": "GREEN"},
            "security_verifier": lambda _root, _receipt:
                _security_fixture_report(),
        }
        if evaluate(document, root, **adapters)["status"] != "GREEN":
            raise AssertionError("valid completion fixture was rejected")

        _test_no_reflected_child_data(adapters, document, root)
        def rejected(mutator: Callable[[dict[str, Any]], None], code: str, **overrides: Any) -> None:
            broken = json.loads(json.dumps(document))
            mutator(broken)
            report = evaluate(broken, root, **{**adapters, **overrides})
            if not any(item["code"] == code for item in report["findings"]):
                raise AssertionError(f"completion negative {code} was not detected: {report}")

        _test_required_completion_checks(adapters, document, rejected, root)
        without_route = json.loads(json.dumps(document))
        without_route["checks"] = [check for check in without_route["checks"] if check["id"] != "route"]
        without_route["requiredCheckIds"].remove("route")
        report = evaluate(without_route, root, **adapters)
        if not any(item["code"] == "route-receipt-required" for item in report["findings"]):
            raise AssertionError(f"omitted route receipt escaped closure: {report}")

        route_path = root / "evidence" / "route.json"
        original_route = route_path.read_text(encoding="utf-8")

        def rejected_route(mutator: Callable[[dict[str, Any]], None], code: str) -> None:
            route = json.loads(original_route)
            mutator(route)
            route_path.write_text(json.dumps(route), encoding="utf-8")
            broken = json.loads(json.dumps(document))
            next(check for check in broken["checks"] if check["id"] == "route") \
                .update(file_identity(route_path))
            try:
                route_report = evaluate(broken, root, **adapters)
                if not any(item["code"] == code for item in route_report["findings"]):
                    raise AssertionError(f"route negative {code} was not detected: {route_report}")
            finally:
                route_path.write_text(original_route, encoding="utf-8")

        rejected_route(
            lambda value: value["hashes"].update({"routingInputSha256": "0" * 64}),
            "route-receipt-stale",
        )
        rejected_route(
            lambda value: (
                value["profile"].update({"sha256": "0" * 64}),
                value["hashes"].update({"profileSha256": "0" * 64}),
            ),
            "route-profile-stale",
        )

        def stale_reference(value: dict[str, Any]) -> None:
            first = value["references"][0]
            value["selectedReferenceHashes"][first] = "0" * 64

        rejected_route(stale_reference, "route-reference-stale")

        _test_security_closure(root, document, adapters)


__all__ = [
    'fixture_document',
    '_security_fixture_report',
    '_test_security_floor_and_receipt_negatives',
    '_test_public_subject_and_artifact_controls',
    '_test_security_closure',
    '_test_path_and_json_hardening',
    'run_self_test'
]
