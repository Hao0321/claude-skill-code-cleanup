# Security hardening gates

## Claim boundary

No client-side desktop application can guarantee that a determined user will never unpack, debug or intercept it. Define falsifiable properties instead:

- shipped payload contains no source maps, source, debug symbols, secrets, private paths or undeclared native executables;
- production resolves only manifest-owned runtimes and cannot use environment variables to replace executable paths or bypass signature policy;
- updates fail closed on transport, size, hash and signer identity drift;
- privileged desktop／agent／Remote boundaries reject unauthorized callers;
- public packages are signed and contain only redistributable assets;
- platform binaries expose required exploit mitigations.

Obfuscation, packers and embedded encryption keys may be measured as reverse-engineering cost experiments, but never close a credential, integrity, entitlement or redistribution obligation. Treat antivirus false positives, startup regression and crash diagnosability as guardrails.

## Threat model before implementation

Name actors and assets: malicious web content, same-LAN browser, forged updater, modified environment, compromised project file, symlinked workspace, curious package recipient, leaked signing secret and accidental public build. For each boundary write one property, one attack fixture and one authoritative observation.

Separate:

- confidentiality: no secret or private path shipped／logged;
- integrity: exact payload, hash, signature and runtime identity;
- authorization: sender, Origin, session, entitlement and workspace boundary;
- availability: request／body／session／rate bounds and safe fallback;
- redistribution: public rights are independent of file existence or encryption.

## Desktop and local-agent gates

For Tauri／Electron or similar shells, require local trusted content, restrictive CSP, sandbox／context isolation, no generic IPC bridge, sender validation, navigation／window／permission denial and exact-path custom protocols. Production helper executables must be bundle-owned; development overrides need a compile-time or packaged guard plus a negative test proving release ignores the variable.

Pin the runtime that performs the build, not merely the runtime shipped in the installer. PATH precedence is insufficient on Windows because wrappers such as `npm.cmd` may invoke a sibling `node.exe`. The process that actually runs compile／bundle steps must emit a receipt with version, bundle-owned relative source and executable SHA-256; lock that receipt into the build input identity and embedded manifest. Reading `process.version` later from the evidence collector is not build provenance.

Agent workspaces require both lexical containment and canonical filesystem containment. Include a real symlink／junction escape fixture for every project, media and output path class; string `..` tests alone are insufficient.

## Remote-control gates

QR bootstrap belongs in a URL fragment, expires quickly and exchanges for an HttpOnly／SameSite session or per-device credential. For “scan once”／permanent binding, generate a separate high-entropy credential per device, store only its one-way hash on the host, retain the raw value only in an HttpOnly cookie or OS vault, rotate on re-pair, and support exact-device revocation. Test constant-time bootstrap comparison, same-origin JSON mutation, Fetch Metadata when available, pairing and command rate limits, bounded bodies／headers／requests, generic server errors, private-path omission and session/device revocation. Inline UI can use CSP nonce or exact SHA-256 hashes; merely setting a CSP that still includes unrestricted `unsafe-inline` is diagnostic.

A permanent-pairing promotion must restart the service/app and reconnect without the QR, prove stop preserves the binding, prove explicit revoke immediately rejects the old credential, and prove no raw long-lived credential appears in the host store, URL, logs, receipts or installer. Device ID/localStorage values are not secrets and cannot authenticate. Stable URL/port reachability, owned HTTPS tunnel, browser storage eviction and lost-device recovery are separate availability obligations.

Replay both sides of every policy change: calibrated cross-origin／missing-Origin attacks must be rejected, while the real delivered pairing and command client must send the accepted Origin／content-type contract and still complete. A security control that silently breaks the authorized product journey is not promotion-ready.

Named HTTPS tunnel ownership, certificate and real-device cross-network acceptance are separate external obligations. A debug Quick Tunnel does not close production availability or trust.

## Delivered-artifact gate

Inspect the actual installer or app bundle with a pinned／hashed extraction tool. Build-directory binaries are non-authoritative. Use a closed-world payload allowlist and scan bounded text files without echoing matched secrets into reports. Reject source maps, source, PDB, private-key formats, credential-shaped tokens, private absolute paths and unexpected EXE／DLL／dylib／so entries.

Read the delivered binary header and signature. On Windows x64, require ASLR (`DYNAMIC_BASE`), NX compatibility and High Entropy VA; report Control Flow Guard separately unless the toolchain has a calibrated requirement. Public promotion requires valid Authenticode and exact signer identity. macOS promotion requires Developer ID verification and notarization on a real macOS runner.

Internal and public resource profiles must be distinct. The public gate rejects owner-only music, models, datasets or references even when the internal installer intentionally carries them. If entitlement is required, prefer authenticated per-user download, short-lived URLs, OS credential storage and revocation. Once offline bytes are decoded on the customer device, promise increased extraction cost, not impossibility.

## Calibration and closure

Before trusting the gate, inject at least: a `.map`, undeclared executable, private-key marker, private absolute path, missing PE mitigation, unsigned public artifact, restricted public asset, runtime environment override, stale／unowned build runtime receipt, cross-origin Remote request and workspace symlink escape. Every fixture must change the decision to BLOCK.

Wire the project-native security gate into the canonical build after packaging, retain machine evidence, and add security properties to the capability-obligation ledger. Signing credentials, app-store identities, public HTTPS ownership, rights provenance and real devices stay `blocked_external` until authoritative acceptance exists.

When a nested journey fails, the parent runner must retain bounded child stderr and fall back to bounded stdout／machine receipt when stderr is empty. A bare child exit code is not enough to localize or reproduce a release blocker.

Any security evaluator or policy change invalidates prior product promotion. Re-capture the current Skill revisions, re-read latest routed instructions, rerun evaluator self-tests, strict Cleanup promotions, delivered journey, security gate and completion closure after the final mutation.

For mixed-language products, an explicit Cleanup `cross-language-architecture-not-checked` remains an honest unmeasured dimension. A project-native TypeScript／Rust graph／cycle／layer gate supplements it but never relabels the Cleanup provider output. Completion may require only the Cleanup dimensions that provider actually measured, but it must independently require the native architecture evidence and preserve both evaluator identities.

Do not close long-file or responsibility-hotspot findings by increasing global thresholds merely to make a gate green. Extract a named responsibility while preserving the previous threshold, then replay typecheck, unit tests, native architecture and the authoritative delivered UI journey. Threshold calibration is an evaluator change and requires a representative corpus, a retained old case and downstream evidence recapture.

Treat evaluator CLI parsing as part of the measurement boundary. Option values such as the path after `--output` must be excluded from positional target discovery; exercise both implicit-default-root and explicit-root orderings, then assert the persisted report's resolved target identity. Exit zero or an evidence file at the requested location cannot prove the intended repository was measured. Separately calibrate the outer wrapper／transpiler: if it consumes the evaluator's flag before child startup, launch through a direct pinned-runtime loader or verified separator and retain the effective child argv. An application-parser unit test does not prove wrapper-level argument delivery.
