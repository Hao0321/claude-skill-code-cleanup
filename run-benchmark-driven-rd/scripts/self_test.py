#!/usr/bin/env python3
"""Regression checks for the benchmark-driven R&D helper scripts."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from external_change_gate import run_self_test as run_external_change_self_test
from command_execution_gate import run_self_test as run_command_execution_self_test
from invocation_revision_gate import run_self_test as run_invocation_revision_self_test
from project_profile_gate import run_self_test as run_project_profile_self_test
from capability_gate import run_self_test as run_capability_gate_self_test
from claim_matrix_gate import run_self_test as run_claim_matrix_self_test
from completion_closure_gate import run_self_test as run_completion_closure_self_test
from delivery_contract_gate import run_self_test as run_delivery_contract_self_test
from record_experiment import append_entry, experiment_id
from run_cleanup_gate import run_self_test as run_cleanup_gate_self_test
from verify_cleanup_evidence import run_self_test as run_cleanup_freshness_self_test
from web_acceptance_gate import run_self_test as run_web_acceptance_self_test


def test_collision_resistant_ids() -> None:
    now = datetime(2026, 8, 13, 3, 5, 59, 123456, tzinfo=timezone.utc)
    first = experiment_id(now, "first")
    second = experiment_id(now, "second")
    assert first != second
    assert first.startswith("exp-20260813T030559123456Z-")


def test_append_only_ledger() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        entries = [{"id": "exp-one"}, {"id": "exp-two"}]
        for entry in entries:
            path = append_entry(temp_dir, entry)
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
        assert rows == entries


def main() -> int:
    test_collision_resistant_ids()
    test_append_only_ledger()
    run_command_execution_self_test()
    run_external_change_self_test()
    run_invocation_revision_self_test()
    run_project_profile_self_test()
    run_capability_gate_self_test()
    run_claim_matrix_self_test()
    run_completion_closure_self_test()
    run_delivery_contract_self_test()
    run_cleanup_gate_self_test()
    run_cleanup_freshness_self_test()
    run_web_acceptance_self_test()
    print("R&D helper self-test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
