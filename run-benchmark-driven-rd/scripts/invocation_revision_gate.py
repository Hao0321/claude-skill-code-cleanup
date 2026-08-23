#!/usr/bin/env python3
"""Route latest-on-every-invocation checks through Cleanup's revision provider."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from run_cleanup_gate import MeasurementError, resolve_active_cleanup_root


ROOT = Path(__file__).resolve().parents[1]


def provider_script(cleanup_root: Path) -> Path:
    path = cleanup_root / "scripts" / "check_skill_revision.py"
    if not path.is_file():
        raise MeasurementError(f"Skill revision provider is missing: {path}")
    return path


def run_provider(arguments: list[str], cleanup_root: Path | None = None) -> subprocess.CompletedProcess[str]:
    root = resolve_active_cleanup_root(cleanup_root)
    return subprocess.run(
        [sys.executable, str(provider_script(root)), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env={**os.environ, "PYTHONUTF8": "1"},
        check=False,
    )


def default_skill_roots(cleanup_root: Path | None = None) -> list[Path]:
    return [resolve_active_cleanup_root(cleanup_root), ROOT]


def run_self_test() -> None:
    root = resolve_active_cleanup_root()
    provider_test = run_provider(["--self-test"], root)
    if provider_test.returncode != 0:
        raise AssertionError(provider_test.stderr or provider_test.stdout)
    with tempfile.TemporaryDirectory(prefix="rd-invocation-revision-") as raw:
        output = Path(raw) / "revision.json"
        arguments = ["capture"]
        for skill_root in default_skill_roots(root):
            arguments.extend(["--root", str(skill_root)])
        arguments.extend(["--output", str(output), "--quiet"])
        captured = run_provider(arguments, root)
        if captured.returncode != 0 or not output.is_file():
            raise AssertionError(captured.stderr or captured.stdout or "revision capture failed")
        verified = run_provider(["verify", "--evidence", str(output)], root)
        if verified.returncode != 0 or '"status": "CURRENT"' not in verified.stdout:
            raise AssertionError(verified.stderr or verified.stdout or "revision verification failed")
        quiet_verified = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "verify", str(output), "--quiet"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            env={**os.environ, "PYTHONUTF8": "1"},
            check=False,
        )
        if quiet_verified.returncode != 0 or quiet_verified.stdout:
            raise AssertionError(
                quiet_verified.stderr or quiet_verified.stdout or "quiet verification failed"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--cleanup-root", type=Path)
    subparsers = parser.add_subparsers(dest="command")
    capture = subparsers.add_parser("capture")
    capture.add_argument("--skill-root", action="append", type=Path)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--quiet", action="store_true")
    verify = subparsers.add_parser("verify")
    verify.add_argument("snapshot", type=Path)
    verify.add_argument("--quiet", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        run_self_test()
        print("R&D invocation revision gate self-test passed")
        return 0
    if args.command == "capture":
        roots = args.skill_root or default_skill_roots(args.cleanup_root)
        arguments = ["capture"]
        for root in roots:
            arguments.extend(["--root", str(root.resolve())])
        arguments.extend(["--output", str(args.output.resolve())])
        if args.quiet:
            arguments.append("--quiet")
    elif args.command == "verify":
        arguments = ["verify", "--evidence", str(args.snapshot.resolve())]
    else:
        raise SystemExit("capture, verify, or --self-test is required")
    try:
        completed = run_provider(arguments, args.cleanup_root)
    except (MeasurementError, OSError, UnicodeError) as exc:
        print(f"MEASUREMENT_BLOCK: {exc}", file=sys.stderr)
        return 2
    if completed.stdout and not (args.command == "verify" and args.quiet):
        sys.stdout.write(completed.stdout)
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
