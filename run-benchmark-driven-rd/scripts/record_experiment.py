#!/usr/bin/env python3
"""Append one structured experiment to .rd/experiments/ledger.jsonl."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def experiment_id(now: datetime, nonce: str | None = None) -> str:
    """Return a sortable, collision-resistant experiment identifier."""
    token = nonce or uuid4().hex[:8]
    return f"{now.strftime('exp-%Y%m%dT%H%M%S%fZ')}-{token}"


def build_entry(args: argparse.Namespace, now: datetime | None = None) -> dict[str, object]:
    metrics = json.loads(args.metrics)
    if not isinstance(metrics, dict):
        raise SystemExit("--metrics must be a JSON object")
    recorded_at = now or datetime.now(timezone.utc)
    entry: dict[str, object] = {
        "id": experiment_id(recorded_at),
        "recordedAt": recorded_at.isoformat(),
        "hypothesis": args.hypothesis,
        "change": args.change,
        "result": args.result,
        "evidence": args.evidence,
        "metrics": metrics,
        "learning": args.learning,
    }
    if args.failure_type:
        entry["failureType"] = args.failure_type
    return entry


def append_entry(project: str, entry: dict[str, object]) -> Path:
    path = Path(project).resolve() / ".rd/experiments/ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".")
    parser.add_argument("--hypothesis", required=True)
    parser.add_argument("--change", required=True)
    parser.add_argument("--result", required=True, choices=("pass", "fail", "inconclusive", "blocked"))
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--metrics", default="{}", help="JSON object")
    parser.add_argument("--learning", required=True)
    parser.add_argument("--failure-type", choices=("algorithm", "data", "runtime", "integration", "measurement", "product"))
    args = parser.parse_args()
    entry = build_entry(args)
    append_entry(args.project, entry)
    print(entry["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
