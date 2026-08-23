#!/usr/bin/env python3
"""Initialize a non-destructive .rd workspace in any project."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FILES = {
    ".rd/project.json": json.dumps(
        {
            "schemaVersion": 1,
            "autoDetect": True,
            "projectTypes": [],
            "modules": [],
        },
        indent=2,
    )
    + "\n",
    ".rd/CHARTER.md": """# R&D Charter

## Falsifiable claim

Unmeasured.

## Baseline and candidate

- Baseline: unmeasured
- Candidate: unmeasured

## Promotion rule

No candidate becomes the default without same-provenance, blinded benchmark evidence and a rollback path.
""",
    ".rd/DECISIONS.md": "# Architecture Decisions\n\nAppend dated decisions with evidence and rollback conditions.\n",
    ".rd/FAILURES.md": "# Reusable Failure Memory\n\nAppend failure patterns, root causes, and prevention rules.\n",
    ".rd/TOOLING.md": "# Evaluation Tooling\n\nRecord evaluator purpose, required detectors, blind spots, self-test/fixture evidence, version or SHA, config SHA, and report schema before collecting a baseline.\n",
    ".rd/EXTERNAL_CHANGES.md": "# External Change Ledger\n\nAppend canonical-target preflights, authorization evidence, execution outcomes, postcondition checks, and recovery notes for every external mutation.\n",
    ".rd/experiments/ledger.jsonl": "",
    ".rd/benchmarks/gate.config.json": json.dumps(
        {
            "schemaVersion": 1,
            "minRunsPerScenario": 30,
            "requireBlinded": True,
            "gates": [],
        },
        indent=2,
    )
    + "\n",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".", help="Project root")
    parser.add_argument("--dry-run", action="store_true", help="Print planned files without writing")
    args = parser.parse_args()
    root = Path(args.project).resolve()
    created = 0
    skipped = 0
    for relative, content in FILES.items():
        path = root / relative
        if path.exists():
            print(f"SKIP {path}")
            skipped += 1
            continue
        print(f"CREATE {path}")
        if not args.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        created += 1
    print(f"created={created} skipped={skipped} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
