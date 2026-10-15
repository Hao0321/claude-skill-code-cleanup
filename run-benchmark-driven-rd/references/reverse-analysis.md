# Reverse-analysis provider workflow

REA research source: [morluto/rea](https://github.com/morluto/rea/tree/6fcfc5b5e0c063300cd5278dd8bad5b1ab1374f6), MIT.
No upstream code is copied. REA-authored code and each external engine retain
their own licenses. The optional provider does not replace the Cleanup/R&D gates.

## Choose a lane

| Question | Useful evidence | Boundary |
|---|---|---|
| How does a shipped JS/Electron feature work? | Module/import/IPC graph, source-map and artifact relationships | Static inference is not observed execution |
| How does a native function work? | Ghidra/Hopper/IDA pseudocode, assembly and references | Provider, format, host and licensing support must be verified |
| What can our release expose? | Exact release scan, extracted payload, symbols/maps, binary metadata | A scan or stripped binary cannot prove impossibility of reverse analysis |
| Did an independent implementation match? | Frozen oracle input/output corpus and failure cases | Matching one function does not establish whole-product parity |

## Optional REA commands

Use the installed, pinned CLI/MCP surface. Examples verified against REA 6.5.0:

```text
rea providers --json
rea capabilities --json
rea analyze-javascript-application <owned-or-authorized-extracted-directory> --json
```

For a native lane, first select a configured provider and consult that version's
`--help`; current upstream examples include `rea analyze <file> --provider ghidra
--json`. Windows support is provider-specific. The source-reference import lane
can require Linux/WSL even when another Windows lane works. Do not turn an
unsupported operation into a generic success claim.

Save stdout as full local evidence, child exit and stderr separately. Retain
target/provider/command identities and limitations. Use supported summary/page
views when output is large; do not feed hundreds of MB into default context or
discard the underlying evidence. A local analyzer still sends selected results
to the agent/model provider when the agent reads them; local execution is not a
guarantee that all downstream processing is offline.

This integration's development trial used Node 24.19 and REA 6.5.0 on an owned
three-file JavaScript fixture on Windows. Static relationships were recovered
without executing that fixture. That is a lane-level trial, not native
decompilation, a Windows-wide compatibility claim, or a capability to recover any
application's original source. Exact receipts and raw evidence remain private.

## Release exposure experiment

Run Cleanup's `check_release_exposure.py` on the actual delivery bytes. It reads
files only and emits UTF-8 JSON with hashes, review candidates and explicit gaps.
Review intended debug/source-map publication against product policy. For archives,
retain the envelope hash and separately inspect an authorized extracted payload;
the checker does not execute unpackers or follow embedded paths.

Test clean, deliberately exposed, malformed, oversized, empty and modified-input
controls. Compare the hardened release against the same scope and evaluator.
Keep server-side authorization, secret handling and signed-update validation as
separate functional/security gates. Minification or obfuscation may increase
analysis effort; do not use their presence as a PASS for confidentiality.
