#!/usr/bin/env python3
"""Build the combined Cleanup/R&D topic index from live canonical topic cards."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


TOPIC_SPECS = {
    "cleanup.context": "code-cleanup-helper/references/topics/context-routing-and-memory.md",
    "cleanup.cross-system": "code-cleanup-helper/references/topics/cross-system-core.md",
    "cleanup.desktop": "code-cleanup-helper/references/topics/desktop-runtime.md",
    "cleanup.media": "code-cleanup-helper/references/topics/media-workstation.md",
    "cleanup.session-ai": "code-cleanup-helper/references/topics/session-native-ai.md",
    "cleanup.updater": "code-cleanup-helper/references/topics/secure-self-update.md",
    "rd.architecture": "run-benchmark-driven-rd/references/topics/architecture-and-evaluator.md",
    "rd.completion-detail": "run-benchmark-driven-rd/references/topics/completion-detail.md",
    "rd.completion-external": "run-benchmark-driven-rd/references/topics/completion-and-external.md",
    "rd.context-learning": "run-benchmark-driven-rd/references/topics/context-and-learning.md",
    "rd.core": "run-benchmark-driven-rd/references/topics/core-experiment.md",
    "rd.delivery-artifact": "run-benchmark-driven-rd/references/topics/delivery-artifact.md",
    "rd.external-detail": "run-benchmark-driven-rd/references/topics/external-detail.md",
    "rd.media-evidence": "run-benchmark-driven-rd/references/topics/media-evidence.md",
    "rd.security-assessment": "run-benchmark-driven-rd/references/topics/security-assessment.md",
    "rd.security-hardening": "run-benchmark-driven-rd/references/topics/security-hardening.md",
    "rd.updater": "run-benchmark-driven-rd/references/topics/secure-self-update.md",
}
RULE_PATTERN = re.compile(r"`((?:cleanup|rd)\.[a-z0-9][a-z0-9.-]+)`")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tokenizer() -> tuple[Any, str, str]:
    try:
        import tiktoken  # type: ignore
    except ImportError as exc:
        raise RuntimeError("tiktoken is required for an exact topic index") from exc
    encoder = tiktoken.get_encoding("o200k_base")
    return encoder, "o200k_base", getattr(tiktoken, "__version__", "unknown")


def _safe_topic(skills_root: Path, raw: str) -> Path:
    if "\\" in raw:
        raise ValueError(f"topic path must use POSIX separators: {raw}")
    rel = PurePosixPath(raw)
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError(f"unsafe topic path: {raw}")
    path = (skills_root / Path(*rel.parts)).resolve()
    path.relative_to(skills_root.resolve())
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing or symlinked topic: {raw}")
    return path


def _existing_metadata(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if not path.is_file():
        return {}, {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("existing topic index must be an object")
    topics = {
        item["id"]: item
        for item in value.get("topics", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    rules = {
        item["id"]: item
        for item in value.get("rules", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    return topics, rules


def build_index(
    skills_root: Path,
    output: Path,
    specs: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    encoder, tokenizer_id, tokenizer_version = _tokenizer()
    existing_topics, existing_rules = _existing_metadata(output)
    topics: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []
    global_owners: dict[str, str] = {}

    for topic_id, relative in sorted((specs or TOPIC_SPECS).items()):
        path = _safe_topic(skills_root, relative)
        payload = path.read_bytes()
        text = payload.decode("utf-8")
        rule_ids = sorted(set(RULE_PATTERN.findall(text)))
        if not rule_ids:
            raise ValueError(f"topic has no stable rule IDs: {relative}")
        for rule_id in rule_ids:
            previous = global_owners.setdefault(rule_id, topic_id)
            if previous != topic_id:
                raise ValueError(f"duplicate rule owner for {rule_id}: {previous}, {topic_id}")

        previous_topic = dict(existing_topics.get(topic_id, {}))
        for key in ("id", "path", "sha256", "contentSha256", "tokenCost", "estimatedTokens", "ruleIds"):
            previous_topic.pop(key, None)
        previous_topic.update(
            {
                "id": topic_id,
                "path": relative,
                "sha256": _sha256(payload),
                "tokenCost": len(encoder.encode(text)),
                "privacy": previous_topic.get("privacy", "sanitized"),
                "ruleIds": rule_ids,
            }
        )
        topics.append(previous_topic)

        for rule_id in rule_ids:
            previous_rule = dict(existing_rules.get(rule_id, {}))
            previous_rule.update(
                {
                    "id": rule_id,
                    "ownerTopic": topic_id,
                    "promotionState": previous_rule.get("promotionState", "provisional"),
                    "evidenceState": previous_rule.get("evidenceState", "diagnostic"),
                    "privacy": previous_rule.get("privacy", "sanitized"),
                    "experimentIds": previous_rule.get("experimentIds", []),
                    "positiveFixtureIds": previous_rule.get("positiveFixtureIds", []),
                    "negativeFixtureIds": previous_rule.get("negativeFixtureIds", []),
                }
            )
            rules.append(previous_rule)

    index = {
        "schemaVersion": 1,
        "tokenizer": {"id": tokenizer_id, "version": tokenizer_version},
        "topicRootPolicy": "explicit-skills-root",
        "topics": topics,
        "rules": sorted(rules, key=lambda item: item["id"]),
    }
    report = {
        "schemaVersion": 1,
        "status": "PASS",
        "output": output.resolve().as_posix(),
        "topics": len(topics),
        "rules": len(rules),
        "totalTopicTokens": sum(item["tokenCost"] for item in topics),
        "maxTopicTokens": max(item["tokenCost"] for item in topics),
        "tokenizer": index["tokenizer"],
    }
    return index, report


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="topic-index-test-") as raw:
        root = Path(raw)
        first = root / "one.md"
        second = root / "two.md"
        first.write_text("- `rd.test.first`: rule", encoding="utf-8")
        second.write_text("- `cleanup.test.second`: rule", encoding="utf-8")
        output = root / "index.json"
        index, report = build_index(root, output, {"one": "one.md", "two": "two.md"})
        _atomic_write(output, index)
        stable, stable_report = build_index(root, output, {"one": "one.md", "two": "two.md"})
        duplicate_failed = False
        second.write_text("- `rd.test.first`: duplicate", encoding="utf-8")
        try:
            build_index(root, output, {"one": "one.md", "two": "two.md"})
        except ValueError:
            duplicate_failed = True
        passed = (
            report["topics"] == 2
            and report["rules"] == 2
            and stable == index
            and stable_report["status"] == "PASS"
            and duplicate_failed
        )
        return {
            "schemaVersion": 1,
            "status": "PASS" if passed else "BLOCK",
            "cases": {"build": report["rules"] == 2, "stable": stable == index, "duplicateOwner": duplicate_failed},
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "topic-index.json")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            report = self_test()
        else:
            index, report = build_index(args.skills_root.resolve(), args.output.resolve())
            _atomic_write(args.output.resolve(), index)
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
        report = {"schemaVersion": 1, "status": "BLOCK", "errors": [str(exc)]}
    if not args.quiet:
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
