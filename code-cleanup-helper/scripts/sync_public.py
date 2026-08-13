#!/usr/bin/env python3
"""Copy configured public files without deleting public-only packaging files."""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def ignored(relative: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(relative.replace("\\", "/"), pattern) for pattern in patterns)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    config = json.loads((ROOT / "audit.config.json").read_text(encoding="utf-8-sig"))
    value = config.get("sync", {}).get("public_root")
    if not value:
        raise ValueError("sync.public_root is not configured")
    destination_root = Path(value).expanduser()
    if not destination_root.is_absolute():
        destination_root = (ROOT / destination_root).resolve()
    patterns = config.get("exclude", []) + config.get("sync", {}).get("ignore", [])
    changed = []
    for source in sorted((path for path in ROOT.rglob("*") if path.is_file())):
        relative = source.relative_to(ROOT).as_posix()
        if ignored(relative, patterns):
            continue
        destination = destination_root / relative
        if destination.exists() and destination.read_bytes() == source.read_bytes():
            continue
        changed.append(relative)
        if args.write:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    mode = "WRITE" if args.write else "DRY_RUN"
    print(f"{mode} public_root={destination_root} changed={len(changed)}")
    for relative in changed:
        print(relative)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
