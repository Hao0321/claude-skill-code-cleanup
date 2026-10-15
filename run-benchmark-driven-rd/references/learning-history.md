# Shared learning replay status

The current topic index distinguishes live replay from retained historical claims. Earlier state-integrity
promotion receipts and the historical state index are retained with their original bytes. Their original
immutable project experiments are unavailable in this installation, so their current rules are provisional
and diagnostic, with the old claim and experiment IDs preserved in `historicalClaim`. This does not erase the
rules or prove the original work failed. It prevents an unavailable historical experiment from being counted
as current verified evidence.

`profiles/reverse-exposure-record.json` is a deliberately sanitized typed experiment record, not a raw project
log. It binds one shared static-exposure rule to the owned fixture source, positive and negative controls, and
a current promotion receipt. Run `python scripts/verify_learning_bundle.py` to replay it in a temporary ledger;
raw project histories are neither copied nor required. Its scope excludes runtime behavior, comprehensive
secret detection and resistance to arbitrary reverse engineering.

The verifier runs current owned calibration in an isolated `python -I` process, ignoring inherited Python import/optimization settings. Its separate `currentCalibration` receipt binds the seven replay/checker/helper/fixture sources and interpreter executable before and after replay. Bounded, unique record declarations and final document freshness are checked. These current hashes do not rewrite the original experiment, attest the full operating system, or prove a user's product safe.
