#!/usr/bin/env python3
"""CLI orchestration for run_cleanup_gate without mixing provider mechanics into main."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cleanup_gate_paths import relative_output_path, report_contains_path


def initial_capture(args: Any, api: Any) -> dict[str, Any]:
    cleanup_root = api.resolve_active_cleanup_root(args.cleanup_root)
    rd_root = Path(__file__).resolve().parents[1]
    adapter_revision = api.capture_skill_revision(cleanup_root, rd_root)
    report, evaluator_hash, config_hash, provider_revision = api.run_provider(
        cleanup_root, args.target, args.mode, args.config
    )
    api.capture_skill_revision(cleanup_root, rd_root, adapter_revision["sha256"])
    output_relative = relative_output_path(args.output, args.target)
    if output_relative and report_contains_path(report, output_relative):
        raise api.MeasurementError(
            "evidence output is part of the audited inventory; write it outside the target "
            "or exclude its evidence directory in audit.config.json"
        )
    snapshot = api.run_snapshot_checker(cleanup_root, report, report)["after"]
    adapter_hash = api.adapter_sha256()
    envelope = api.build_envelope(
        report, cleanup_root, evaluator_hash, config_hash, args.phase, args.require_checked,
        review_policy=args.review_policy, snapshot=snapshot, adapter_hash=adapter_hash,
        provider_revision=provider_revision, adapter_revision=adapter_revision,
    )
    return {
        "cleanup_root": cleanup_root, "rd_root": rd_root, "adapter_revision": adapter_revision,
        "report": report, "evaluator_hash": evaluator_hash, "config_hash": config_hash,
        "provider_revision": provider_revision, "output_relative": output_relative,
        "adapter_hash": adapter_hash, "envelope": envelope,
    }


def stabilize_in_target_output(args: Any, state: dict[str, Any], api: Any) -> dict[str, Any]:
    api.write_envelope(state["envelope"], args.output, quiet=True)
    after_report, after_evaluator, after_config, after_provider = api.run_provider(
        state["cleanup_root"], args.target, args.mode, args.config
    )
    if (
        after_evaluator != state["evaluator_hash"]
        or after_config != state["config_hash"]
        or after_provider != state["provider_revision"]
    ):
        raise api.MeasurementError("evaluator, config, or provider revision changed during promotion capture")
    api.capture_skill_revision(
        state["cleanup_root"], state["rd_root"], state["adapter_revision"]["sha256"]
    )
    if report_contains_path(after_report, state["output_relative"]):
        raise api.MeasurementError(
            "evidence output entered the audited inventory after capture; exclude its directory "
            "or write the envelope outside the target"
        )
    snapshot = api.run_snapshot_checker(state["cleanup_root"], state["report"], after_report)
    if snapshot["status"] != "FRESH":
        raise api.MeasurementError(
            "target changed while promotion evidence was being written: "
            + json.dumps(snapshot["changes"], ensure_ascii=False)
        )
    return api.build_envelope(
        after_report, state["cleanup_root"], after_evaluator, after_config,
        args.phase, args.require_checked, review_policy=args.review_policy,
        snapshot=snapshot["after"], adapter_hash=state["adapter_hash"],
        provider_revision=after_provider, adapter_revision=state["adapter_revision"],
    )


def execute(args: Any, api: Any) -> int:
    try:
        state = initial_capture(args, api)
        envelope = state["envelope"]
        if state["output_relative"]:
            envelope = stabilize_in_target_output(args, state, api)
    except (api.MeasurementError, OSError, UnicodeError) as exc:
        envelope = {
            "contract_version": api.CONTRACT_VERSION,
            "decision": "MEASUREMENT_BLOCK",
            "phase": args.phase,
            "errors": [str(exc)],
        }
        api.write_envelope(envelope, args.output, quiet=args.quiet)
        return 2
    api.write_envelope(envelope, args.output, quiet=args.quiet)
    return 1 if envelope["decision"] == "BLOCK" else 0
