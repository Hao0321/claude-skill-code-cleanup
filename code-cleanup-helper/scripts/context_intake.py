#!/usr/bin/env python3
"""Plan/emit bounded workflow context, not change a host's injected prompt."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from check_context_budget import ENCODING, ContextBudgetError, JsonParser, _emit, _json_object, evaluate, load_tokenizer
from sync_safety import PRIVATE_DIRS, checked_root, privacy_check, read_bytes, safe_path

EVENTS = ("startup", "turn", "resume")
LIMITATIONS = {
    "hostApplied": False, "hostInjectionTokens": "NOT_CHECKED", "billedTokens": "NOT_CHECKED",
    "cacheHits": "NOT_CHECKED", "modelConsumption": "NOT_CHECKED",
    "scope": "Declared workflow payload only; mandatory host reads still apply. Disk receipts do not prove resident model context.",
}


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _public_path(root, name):
    if not isinstance(name, str) or any(p.casefold() in PRIVATE_DIRS | {".cleanup-evidence"} for p in name.split("/")):
        raise ValueError("private context paths require separate explicit retrieval")
    return safe_path(root, name)


def _read_source(root, name):
    data = read_bytes(_public_path(root, name))
    privacy_check(data, name, {})
    return data, data.decode("utf-8-sig")


def _catalog(text):
    match = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|$)", text.replace("\r\n", "\n"), re.S)
    if not match:
        raise ValueError("SKILL.md frontmatter is missing")
    values = {}
    for key in ("name", "description"):
        rows = re.findall(r"^" + key + r":[ \t]*(.*)$", match[1], re.M)
        if len(rows) != 1 or not rows[0].strip() or rows[0].strip()[0] in "|>[{":
            raise ValueError("catalog requires unique, inline name/description scalars")
        raw = rows[0].strip()
        if raw.startswith('"'):
            raw = json.loads(raw)
        elif raw.startswith("'"):
            if not raw.endswith("'"):
                raise ValueError("unterminated catalog scalar")
            raw = raw[1:-1].replace("''", "'")
        if not isinstance(raw, str) or not raw or "\n" in raw or "\r" in raw:
            raise ValueError("invalid catalog scalar")
        values[key] = raw
    return f"Skill: {values['name']}\nDescription: {values['description']}\nPath: SKILL.md\n"


def _routes(document, selected):
    if not isinstance(document, dict) or set(document) != {"schemaVersion", "tokenizer", "routes"}:
        raise ValueError("unsupported context manifest fields")
    if type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1 or document["tokenizer"] != ENCODING:
        raise ValueError("unsupported context schema/tokenizer")
    if not isinstance(document["routes"], list) or not 1 <= len(document["routes"]) <= 256:
        raise ValueError("manifest routes must be non-empty")
    available = {}
    for row in document["routes"]:
        name = row.get("id") if isinstance(row, dict) else None
        if not isinstance(name, str) or not name.strip() or name != name.strip() or name.casefold() in available:
            raise ValueError("invalid or duplicate route ID")
        available[name.casefold()] = row
    if len({s.casefold() for s in selected}) != len(selected):
        raise ValueError("duplicate requested route")
    if any(s.casefold() not in available for s in selected):
        raise ValueError("unknown route; choose a known route or explicit legacy fallback")
    return [available[s.casefold()] for s in selected]


def _selected(root, document, routes, tokenizer):
    paths = {}
    for route in routes:
        if not isinstance(route.get("files"), list) or not 1 <= len(route["files"]) <= 64 or not any(isinstance(f, dict) and f.get("path") == "SKILL.md" for f in route["files"]):
            raise ValueError("selected routes must retain the critical SKILL.md entry")
        for item in route["files"]:
            if not isinstance(item, dict):
                raise ValueError("invalid route file")
            path = _public_path(root, item.get("path"))
            paths[str(path).casefold()] = path
    if len(paths) > 128 or sum(path.stat().st_size for path in paths.values()) > 2 * 1024 * 1024:
        raise ValueError("selected source set exceeds read bounds")
    measured = evaluate({**document, "routes": routes}, root, tokenizer=tokenizer)
    if measured["status"] != "GREEN":
        return measured, [], []
    parts, sources = [], []
    for item in measured["inventory"]:
        data, text = _read_source(root, item["path"])
        if _digest(data) != item["sha256"]:
            raise ValueError("source drift between measurement and emission")
        parts.append(f"## {item['path']}\n{text}")
        sources.append({**item, "projection": "full", "reason": "selected-route"})
    return measured, parts, sources


def build(root, manifest="profiles/context-budget.json", event="startup", selected=(), *, tokenizer=None,
          catalog_max=128, packet_max=6000):
    if event not in EVENTS or any(type(v) is not int or v <= 0 for v in (catalog_max, packet_max)):
        raise ValueError("invalid event or budget")
    root = checked_root(Path(root))
    tokenizer = tokenizer or load_tokenizer()
    manifest_bytes, manifest_text = _read_source(root, manifest)
    document = json.loads(manifest_text, object_pairs_hook=_json_object)
    routes = _routes(document, selected)
    if event == "turn" and not routes:
        raise ValueError("turn intake requires a selected route; no silent critical-rule omission")
    report = {"schemaVersion": 1, "status": "GREEN", "event": event, "selectionOnly": True,
              "selectedRouteIds": [r["id"] for r in routes], "manifestSha256": _digest(manifest_bytes),
              "tokenizer": tokenizer.as_json(), "sources": [], "catalogTokens": 0,
              "cadence": {"hostMandatory": "host-controlled; never skipped by this tool", "startup": "catalog only unless routes selected", "turn": "selected routes only", "resume": "cold catalog and selected routes", "rawHistory": "never auto-loaded"},
              "limitations": dict(LIMITATIONS)}
    if not tokenizer.available or tokenizer.count is None:
        return {**report, "status": "NOT_CHECKED", "reason": "exact tokenizer unavailable"}, ""
    parts = []
    if event in {"startup", "resume"}:
        data, text = _read_source(root, "SKILL.md")
        catalog = _catalog(text)
        report["catalogTokens"] = tokenizer.count(catalog)
        if report["catalogTokens"] > catalog_max:
            raise ValueError("catalog token budget exceeded; shorten metadata, not critical rules")
        parts.append(catalog)
        report["sources"].append({"path": "SKILL.md", "sha256": _digest(data), "projection": "name-description-path", "reason": "startup-or-resume"})
    if routes:
        measured, details, sources = _selected(root, document, routes, tokenizer)
        report["routeBudgetStatus"] = measured["status"]
        if measured["status"] != "GREEN":
            return {**report, "status": measured["status"], "findings": measured["findings"]}, ""
        parts.extend(details)
        report["sources"].extend(sources)
    packet = "\n".join(parts)
    tokens = tokenizer.count(packet)
    if tokens > packet_max:
        raise ValueError("aggregate packet token budget exceeded; no content was truncated")
    if _digest(read_bytes(_public_path(root, manifest))) != report["manifestSha256"]:
        raise ValueError("manifest changed during intake")
    for source in report["sources"]:
        if _digest(read_bytes(_public_path(root, source["path"]))) != source["sha256"]:
            raise ValueError("source changed during intake")
    report["payload"] = {"bytes": len(packet.encode("utf-8")), "tokens": tokens,
                         "sha256": _digest(packet.encode("utf-8")), "framingIncluded": True,
                         "scope": "packet text only; excludes JSON/tool framing and existing prompt"}
    return report, packet


def _output_path(output, root):
    if output is None:
        return
    parent = checked_root(output.absolute().parent, allow_missing=True)
    output = safe_path(parent, output.name)
    if output.exists():
        raise ValueError("use a fresh receipt path; existing files are never overwritten")
    try:
        relative = output.absolute().relative_to(root).as_posix()
    except ValueError:
        return output
    if relative.split("/")[0] not in {".rd", ".cleanup-evidence"}:
        raise ValueError("receipts inside the source root must be in an evidence directory")
    return output


def build_parser():
    parser = JsonParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="profiles/context-budget.json")
    parser.add_argument("--event", choices=EVENTS, default="startup")
    parser.add_argument("--route", action="append", default=[])
    parser.add_argument("--catalog-max-tokens", type=int, default=128)
    parser.add_argument("--packet-max-tokens", type=int, default=6000)
    parser.add_argument("--emit-packet", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def run_self_test():
    from context_intake_selftest import run_self_test as replay
    replay(sys.modules[__name__])


def _emit_fresh(output, report, quiet):
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        checked_root(output.parent)
        # Exclusive creation also rejects a writer arriving after path preflight.
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if not quiet:
        summary = {key: report[key] for key in ("status", "event", "selectedRouteIds", "reason", "selfTest", "packetText") if key in report}
        if "payload" in report:
            summary["payloadTokens"] = report["payload"]["tokens"]
            summary["payloadBytes"] = report["payload"]["bytes"]
        if "findings" in report:
            summary["findings"] = report["findings"]
        summary["hostApplied"] = False
        summary["billedTokens"] = "NOT_CHECKED"
        _emit(None, summary, False)


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        if args.quiet and (args.output is None or args.emit_packet):
            raise ContextBudgetError("--quiet needs --output and cannot emit packet text")
        root = checked_root(args.root)
        args.output = _output_path(args.output, root)
        if args.self_test:
            run_self_test()
            report = {"schemaVersion": 1, "status": "GREEN", "selfTest": "passed", "limitations": dict(LIMITATIONS)}
        else:
            report, packet = build(root, args.manifest, args.event, args.route,
                                   catalog_max=args.catalog_max_tokens, packet_max=args.packet_max_tokens)
            if args.emit_packet and report["status"] == "GREEN":
                report["packetText"] = packet
        _emit_fresh(args.output, report, args.quiet)
    except (OSError, ValueError, RuntimeError, UnicodeError, RecursionError) as exc:
        report = {"schemaVersion": 1, "status": "BLOCK", "reason": str(exc), "limitations": dict(LIMITATIONS)}
        # An unsafe output is not permission to write the failure over source.
        print(json.dumps(report, ensure_ascii=False))
        return 1
    return 0 if report["status"] == "GREEN" else 2 if report["status"] == "NOT_CHECKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
