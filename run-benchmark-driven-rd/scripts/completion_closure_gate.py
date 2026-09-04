#!/usr/bin/env python3
"""Close a long-running product scope against fresh live evidence in one gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Callable

from capability_gate import evaluate as evaluate_capabilities
from delivery_contract_gate import evaluate as evaluate_delivery
from evidence_identity import valid_identity
from project_profile_gate import (
    DEFAULT_PROFILE,
    build_security_assessment_obligation,
    build_update_obligation,
    compose_route,
    sha256_json,
    validate_profile,
)
from run_cleanup_gate import resolve_cleanup_root
from verify_cleanup_evidence import verify as verify_cleanup


from completion_closure_common import *  # noqa: F403
from completion_closure_route import *  # noqa: F403
from completion_closure_checks import *  # noqa: F403
from completion_closure_selftest import *  # noqa: F403


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", nargs="?", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        print("completion closure self-test passed")
        return 0
    if not args.contract:
        parser.error("contract is required unless --self-test is used")
    if args.quiet and not args.output:
        parser.error("--quiet requires --output")
    requested_contract = _lexical_absolute(args.contract)
    root = _lexical_absolute(args.root) if args.root else requested_contract.parent
    contract_path, contract_error = _existing_cli_path(root, requested_contract)
    if contract_error or contract_path is None:
        parser.error(f"unsafe contract path: {contract_error}")
    try:
        contract_document, contract_identity = _read_json_with_identity(contract_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
        parser.error("invalid bounded contract JSON")
    report = evaluate(contract_document, root)
    evaluator_path = _lexical_absolute(Path(__file__))
    report["evaluator"] = file_identity(evaluator_path)
    report["contract"] = contract_identity
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output, output_error = _prepare_output_path(root, args.output)
        if output_error or output is None:
            parser.error(f"unsafe output path: {output_error}")
        if output == contract_path:
            parser.error("output must not replace the closure contract")
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, delete=False) as handle:
            handle.write(payload)
            temporary = Path(handle.name)
        temporary.replace(output)
    if not args.quiet:
        print(payload, end="")
    return 0 if report["status"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
