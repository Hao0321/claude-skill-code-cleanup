"""An unchanged index retains exact bytes; real topic mutations change its identity."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile


def run_self_test(api) -> None:
    build_index, _atomic_write = api.build_index, api._atomic_write
    with tempfile.TemporaryDirectory(prefix="rd-index-identity-") as raw:
        root = Path(raw)
        topic = root / "owned.md"
        topic.write_bytes(b"- `rd.owned.rule`: owned rule\n")
        output = root / "index.json"
        specs = {"owned": "owned.md"}
        value, _ = build_index(root, output, specs)
        value["topics"][0]["maintainerNote"] = "preserve metadata"
        # Existing metadata order/indent/newlines are not an instruction to rewrite the index.
        original = (json.dumps(value, ensure_ascii=False, indent=4) + "\r\n").encode("utf-8")
        output.write_bytes(original)
        rebuilt, _ = build_index(root, output, specs)
        assert rebuilt == value
        _atomic_write(output, rebuilt)
        assert output.read_bytes() == original, "no-op index build invalidated receipt bytes"
        topic.write_bytes(b"- `rd.owned.rule`: changed owned rule\n")
        changed, _ = build_index(root, output, specs)
        assert changed["topics"][0]["sha256"] != value["topics"][0]["sha256"]
        assert changed["topics"][0]["maintainerNote"] == "preserve metadata"
        _atomic_write(output, changed)
        assert output.read_bytes() != original, "real topic drift retained old index identity"
        frozen = output.read_bytes()
        again, _ = build_index(root, output, specs)
        _atomic_write(output, again)
        assert output.read_bytes() == frozen, "second rebuild changed stable index bytes"
        invalid = json.loads(frozen)
        invalid["schemaVersion"] = True
        output.write_text(json.dumps(invalid), encoding="utf-8")
        _atomic_write(output, again)
        assert type(json.loads(output.read_bytes())["schemaVersion"]) is int, "boolean schema was treated as an integer no-op"
