# Security hardening card

## Applicability

Use for high-risk implementation/promotion, public or installer artifacts, secure updaters, privileged desktop/agent boundaries, credentials, or untrusted input. Exclude ordinary low-risk design. Load `../security-hardening-gates.md` for a specialized remote-pairing, platform-signing, binary-mitigation, mixed-language, or entitlement claim; legacy fallback retains the full contract.

## Rules

- `rd.security.explicit-threat-model`: name actors, assets, trust boundaries, falsifiable confidentiality/integrity/authorization/availability/redistribution properties, and one attack fixture per applicable boundary.
- `rd.security.owned-runtime`: production uses manifest-owned runtimes/helpers and rejects environment replacement, unauthorized callers, generic IPC, path escapes, traversal, and symlink/junction escape.
- `rd.security.artifact-inspection`: `security.no-secrets-or-private-paths-in-payload` — inspect the extracted authoritative artifact with pinned tools; reject source maps, secrets, private paths, undeclared executables, debug payload, and unauthorized assets.
- `rd.security.identity-drift`: `security.fail-closed-on-identity-drift` — fail closed on transport, size, hash, signer, runtime, receipt, platform, trust-policy, or evaluator drift; authorization success cannot replace identity evidence.
- `rd.security.external-obligations`: keep signing identities, public HTTPS/update ownership, legal rights, stores, and real-device acceptance blocked externally until authoritative evidence exists.

## Evidence and calibration

Retain threat model, exact artifact/runtime hashes, extraction and payload scan, caller/path policy results, signer/trust identity, negative controls, delivered authorized journey, and current evaluator revision. Do not echo secrets.

False green: obfuscation, antivirus status, an authenticated session, source scan, or a security tool exit code is treated as delivered safety.

Negative fixtures: `.map`; private-key marker; private path; undeclared executable; runtime override; forged signer/hash; unauthorized caller; workspace symlink escape; restricted public asset. Every applicable fixture must change the decision to BLOCK while the real authorized journey still passes.
