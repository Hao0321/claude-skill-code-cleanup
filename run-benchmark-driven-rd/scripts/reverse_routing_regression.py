"""Typed reverse-analysis routing and console-independent JSON fixtures."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import project_profile_gate as router


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="rd-reverse-") as raw:
        project = Path(raw) / "工程-Ω"
        project.mkdir()
        contract = {"schemaVersion": 2, "autoDetect": False, "projectTypes": ["software"],
                    "modules": [], "taskIntent": "reverse-engineering", "stage": "discovery",
                    "artifact": "binary", "risk": "low", "contextBudgetTokens": 12000}
        path = project / "contract.json"
        path.write_text(json.dumps(contract), encoding="utf-8")
        command = [sys.executable, "-B", str(Path(router.__file__)), "--project", str(project),
                   "--contract", str(path)]
        child = subprocess.run(command, capture_output=True, timeout=30, check=False,
                               env={**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"})
        assert child.returncode == 0, "routing JSON depends on console code page"
        report = json.loads(child.stdout.decode("utf-8", errors="strict"))
        assert Path(report["projectRoot"]) == project, "Unicode project identity changed"
        assert "reverse-engineering" in report["selectedTopicIds"]
        assert "rd.reverse.epistemic" in report["criticalRuleIds"]
        assert "secure-self-update" not in report["selectedTopicIds"], "analysis inferred an updater"
        assert report["gateEvidence"]["status"] == "NOT_EVALUATED", "routing became analysis proof"
        contract.update(taskIntent="audit", artifact="source")
        path.write_text(json.dumps(contract), encoding="utf-8")
        control = router.compose_route(project, router.DEFAULT_PROFILE, path)
        assert "reverse-engineering" not in control["selectedTopicIds"], "reverse card leaked into unrelated audit"


if __name__ == "__main__":
    run_self_test()
    print("Reverse-analysis routing and UTF-8 JSON regressions passed")
