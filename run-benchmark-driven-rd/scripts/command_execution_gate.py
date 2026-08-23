#!/usr/bin/env python3
"""Run one external command without a shell and retain launch-integrity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = 1
ALGORITHM = "sha256"


class CommandGateError(ValueError):
    """Raised when the command contract itself is invalid."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stream_identity(payload: bytes) -> dict[str, Any]:
    return {
        "algorithm": ALGORITHM,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def resolve_executable(value: str) -> Path:
    if not value or "\x00" in value:
        raise CommandGateError("command executable is empty or malformed")
    candidate = Path(value).expanduser()
    has_path_hint = candidate.is_absolute() or candidate.parent != Path(".")
    resolved = Path(os.path.abspath(candidate)) if has_path_hint else None
    if resolved is None or not resolved.is_file():
        located = shutil.which(value)
        resolved = Path(os.path.abspath(located)) if located else None
    if resolved is None or not resolved.is_file():
        raise CommandGateError(f"executable was not resolved: {value}")
    if os.name == "nt" and resolved.suffix.lower() in {".bat", ".cmd", ".ps1"}:
        raise CommandGateError(
            f"shell wrapper is not a shell-free executable; invoke its interpreter explicitly: {resolved}"
        )
    return resolved


def atomic_write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def blocked_receipt(
    argv: Sequence[str], cwd: Path, failure_class: str, message: str
) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "BLOCK",
        "failureType": "measurement",
        "failureClass": failure_class,
        "message": message,
        "command": {"argv": list(argv), "cwd": str(cwd)},
    }


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    expected_output: Sequence[str] = (),
) -> dict[str, Any]:
    command = list(argv)
    if not command:
        return blocked_receipt(command, cwd, "launch", "no command was supplied")
    if timeout_seconds <= 0:
        return blocked_receipt(command, cwd, "contract", "timeout must be positive")
    if not cwd.is_dir():
        return blocked_receipt(command, cwd, "launch", f"working directory does not exist: {cwd}")
    try:
        executable = resolve_executable(command[0])
    except CommandGateError as error:
        return blocked_receipt(command, cwd, "launch", str(error))

    resolved_command = [str(executable), *command[1:]]
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            resolved_command,
            cwd=cwd,
            shell=False,
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        receipt = blocked_receipt(command, cwd, "timeout", f"command exceeded {timeout_seconds:g}s")
        receipt.update({"startedAt": started_at, "durationMs": duration_ms})
        receipt["stdout"] = stream_identity(error.stdout or b"")
        receipt["stderr"] = stream_identity(error.stderr or b"")
        return receipt
    except OSError as error:
        return blocked_receipt(command, cwd, "launch", f"process launch failed: {error}")

    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    combined = (completed.stdout + b"\n" + completed.stderr).decode("utf-8", errors="replace")
    missing = [marker for marker in expected_output if marker not in combined]
    status = "GREEN" if completed.returncode == 0 and not missing else "BLOCK"
    failure_class = None
    if completed.returncode != 0:
        failure_class = "process-exit"
    elif missing:
        failure_class = "expected-output"
    executable_stat = executable.stat()
    physical_executable = executable.resolve()
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": status,
        "failureType": None if status == "GREEN" else "measurement",
        "failureClass": failure_class,
        "message": "command executed and satisfied its contract" if status == "GREEN" else "command evidence did not satisfy its contract",
        "startedAt": started_at,
        "durationMs": duration_ms,
        "host": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "command": {
            "argv": command,
            "cwd": str(cwd),
            "resolvedExecutable": str(executable),
            "physicalExecutable": str(physical_executable),
            "invocationIsSymlink": executable.is_symlink(),
            "executableBytes": executable_stat.st_size,
            "executableSha256": sha256_file(executable),
            "shell": False,
            "exitCode": completed.returncode,
        },
        "expectedOutput": list(expected_output),
        "missingExpectedOutput": missing,
        "stdout": stream_identity(completed.stdout),
        "stderr": stream_identity(completed.stderr),
    }


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="rd-command-gate-") as raw:
        root = Path(raw).resolve()
        green = run_command(
            [sys.executable, "-c", "print('COMMAND_GATE_OK')"],
            cwd=root,
            timeout_seconds=10,
            expected_output=["COMMAND_GATE_OK"],
        )
        if green["status"] != "GREEN" or green["command"]["exitCode"] != 0:
            raise AssertionError("valid command did not produce GREEN launch evidence")
        alias = root / ("python-proxy.exe" if os.name == "nt" else "python-proxy")
        try:
            alias.symlink_to(Path(sys.executable))
        except OSError:
            alias = None
        if alias is not None:
            preserved = resolve_executable(str(alias))
            if preserved != alias.absolute() or not preserved.is_symlink():
                raise AssertionError("proxy invocation path was collapsed to its physical target")
            proxy = run_command(
                [str(alias), "-c", "print('PROXY_OK')"],
                cwd=root,
                timeout_seconds=10,
                expected_output=["PROXY_OK"],
            )
            if proxy["status"] != "GREEN" or not proxy["command"]["invocationIsSymlink"]:
                raise AssertionError("symlinked executable proxy was not launched through its alias")
        missing = run_command(
            ["__rd_command_that_does_not_exist__"], cwd=root, timeout_seconds=10
        )
        if missing["status"] != "BLOCK" or missing["failureClass"] != "launch":
            raise AssertionError("missing executable was not launch-blocked")
        if os.name == "nt":
            wrapper = root / "false-green.cmd"
            wrapper.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
            wrapped = run_command([str(wrapper)], cwd=root, timeout_seconds=10)
            if wrapped["status"] != "BLOCK" or wrapped["failureClass"] != "launch":
                raise AssertionError("Windows shell wrapper was accepted as shell-free evidence")
        failed = run_command(
            [sys.executable, "-c", "raise SystemExit(7)"], cwd=root, timeout_seconds=10
        )
        if failed["status"] != "BLOCK" or failed["failureClass"] != "process-exit":
            raise AssertionError("non-zero child exit was not blocked")
        absent_marker = run_command(
            [sys.executable, "-c", "print('different')"],
            cwd=root,
            timeout_seconds=10,
            expected_output=["COMMAND_GATE_OK"],
        )
        if absent_marker["status"] != "BLOCK" or absent_marker["failureClass"] != "expected-output":
            raise AssertionError("missing success marker was not blocked")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--timeout-seconds", type=float, default=600)
    parser.add_argument("--expect-output", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        run_self_test()
        print("command execution gate self-test passed")
        return 0
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if args.quiet and args.output is None:
        raise SystemExit("--quiet requires --output so evidence is not discarded")
    receipt = run_command(
        command,
        cwd=args.cwd.resolve(),
        timeout_seconds=args.timeout_seconds,
        expected_output=args.expect_output,
    )
    if args.output is not None:
        atomic_write_json(args.output.resolve(), receipt)
    if not args.quiet:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["status"] == "GREEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
