"""Task-shaped intake controls; synthetic files and a disclosed test counter."""
from __future__ import annotations
import copy
import io
import json
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from check_context_budget import Tokenizer

COUNTER = Tokenizer(True, "fixture", None, len, "test-character-counter")


def _setup(root):
    (root / "SKILL.md").write_text("---\nname: sample\ndescription: Small fixture\n---\nCORE_REQUIRED\n", encoding="utf-8")
    (root / "focused.md").write_text("FOCUSED_BODY", encoding="utf-8")
    (root / "other.md").write_text("UNRELATED_BODY", encoding="utf-8")
    file_row = lambda p: {"path": p, "maxBytes": 2000, "maxTokens": 2000}
    route = lambda name, p: {"id": name, "files": [file_row("SKILL.md"), file_row(p)], "maxBytes": 4000, "maxTokens": 4000}
    doc = {"schemaVersion": 1, "tokenizer": "o200k_base", "routes": [route("focused", "focused.md"), route("other", "other.md")]}
    (root / "policy.json").write_text(json.dumps(doc), encoding="utf-8")
    return doc


def _save(root, doc):
    (root / "policy.json").write_text(json.dumps(doc), encoding="utf-8")


def _build(root, event="turn", selected=("focused",), **kwargs):
    return intake.build(root, "policy.json", event, selected, tokenizer=COUNTER, catalog_max=512, **kwargs)


def _reject(call):
    try:
        report, text = call()
    except (ValueError, RuntimeError, OSError):
        return
    if report["status"] == "GREEN" or text:
        raise AssertionError("invalid intake produced a usable packet")


def _lifecycle(root):
    original = intake._read_source
    with patch.object(intake, "_read_source", wraps=original) as reads:
        report, text = _build(root, "startup", ())
    assert report["status"] == "GREEN" and "CORE_REQUIRED" not in text
    assert "Description: Small fixture" in text and "UNRELATED_BODY" not in text
    assert {c.args[1] for c in reads.call_args_list} == {"policy.json", "SKILL.md"}
    report, text = _build(root)
    assert report["status"] == "GREEN" and "CORE_REQUIRED" in text and "FOCUSED_BODY" in text
    assert "UNRELATED_BODY" not in text and report["catalogTokens"] == 0
    report, text = _build(root, selected=("focused", "other"))
    assert report["status"] == "GREEN" and text.count("CORE_REQUIRED") == 1
    # An old disk receipt cannot suppress fresh data after resume.
    (root / "old-receipt.json").write_text(json.dumps(report), encoding="utf-8")
    (root / "focused.md").write_text("CURRENT_AFTER_COMPACTION", encoding="utf-8")
    report, text = _build(root, "resume")
    assert "CURRENT_AFTER_COMPACTION" in text and report["limitations"]["hostApplied"] is False
    assert report["limitations"]["billedTokens"] == "NOT_CHECKED"


def _invalid(root, doc):
    for event, selected in (("turn", ()), ("turn", ("missing",)), ("turn", ("focused", "FOCUSED")), ("bad", ())):
        _reject(lambda: _build(root, event, selected))
    for field, value in (("id", "other"), ("files", [{"path": "focused.md", "maxBytes": 20, "maxTokens": 20}])):
        bad = copy.deepcopy(doc)
        bad["routes"][0][field] = value
        _save(root, bad)
        _reject(lambda: _build(root))
    _save(root, doc)
    (root / "policy.json").write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
    _reject(lambda: _build(root))
    _save(root, doc)
    _reject(lambda: _build(root, packet_max=20))
    bad = copy.deepcopy(doc)
    bad["routes"][0]["files"][1]["maxTokens"] = 1
    _save(root, bad)
    _reject(lambda: _build(root))
    _save(root, doc)


def _paths_and_drift(root, doc):
    (root / ".rd").mkdir()
    (root / ".rd/private.md").write_text("PRIVATE_HISTORY", encoding="utf-8")
    for value in (".rd/private.md", "../escape.md", "C:/outside.md", "a/../focused.md"):
        bad = copy.deepcopy(doc)
        bad["routes"][0]["files"][1]["path"] = value
        _save(root, bad)
        _reject(lambda: _build(root))
    _save(root, doc)
    # Simulated reparse detection exercises the real shared path guard.
    with patch("sync_safety.link_like", return_value=True):
        _reject(lambda: _build(root))
    original = intake._read_source
    def drifting(base, name):
        if name == "focused.md":
            (root / name).write_text("CHANGED_DURING_EMISSION", encoding="utf-8")
        return original(base, name)
    with patch.object(intake, "_read_source", side_effect=drifting):
        _reject(lambda: _build(root))
    _setup(root)


def _unavailable_and_outputs(root):
    unavailable = Tokenizer(False, None, "missing fixture", None)
    report, text = intake.build(root, "policy.json", "turn", ["focused"], tokenizer=unavailable)
    assert report["status"] == "NOT_CHECKED" and not text
    for output in (root / "SKILL.md", root / ".rd/../SKILL.md", root / "policy.json"):
        try:
            intake._output_path(output, root)
        except (ValueError, OSError):
            pass
        else:
            raise AssertionError("source overwrite path accepted")
    assert intake._output_path(root / ".rd/new.json", root) == root / ".rd/new.json"
    (root / ".rd/existing.json").write_text("{}", encoding="utf-8")
    try:
        intake._output_path(root / ".rd/existing.json", root)
    except ValueError:
        pass
    else:
        raise AssertionError("immutable receipt overwrite accepted")
    # A competing writer arriving after validation must not be replaced.
    output = intake._output_path(root / ".rd/race.json", root)
    output.write_text("COMPETING_WRITER", encoding="utf-8")
    try:
        intake._emit_fresh(output, {"status": "GREEN"}, True)
    except FileExistsError:
        pass
    else:
        raise AssertionError("competing receipt was overwritten")
    assert output.read_text(encoding="utf-8") == "COMPETING_WRITER"


def _cli_errors(root):
    for flags in (["--unknown"], ["--quiet"], ["--event", "bad"], ["--output", str(root / "SKILL.md")]):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = intake.main([str(root), *flags])
        assert code == 1 and not err.getvalue()
        assert json.loads(out.getvalue())["status"] == "BLOCK"
    out = io.StringIO()
    with redirect_stdout(out):
        intake._emit_fresh(None, {"status": "GREEN", "sources": ["NO_SOURCE_DUMP"], "payload": {"tokens": 3, "bytes": 4}}, False)
    summary = json.loads(out.getvalue())
    assert summary["payloadTokens"] == 3 and "sources" not in summary


def run_self_test(api):
    global intake
    intake = api
    with tempfile.TemporaryDirectory(prefix="context-intake-") as raw:
        root = Path(raw).resolve()
        doc = _setup(root)
        _lifecycle(root)
        _setup(root)
        _invalid(root, doc)
        _paths_and_drift(root, doc)
        _unavailable_and_outputs(root)
        _cli_errors(root)
