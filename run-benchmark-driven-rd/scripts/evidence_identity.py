"""Shared validation for byte-count and SHA-256 evidence identities."""

from __future__ import annotations

import re
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def valid_identity(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("bytes"), int)
        and not isinstance(value.get("bytes"), bool)
        and value["bytes"] > 0
        and isinstance(value.get("sha256"), str)
        and SHA256_RE.fullmatch(value["sha256"]) is not None
    )
