"""Immutable task-class and updater fixtures for the router quality corpus."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


BASE_TOPICS = ("core-experiment", "context-and-learning")
BASE_RULES = ("rd.core.truthful-verdict", "rd.context.critical-fallback")
SECURITY_CAPABILITY_IDS = (
    "security.scan-scope",
    "security.scan-coverage",
    "security.scanner-provenance",
    "security.finding-normalization",
    "security.engine-admission",
    "security.adapter-integrity",
)
VARIANTS = ("direct-positive", "near-miss-negative", "stale-or-distractor")


@dataclass(frozen=True)
class ClassSpec:
    task_class: str
    intent: str | None
    stage: str
    artifact: str
    risk: str
    expected_topics: tuple[str, ...]
    required_rules: tuple[str, ...]
    forbidden_topics: tuple[str, ...] = ()
    project_types: tuple[str, ...] = ("software",)
    max_selected_topics: int | None = 5
    cap_policy: str = "default-five-card-cap"
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    task_class: str
    variant: str
    contract: dict[str, Any]
    expected_mode: str
    expected_fallback_reason: str | None
    expected_topics: tuple[str, ...]
    required_rules: tuple[str, ...]
    forbidden_topics: tuple[str, ...]
    expected_effective_risk: str
    expected_adjustment_rules: tuple[str, ...] = ()
    max_selected_topics: int | None = 5
    cap_policy: str = "default-five-card-cap"
    flags: tuple[str, ...] = ()


CLASS_SPECS = (
    ClassSpec(
        "mixed-ts-rust-audit",
        "audit",
        "discovery",
        "source",
        "low",
        (*BASE_TOPICS, "focused-audit"),
        (*BASE_RULES, "audit.read-only-unless-implementation-authorized"),
        ("benchmark-metrics", "media-evidence", "model-context", "completion-detail"),
        flags=("audit-authorization", "mixed-language-not-checked"),
    ),
    ClassSpec(
        "architecture",
        "architecture",
        "discovery",
        "source",
        "standard",
        (*BASE_TOPICS, "architecture-evaluation"),
        (*BASE_RULES, "rd.arch.one-owner", "rd.arch.cleanup-provider"),
        ("benchmark-metrics", "media-evidence", "completion-detail"),
    ),
    ClassSpec(
        "implementation",
        "implementation",
        "implementation",
        "source",
        "low",
        (*BASE_TOPICS, "implementation-discipline"),
        (*BASE_RULES, "rd.core.smallest-decisive"),
        ("benchmark-metrics", "media-evidence", "completion-detail"),
    ),
    ClassSpec(
        "benchmark",
        "benchmark",
        "baseline",
        "source",
        "standard",
        (*BASE_TOPICS, "benchmark-metrics", "baseline-evidence"),
        (*BASE_RULES, "benchmark.same-provenance-only", "baseline.existing-failures-remain-evidence"),
        ("implementation-discipline", "media-evidence", "completion-detail"),
    ),
    ClassSpec(
        "model-context",
        "model-context",
        "discovery",
        "source",
        "standard",
        (*BASE_TOPICS, "model-context"),
        (*BASE_RULES, "context.typed-contract-binds-semantic-router"),
        ("benchmark-metrics", "media-evidence", "completion-detail"),
    ),
    ClassSpec(
        "completion",
        "completion",
        "completion",
        "source",
        "standard",
        (*BASE_TOPICS, "completion-detail"),
        (*BASE_RULES, "rd.complete.fresh-close", "completion.last-mutation-barrier"),
        ("benchmark-metrics", "media-evidence", "model-context"),
    ),
    ClassSpec(
        "security-assessment",
        "security-assessment",
        "baseline",
        "source",
        "standard",
        (*BASE_TOPICS, "security-assessment", "baseline-evidence"),
        (*BASE_RULES, "rd.security.scan-authority-envelope",
         "rd.security.scan-coverage-ledger", "rd.security.adapter-evidence-integrity"),
        ("media-evidence", "model-context", "completion-detail", "secure-self-update"),
        flags=("security-assessment",),
    ),
    ClassSpec(
        "external-release",
        "external-change",
        "completion",
        "release",
        "standard",
        (*BASE_TOPICS, "external-detail", "completion-detail", "delivery-artifact",
         "security-hardening", "security-assessment", "architecture-evaluation", "completion-core",
         "secure-self-update"),
        (*BASE_RULES, "rd.external.current-authority", "rd.external.postverify",
         "delivery.source-tests-do-not-prove-shipped-bytes",
         "rd.updater.default-obligation", "rd.updater.user-control"),
        ("media-evidence", "model-context", "benchmark-metrics"),
        max_selected_topics=10,
        cap_policy="documented-external-release-update-closure-route",
        flags=("external-release", "default-updater"),
    ),
    ClassSpec(
        "mcp-session-ai-skill",
        "model-context",
        "discovery",
        "skill",
        "standard",
        (*BASE_TOPICS, "model-context", "skill-artifact"),
        (*BASE_RULES, "context.typed-contract-binds-semantic-router", "skill.current-private-bytes-are-authoritative"),
        ("benchmark-metrics", "media-evidence", "delivery-artifact", "completion-detail"),
        project_types=("skill",),
        flags=("session-ai",),
    ),
    ClassSpec(
        "web-product",
        "implementation",
        "implementation",
        "web",
        "low",
        (*BASE_TOPICS, "implementation-discipline", "web-product"),
        (*BASE_RULES, "rd.core.smallest-decisive", "web.live-geometry-not-dom-presence"),
        ("benchmark-metrics", "media-evidence", "completion-detail", "security-hardening"),
    ),
    ClassSpec(
        "database-integrity",
        "architecture",
        "discovery",
        "database",
        "standard",
        (*BASE_TOPICS, "architecture-evaluation", "database-integrity"),
        (*BASE_RULES, "rd.arch.one-owner", "database.migration-and-rollback-evidence-required"),
        ("web-product", "media-evidence", "benchmark-metrics", "completion-detail"),
    ),
    ClassSpec(
        "game-delivery-media",
        "implementation",
        "implementation",
        "game",
        "standard",
        (*BASE_TOPICS, "implementation-discipline", "delivery-artifact", "media-evidence",
         "architecture-evaluation", "secure-self-update", "security-hardening", "security-assessment"),
        (*BASE_RULES, "rd.core.smallest-decisive",
         "delivery.extracted-envelope-is-authority", "media.decoded-user-output-is-authority",
         "rd.updater.default-obligation", "rd.updater.safe-client",
         "rd.updater.user-control"),
        ("benchmark-metrics", "model-context", "completion-detail"),
        max_selected_topics=9,
        cap_policy="documented-game-delivery-update-route",
        flags=("specialized-media", "default-updater"),
    ),
    ClassSpec(
        "skill-iteration-update-default",
        "implementation",
        "implementation",
        "skill",
        "low",
        (*BASE_TOPICS, "implementation-discipline", "skill-artifact",
         "architecture-evaluation", "secure-self-update", "delivery-artifact",
         "security-hardening", "security-assessment"),
        (*BASE_RULES, "skill.current-private-bytes-are-authoritative",
         "rd.updater.default-obligation", "rd.updater.safe-client",
         "rd.updater.user-control"),
        ("benchmark-metrics", "media-evidence", "completion-detail"),
        project_types=("skill",),
        max_selected_topics=9,
        cap_policy="documented-skill-update-safety-route",
        flags=("default-updater",),
    ),
    ClassSpec(
        "software-promotion-update-default",
        "implementation",
        "promotion",
        "software",
        "low",
        (*BASE_TOPICS, "implementation-discipline", "promotion-evidence",
         "delivery-artifact", "architecture-evaluation", "secure-self-update",
         "security-hardening", "security-assessment"),
        (*BASE_RULES, "promotion.final-evidence-must-be-fresh",
         "rd.updater.default-obligation", "rd.updater.safe-client",
         "rd.updater.user-control"),
        ("benchmark-metrics", "media-evidence", "completion-detail"),
        max_selected_topics=9,
        cap_policy="documented-software-update-promotion-route",
        flags=("default-updater",),
    ),
    ClassSpec(
        "installer-implementation-update-default",
        "implementation",
        "implementation",
        "installer",
        "low",
        (*BASE_TOPICS, "implementation-discipline", "delivery-artifact",
         "security-hardening", "security-assessment", "architecture-evaluation", "secure-self-update"),
        (*BASE_RULES, "delivery.source-tests-do-not-prove-shipped-bytes",
         "rd.updater.default-obligation", "rd.updater.safe-client",
         "rd.updater.user-control"),
        ("benchmark-metrics", "media-evidence", "completion-detail"),
        max_selected_topics=8,
        cap_policy="documented-installer-update-safety-route",
        flags=("default-updater",),
    ),
    ClassSpec(
        "skill-audit-update-excluded",
        "audit",
        "baseline",
        "skill",
        "low",
        (*BASE_TOPICS, "focused-audit", "baseline-evidence", "skill-artifact"),
        (*BASE_RULES, "audit.read-only-unless-implementation-authorized",
         "skill.current-private-bytes-are-authoritative"),
        ("secure-self-update", "delivery-artifact", "security-hardening", "security-assessment"),
        project_types=("skill",),
        flags=("audit-authorization", "update-excluded"),
    ),
    ClassSpec(
        "ambiguous-legacy-fallback",
        "mixed",
        "discovery",
        "software",
        "standard",
        ("legacy-full-module-route",),
        ("rd.context.critical-fallback", "rd.core.truthful-verdict", "cleanup.adapter-only", "learning.project-local-by-default"),
        (),
        max_selected_topics=None,
        cap_policy="documented-legacy-fallback-exception",
        flags=("fallback",),
    ),
)


UPDATER_SPECS = (
    CaseSpec(
        "updater.discovery-low",
        "secure-self-update",
        "updater-special",
        {},
        "task-aware-v2",
        None,
        (*BASE_TOPICS, "secure-self-update"),
        (*BASE_RULES, "rd.updater.source-policy", "rd.updater.safe-client", "rd.updater.user-control"),
        ("benchmark-metrics", "media-evidence", "completion-detail", "security-hardening"),
        "low",
        max_selected_topics=5,
        flags=("updater",),
    ),
    CaseSpec(
        "updater.implementation-promotion-risk-floor",
        "secure-self-update",
        "updater-special",
        {},
        "task-aware-v2",
        None,
        (*BASE_TOPICS, "secure-self-update", "promotion-evidence", "architecture-evaluation", "delivery-artifact", "security-hardening", "security-assessment"),
        (*BASE_RULES, "rd.updater.safe-client", "promotion.final-evidence-must-be-fresh", "security.fail-closed-on-identity-drift", "rd.security.scan-coverage-ledger"),
        ("benchmark-metrics", "media-evidence", "model-context", "completion-detail"),
        "high",
        ("rd.updater.safe-client",),
        8,
        "documented-updater-safety-floor",
        ("updater",),
    ),
    CaseSpec(
        "updater.completion-destructive",
        "secure-self-update",
        "updater-special",
        {},
        "task-aware-v2",
        None,
        (*BASE_TOPICS, "secure-self-update", "completion-detail", "architecture-evaluation", "completion-core", "delivery-artifact", "security-hardening", "security-assessment"),
        (*BASE_RULES, "rd.updater.safe-client", "rd.updater.retirement", "rd.updater.user-control", "rd.complete.closed-obligations", "completion.last-mutation-barrier", "rd.security.adapter-evidence-integrity"),
        ("benchmark-metrics", "media-evidence", "model-context"),
        "critical",
        ("rd.updater.safe-client",),
        9,
        "documented-updater-completion-safety-floor",
        ("updater", "destructive-boundary"),
    ),
)
