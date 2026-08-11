#!/usr/bin/env python3
"""Dependency-free smoke tests for the audit engine."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from audit_core import declared_versions, run_audit


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def main() -> int:
    versions = declared_versions("# Doc\n目前版本：**v2.3.4**\n散文提到 v9.9.9 不算宣告\n## v2.2.0 — old\n")
    if versions != ["v2.3.4", "v2.2.0"]:
        raise AssertionError(f"version declaration parser failed: {versions}")
    with tempfile.TemporaryDirectory(prefix="cleanup-audit-") as raw:
        root = Path(raw) / "sample-skill"
        root.mkdir()
        write(root / "SKILL.md", "---\nname: sample-skill\ndescription: sample\n---\n# Sample\nCases 1-1\n")
        write(root / "agents" / "openai.yaml", 'interface:\n  default_prompt: "Use $sample-skill to audit this."\n')
        write(root / "references" / "cases.md", "# Cases\n\n## Case 1: A\n\n## Case 2: B\n")
        write(root / "references" / "broken.md", "[missing](nope.md)\n")
        write(root / "references" / "notes.md", "[note](這是一段說明，不是路徑)\n")
        write(root / "leak.txt", "Example path: C:\\Users\\sample-user\\private\n")
        write(root / "audit.config.json", json.dumps({
            "drift_assertions": [{
                "id": "forbidden-old-value",
                "files": ["SKILL.md"],
                "pattern": "Cases 1-1",
                "expected_count": 0,
            }],
            "privacy": {"tokens": ["C:\\Users\\sample-user"], "allow": []},
        }))
        report = run_audit(root, "all")
        codes = {item["code"] for item in report["findings"] if item["status"] == "FAIL"}
        expected = {"range-drift", "broken-link", "forbidden-old-value", "privacy-token"}
        missing = expected - codes
        if missing:
            raise AssertionError(f"self-test missing expected findings: {sorted(missing)}")
        broken = [item for item in report["findings"] if item["code"] == "broken-link"]
        if len(broken) != 1 or broken[0]["path"] != "references/broken.md":
            raise AssertionError(f"pseudo-link filter failed: {broken}")
    print("self-test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
