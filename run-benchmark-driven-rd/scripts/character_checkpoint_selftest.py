"""Behavioral positive, stale, malformed, escape and concurrent-writer controls."""
import copy
import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import read_character_checkpoint as reader


def self_test() -> dict:
    cases = {}
    with tempfile.TemporaryDirectory(prefix="character-checkpoint-") as raw:
        root = Path(raw); manifest = root / "checkpoint.json"
        row = dict(schemaVersion=1, id="fixture", stage="NATIVE_REVIEW_OPEN", nativeObject="Face",
                   accepted=False, blockedBy=["eye fold"], rejectedMethods=["vertex UV transfer"],
                   nextAction="Inspect one eye corner; no command execution.", artifacts=[])
        for role in ("source", "candidate", "requirements", "review"):
            payload = role.encode(); (root / role).write_bytes(payload)
            row["artifacts"].append(dict(role=role, path=role, sha256=hashlib.sha256(payload).hexdigest()))

        def save(value):
            manifest.write_text(json.dumps(value), encoding="utf-8")

        def blocked(value):
            save(value)
            try:
                reader.read_checkpoint(root, "checkpoint.json")
                return False
            except (OSError, ValueError):
                return True

        save(row); before = {p.name: p.read_bytes() for p in root.iterdir()}
        good = reader.read_checkpoint(root, "checkpoint.json")
        cases["fresh_rejected_candidate_preserved"] = good["status"] == "CURRENT" and good["accepted"] is False and good["blockedBy"] == ["eye fold"]
        cases["read_only"] = before == {p.name: p.read_bytes() for p in root.iterdir()}
        (root / "candidate").write_bytes(b"changed")
        cases["stale_hash_rejected"] = blocked(row)
        (root / "candidate").write_bytes(b"candidate")
        for name, value in (("parent_escape", "../outside"), ("absolute", "/outside"),
                            ("windows_drive", "C:/outside"), ("backslash", "..\\outside"),
                            ("missing", "absent")):
            bad = copy.deepcopy(row); bad["artifacts"][0]["path"] = value
            cases[name + "_rejected"] = blocked(bad)
        bad = copy.deepcopy(row); bad["artifacts"][0]["role"] = "candidate"
        cases["duplicate_role_rejected"] = blocked(bad)
        bad = copy.deepcopy(row); bad["schemaVersion"] = True
        cases["boolean_schema_rejected"] = blocked(bad)
        bad = copy.deepcopy(row); bad["accepted"] = "false"
        cases["string_approval_rejected"] = blocked(bad)
        bad = copy.deepcopy(row); bad["artifacts"][0]["sha256"] = "not-a-digest"
        cases["malformed_digest_rejected"] = blocked(bad)
        bad = copy.deepcopy(row); bad["nextAction"] = "x" * 401
        cases["oversized_text_rejected"] = blocked(bad)
        for name, payload in (("duplicate_key", '{"schemaVersion":1,"schemaVersion":1}'),
                              ("malformed_json", '{'), ("nonfinite", '{"a":NaN}')):
            manifest.write_text(payload, encoding="utf-8")
            try:
                reader.read_checkpoint(root, "checkpoint.json"); cases[name + "_rejected"] = False
            except ValueError:
                cases[name + "_rejected"] = True
        original = reader._hash_file

        def racing(path):
            digest = original(path)
            if path.name == "review":
                (root / "source").write_bytes(b"writer changed already hashed source")
            return digest

        save(row)
        with patch.object(reader, "_hash_file", racing):
            cases["concurrent_writer_rejected"] = blocked(row)
        (root / "source").write_bytes(b"source"); save(row)
        cases["valid_after_restore"] = reader.read_checkpoint(root, "checkpoint.json")["status"] == "CURRENT"
    assert all(cases.values()), cases
    return {"status": "PASS", "cases": cases}


if __name__ == "__main__":
    print(json.dumps(self_test(), sort_keys=True))
