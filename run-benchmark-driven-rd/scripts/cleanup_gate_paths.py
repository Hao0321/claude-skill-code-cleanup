#!/usr/bin/env python3
"""Path helpers shared by Cleanup promotion capture and freshness verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def relative_output_path(output: Path | None, target: Path) -> str | None:
    if not output:
        return None
    try:
        return output.resolve().relative_to(target.resolve()).as_posix()
    except ValueError:
        return None


def report_contains_path(report: dict[str, Any], relative: str) -> bool:
    return any(
        isinstance(item, dict) and item.get("path", "").casefold() == relative.casefold()
        for item in report.get("inventory", [])
    )
