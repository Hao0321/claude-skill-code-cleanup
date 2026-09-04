#!/usr/bin/env python3
"""Self-test fixtures for :mod:`project_profile_gate`."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any


_ROUTER: Any | None = None


def _runtime() -> Any:
    """Return the router API injected by the public self-test wrapper."""
    if _ROUTER is None:
        raise RuntimeError("project profile gate self-test runtime was not provided")
    return _ROUTER


def assert_selection_only(route: dict[str, Any]) -> None:
    assert route["decision"] == "ROUTED"
    assert route["evidenceStatus"] == "NOT_EVALUATED"
    assert route["selectionOnly"] is True
    assert route["gateEvidence"]["status"] == "NOT_EVALUATED"
    assert route["gateEvidence"]["routeOnly"] is True
    assert "PASS" not in json.dumps(route["gateEvidence"])
    assert all(len(value) == 64 for value in route["hashes"].values() if value)


def write_contract(root: Path, name: str, payload: dict[str, Any]) -> Path:
    path = root / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def expect_contract_error(root: Path, name: str, payload: dict[str, Any]) -> None:
    router = _runtime()
    path = write_contract(root, name, payload)
    try:
        router.compose_route(root, contract_path=path)
    except router.ProfileError:
        return
    raise AssertionError(f"malformed fixture was accepted: {name}")


def expect_profile_error(profile: dict[str, Any], label: str) -> None:
    router = _runtime()
    try:
        router.validate_profile(profile)
    except router.ProfileError:
        return
    raise AssertionError(f"weakened profile was accepted: {label}")


def test_security_profile_rejections(profile: dict[str, Any]) -> None:
    def clone() -> dict[str, Any]:
        return json.loads(json.dumps(profile))

    partial = clone()
    partial["routing"]["defaultSecurityAssessmentObligation"][
        "requiredCapabilityObligationIds"
    ].pop()
    expect_profile_error(partial, "partial-security-capability-floor")

    extra = clone()
    extra["routing"]["defaultSecurityAssessmentObligation"][
        "requiredCapabilityObligationIds"
    ].append("security.unexpected")
    expect_profile_error(extra, "extra-security-capability-id")

    case_variant = clone()
    case_variant["routing"]["defaultSecurityAssessmentObligation"][
        "requiredCapabilityObligationIds"
    ][0] = "Security.scan-scope"
    expect_profile_error(case_variant, "case-variant-security-capability-id")

    reordered = clone()
    ids = reordered["routing"]["defaultSecurityAssessmentObligation"][
        "requiredCapabilityObligationIds"
    ]
    ids[0], ids[1] = ids[1], ids[0]
    expect_profile_error(reordered, "reordered-security-capability-floor")

    for mutation, label in (
        (lambda values: values.pop(), "partial-security-control-floor"),
        (lambda values: values.append("security.unexpected"), "extra-security-control-id"),
        (lambda values: values.__setitem__(0, "Security.scan-scope"), "case-security-control-id"),
        (lambda values: values.__setitem__(slice(0, 2), values[1::-1]), "reordered-security-control-floor"),
    ):
        weakened = clone()
        mutation(weakened["routing"]["defaultSecurityAssessmentObligation"][
            "requiredSecurityControlIds"
        ])
        expect_profile_error(weakened, label)

    colliding_intent = clone()
    colliding_intent["taskDimensions"]["intents"].append("Audit")
    expect_profile_error(colliding_intent, "case-folding-intent-collision")

    colliding_topic = clone()
    colliding_topic["topics"]["Security-assessment"] = clone()["topics"][
        "security-assessment"
    ]
    expect_profile_error(colliding_topic, "case-folding-topic-collision")

    for risk in ("high", "critical"):
        missing_topic = clone()
        missing_topic["routing"]["secureUpdaterRiskTopics"][risk].remove(
            "security-assessment"
        )
        expect_profile_error(
            missing_topic, f"{risk}-updater-security-assessment-floor"
        )


def test_legacy_compatibility(base: Path) -> tuple[Path, Path]:
    router = _runtime()
    fixtures = {
        "skill": ("SKILL.md", "---\nname: fixture\n---\n"),
        "web": ("package.json", '{"dependencies":{"next":"1"}}'),
        "database": ("schema.sql", "create table t(id int);"),
        "game": ("project.godot", "[application]"),
        "software": ("pyproject.toml", "[project]\nname='fixture'\n")}
    for kind, (relative, content) in fixtures.items():
        root = base / kind
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        route = router.compose_route(root)
        assert kind in route["projectTypes"] and kind in route["selectedModules"]
        assert route["cleanup"]["provider"] == "code-cleanup-helper"
        assert route["routingMode"] == "legacy-compatible-fallback"
        assert route["references"] == route["legacyReferences"]
        assert route["fallbackReason"] == "task-intent-missing"
        assert_selection_only(route)

    combined = base / "combined"
    combined.mkdir()
    contract = write_contract(combined, "project.json", {"schemaVersion": 1,
        "autoDetect": False,
        "projectTypes": ["web", "database"],
        "modules": ["public-release", "security"],
        "projectGates": ["native-project-gate"],
        "evidenceBindings": {"native-project-gate":
                             ".rd/receipts/native-project-gate.json"}})
    route = router.compose_route(combined, contract_path=contract)
    assert route["cleanup"]["mode"] == "all"
    assert route["selectedModules"] == ["core", "cleanup", "web", "database",
                                         "public-release", "security"]
    assert route["selectedModuleIds"] == route["selectedModules"]
    assert route["routingMode"] == "legacy-compatible-fallback"
    assert route["fallbackReason"] == "task-intent-missing"
    assert route["references"] == ["references/protocol.md", "references/metrics.md",
        "references/tooling-and-architecture-gates.md", "references/capability-obligations.md",
        "../code-cleanup-helper/references/rd-integration.md",
        "references/web-commerce-acceptance.md", "references/security-hardening-gates.md",
        "references/external-change-gates.md", "references/completion-closure.md",
        "references/topics/security-assessment.md"]
    assert route["gates"] == [
        "evaluator-calibration", "capability-ledger", "completion-closure",
        "cleanup-baseline", "cleanup-promotion", "cleanup-evidence-freshness",
        "browser-geometry", "keyboard-dialog-lifecycle", "responsive-journey",
        "schema-migration", "transaction-integrity", "backup-restore",
        "least-privilege", "privacy-preflight", "canonical-target",
        "tag-release-remote-hash", "security-assessment-receipt", "threat-model", "negative-security-fixtures",
        "delivered-security-audit", "native-project-gate"]
    assert route["projectEvidence"] == {"native-project-gate":
                                        ".rd/receipts/native-project-gate.json"}
    assert len(route["contract"]["sha256"]) == 64
    assert_selection_only(route)
    return combined, contract


def test_default_update_obligation_routes(routed: Any) -> None:
    for target_artifact, target_stage, expected_risk in (
        ("skill", "implementation", "high"),
        ("software", "promotion", "high"),
        ("game", "implementation", "high"),
        ("installer", "implementation", "high"),
        ("release", "completion", "critical"),
    ):
        distributable = routed(
            f"default-update-{target_artifact}",
            projectType="skill" if target_artifact == "skill" else "software",
            taskIntent="implementation" if target_stage != "completion" else "completion",
            stage=target_stage, artifact=target_artifact, risk="low",
            contextBudgetTokens=50000,
        )
        assert distributable["task"]["updateObligation"]["status"] == "REQUIRED_DEFAULT"
        assert distributable["task"]["risk"] == expected_risk
        assert "secure-self-update" in distributable["selectedTopicIds"]
        assert "security-assessment" in distributable["selectedTopicIds"]
        assert distributable["task"]["securityAssessmentObligation"]["status"] \
            == "REQUIRED_ROUTE"
        assert {
            "security.scan-scope", "security.scan-coverage",
            "security.scanner-provenance", "security.finding-normalization",
            "security.engine-admission", "security.adapter-integrity",
        }.issubset(distributable["requiredCapabilityObligationIds"])
        assert distributable["task"]["updateObligation"]["authorityEffect"] \
            == "selection-only-no-additional-authority"

    audit_skill = routed("audit-skill-update-excluded", projectType="skill",
        taskIntent="audit", stage="implementation", artifact="skill", risk="low",
        contextBudgetTokens=10000)
    assert audit_skill["task"]["updateObligation"]["status"] == "EXCLUDED"
    assert audit_skill["task"]["risk"] == "low"
    assert "secure-self-update" not in audit_skill["selectedTopicIds"]
    source_iteration = routed("source-update-excluded", taskIntent="implementation",
        stage="implementation", artifact="source", risk="low",
        contextBudgetTokens=10000)
    assert source_iteration["task"]["updateObligation"]["reason"] \
        == "source-only-or-nondistributable-artifact"
    assert source_iteration["requiredCapabilityObligationIds"] == []


def test_security_assessment_routes(routed: Any, profile: dict[str, Any]) -> None:
    security_route = routed("security-assessment", taskIntent="security-assessment",
        stage="baseline", artifact="source", risk="standard",
        contextBudgetTokens=16000)
    obligation = security_route["task"]["securityAssessmentObligation"]
    assert obligation["status"] == "REQUIRED_EXPLICIT"
    assert obligation["authorityEffect"] == "selection-only-no-scan-or-contact-authority"
    assert security_route["task"]["updateObligation"]["status"] == "EXCLUDED"
    assert security_route["requiredCapabilityObligationIds"] \
        == profile["routing"]["defaultSecurityAssessmentObligation"] \
        ["requiredCapabilityObligationIds"]
    assert obligation["requiredSecurityControlIds"] \
        == profile["routing"]["defaultSecurityAssessmentObligation"] \
        ["requiredSecurityControlIds"]
    assert "security-assessment" in security_route["selectedTopicIds"]
    assert {"rd.security.scan-authority-envelope",
        "rd.security.scan-coverage-ledger",
        "rd.security.adapter-evidence-integrity"}.issubset(
            security_route["criticalRuleIds"])
    assert_selection_only(security_route)

    security_audit = routed("security-audit", modules=["security"],
        taskIntent="audit", stage="baseline", artifact="source", risk="standard",
        contextBudgetTokens=16000)
    assert "security-assessment" in security_audit["selectedTopicIds"]
    assert security_audit["task"]["securityAssessmentObligation"]["status"] == "EXCLUDED"
    assert security_audit["task"]["securityAssessmentObligation"][
        "requiredSecurityControlIds"
    ] == []
    assert security_audit["requiredCapabilityObligationIds"] == []
    assert_selection_only(security_audit)


def test_security_route_matrix(routed: Any, profile: dict[str, Any]) -> None:
    router = _runtime()
    fallback_intents = set(profile["taskDimensions"]["fallbackIntents"])
    authorized_intents = [
        intent for intent in profile["taskDimensions"]["intents"]
        if intent != "audit" and intent not in fallback_intents
    ]
    artifacts = ("skill", "software", "game", "installer", "release")
    stages = ("implementation", "promotion", "completion")
    for intent in authorized_intents:
        for target_stage in stages:
            for target_artifact in artifacts:
                route = routed(
                    f"security-matrix-{intent}-{target_stage}-{target_artifact}",
                    projectType=("skill" if target_artifact == "skill" else "software"),
                    taskIntent=intent,
                    stage=target_stage,
                    artifact=target_artifact,
                    risk="low",
                    contextBudgetTokens=100000,
                )
                obligation = route["task"]["securityAssessmentObligation"]
                expected_status = (
                    "REQUIRED_EXPLICIT"
                    if intent == "security-assessment"
                    else "REQUIRED_ROUTE"
                )
                assert "security-assessment" in route["selectedTopicIds"]
                assert obligation["status"] == expected_status
                assert obligation["required"] is True
                assert tuple(obligation["requiredCapabilityObligationIds"]) \
                    == router.SECURITY_CAPABILITY_IDS
                assert tuple(obligation["requiredSecurityControlIds"]) \
                    == router.SECURITY_CAPABILITY_IDS
                assert set(router.SECURITY_CAPABILITY_IDS).issubset(
                    route["requiredCapabilityObligationIds"]
                )
                assert_selection_only(route)

    for intent in profile["taskDimensions"]["intents"]:
        for target_stage, expected_risk in (
            ("implementation", "high"),
            ("promotion", "high"),
            ("completion", "critical"),
        ):
            route = routed(
                f"updater-security-matrix-{intent}-{target_stage}",
                taskIntent=intent,
                stage=target_stage,
                artifact="updater",
                risk="low",
                contextBudgetTokens=100000,
            )
            obligation = route["task"]["securityAssessmentObligation"]
            assert route["task"]["risk"] == expected_risk
            if intent == "audit" or intent in fallback_intents:
                assert obligation["required"] is False
                assert obligation["requiredCapabilityObligationIds"] == []
                assert obligation["requiredSecurityControlIds"] == []
            else:
                assert "security-assessment" in route["selectedTopicIds"]
                assert tuple(obligation["requiredCapabilityObligationIds"]) \
                    == router.SECURITY_CAPABILITY_IDS
                assert tuple(obligation["requiredSecurityControlIds"]) \
                    == router.SECURITY_CAPABILITY_IDS
            assert obligation["authorityEffect"] \
                == "selection-only-no-scan-or-contact-authority"
            assert_selection_only(route)


def run_self_test(router_api: Any) -> None:
    global _ROUTER
    _ROUTER = router_api
    router = _runtime()
    profile = router.load_json(router.DEFAULT_PROFILE)
    router.validate_profile(profile)
    test_security_profile_rejections(profile)
    with tempfile.TemporaryDirectory(prefix="project-profile-gate-") as raw:
        base = Path(raw)
        combined, contract = test_legacy_compatibility(base)

        common = {"schemaVersion": 2, "autoDetect": False, "modules": []}
        def routed(name: str, **values: Any) -> dict[str, Any]:
            payload = {**common, "projectTypes": [values.pop("projectType", "software")],
                       **values}
            return router.compose_route(combined, contract_path=write_contract(
                combined, f"{name}.json", payload))

        focused_route = routed("focused", taskIntent="audit", stage="baseline",
            artifact="source", risk="low", contextBudgetTokens=6000)
        assert focused_route["selectedTopicIds"] == ["core-experiment",
            "context-and-learning", "focused-audit", "baseline-evidence"]
        assert len(focused_route["selectedTopicIds"]) <= 5
        assert not set(focused_route["references"]) & {"references/metrics.md",
            "references/tooling-and-architecture-gates.md",
            "references/capability-obligations.md", "references/media-artifact-evidence.md"}
        assert focused_route["contextBudget"]["status"] == "WITHIN_BUDGET"
        assert_selection_only(focused_route)

        model_route = routed("model", projectType="skill", taskIntent="model-context",
            stage="implementation", artifact="skill", risk="standard",
            contextBudgetTokens=16000)
        assert {"references/model-and-reasoning-gates.md",
            "../code-cleanup-helper/references/model-context-contract-audit.md"}.issubset(
                model_route["references"])
        assert "references/metrics.md" not in model_route["references"]
        assert model_route["task"]["updateObligation"]["status"] == "REQUIRED_DEFAULT"
        assert model_route["task"]["risk"] == "high"
        assert {"secure-self-update", "delivery-artifact", "security-hardening"}.issubset(
            model_route["selectedTopicIds"])
        assert "security-assessment" in model_route["selectedTopicIds"]
        assert model_route["requiredCapabilityObligationIds"] == [
            "update.client-check", "update.release-channel",
            *profile["routing"]["defaultSecurityAssessmentObligation"]
            ["requiredCapabilityObligationIds"],
        ]
        assert_selection_only(model_route)

        test_security_assessment_routes(routed, profile)

        test_default_update_obligation_routes(routed)
        test_security_route_matrix(routed, profile)

        completion_route = routed("completion", modules=["public-release"],
            taskIntent="completion", stage="completion", artifact="release",
            risk="critical", contextBudgetTokens=50000)
        assert {"references/capability-obligations.md", "references/completion-closure.md",
            "references/external-change-gates.md", "references/delivery-artifact-gates.md",
            "references/security-hardening-gates.md"}.issubset(completion_route["references"])
        assert {"rd.external.current-authority", "completion.last-mutation-barrier"}.issubset(
            completion_route["criticalRuleIds"])
        assert_selection_only(completion_route)

        updater_contract = write_contract(combined, "updater.json", {**common,
            "projectTypes": ["software"], "taskIntent": "secure-self-update",
            "stage": "discovery", "artifact": "updater", "risk": "low",
            "contextBudgetTokens": 6000})
        updater_route = router.compose_route(combined, contract_path=updater_contract)
        assert updater_route["selectedTopicIds"] == ["core-experiment",
            "context-and-learning", "secure-self-update"]
        assert updater_route["task"]["updateObligation"]["status"] == "REQUIRED_EXPLICIT"
        assert updater_route["requiredCapabilityObligationIds"] == [
            "update.client-check", "update.release-channel"]
        assert updater_route["task"]["safetyAdjustments"] == []
        assert not set(updater_route["references"]) & {"references/delivery-artifact-gates.md",
            "references/security-hardening-gates.md", "references/external-change-gates.md"}
        assert {"rd.updater.safe-client", "rd.updater.side-by-side",
            "rd.updater.workspace-ownership", "rd.updater.upgrade-matrix",
            "rd.updater.runtime-entrypoint",
            "rd.updater.health-rollback", "rd.updater.retirement",
            "rd.updater.user-control", "rd.updater.receipt"}.issubset(
                updater_route["criticalRuleIds"])
        assert_selection_only(updater_route)

        for updater_stage, effective_risk in (("implementation", "high"),
                                               ("promotion", "high"),
                                               ("completion", "critical")):
            staged = router.compose_route(combined, contract_path=updater_contract,
                stage=updater_stage, risk="standard", context_budget_tokens=50000)
            assert staged["task"]["declaredRisk"] == "standard"
            assert staged["task"]["risk"] == effective_risk
            assert staged["task"]["safetyAdjustments"][0]["ruleId"] == "rd.updater.safe-client"
            assert {"delivery-artifact", "security-hardening", "security-assessment"}.issubset(
                staged["selectedTopicIds"])
            assert staged["task"]["securityAssessmentObligation"]["required"] is True
            if updater_stage == "completion":
                assert {"completion-core", "completion-detail"}.issubset(
                    staged["selectedTopicIds"])
            assert_selection_only(staged)

        for label, intent_value, reason, budget in (
            ("missing", None, "task-intent-missing", 512),
            ("mixed", "mixed", "task-intent-ambiguous:mixed", 12000)):
            payload = {**common, "projectTypes": ["software"],
                "contextBudgetTokens": budget, **({"taskIntent": intent_value}
                if intent_value else {})}
            fallback = router.compose_route(combined, contract_path=write_contract(
                combined, f"{label}-intent.json", payload))
            assert fallback["routingMode"] == "legacy-compatible-fallback"
            assert fallback["fallbackReason"] == reason
            assert fallback["references"] == fallback["legacyReferences"]
            assert_selection_only(fallback)
        assert fallback["references"]

        cli_route = router.compose_route(combined, contract_path=contract,
            task_intent="audit", stage="baseline", artifact="source", risk="low",
            context_budget_tokens=50000)
        assert cli_route["routingMode"] == "task-aware-v2"
        assert all(cli_route["task"]["sources"][field] == "cli" for field in
            ("intent", "stage", "artifact", "risk", "contextBudgetTokens"))
        assert_selection_only(cli_route)
        parsed = router.build_parser().parse_args(["--task-intent", "audit", "--stage",
            "baseline", "--artifact", "source", "--risk", "low",
            "--context-budget-tokens", "6000"])
        assert (parsed.task_intent, parsed.context_budget_tokens) == ("audit", 6000)

        valid = {**common, "projectTypes": ["software"], "taskIntent": "audit",
            "stage": "baseline", "artifact": "source", "risk": "low",
            "contextBudgetTokens": 6000}
        for field, value in (("taskIntent", "unknown-intent"),
                             ("stage", "unknown-stage"),
                             ("artifact", "unknown-artifact"),
                             ("risk", "unknown-risk")):
            payload = dict(valid)
            payload[field] = value
            expect_contract_error(combined, f"invalid-{field}.json", payload)
        malformed = (
            ("project-type", {"schemaVersion": 1, "projectTypes": ["unknown"]}),
            ("gate", {"schemaVersion": 1, "projectGates": ["x", "x"]}),
            ("schema1-task", {"schemaVersion": 1, "taskIntent": "audit"}),
            ("budget-type", {"schemaVersion": 2, "taskIntent": "audit",
                             "contextBudgetTokens": True}),
            ("budget-range", {"schemaVersion": 2, "taskIntent": "audit",
                              "contextBudgetTokens": 1}),
            ("budget-overflow", {**valid, "contextBudgetTokens": 512}),
        )
        for name, payload in malformed:
            expect_contract_error(combined, f"invalid-{name}.json", payload)
        try:
            router.compose_route(combined, task_intent="unknown-intent")
        except router.ProfileError:
            pass
        else:
            raise AssertionError("unknown CLI task intent was accepted")
