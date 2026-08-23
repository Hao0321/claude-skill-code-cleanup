#!/usr/bin/env python3
"""Reusable valid fixture for the external-change gate and its CLI template."""

from __future__ import annotations

from typing import Any


def valid_plan_template() -> dict[str, Any]:
    return {
        "operation_id": "ext-001",
        "system": "github",
        "action": "update",
        "destructive": False,
        "user_context": {"availability": "desktop"},
        "namespace_inventory": {
            "performed": True,
            "method": "authoritative API list/search",
            "resources": [
                {"id": "owner/canonical-repo", "possible_canonical": True}
            ],
            "similar_resources_reviewed": ["owner/canonical-repo"],
        },
        "target_resolution": {
            "canonical_survivor": "owner/canonical-repo",
            "mutation_target": "owner/canonical-repo",
            "ambiguous": False,
            "evidence": "remote, history, releases, and user intent agree",
        },
        "user_authorization": {
            "granted": True,
            "action": "update",
            "target": "owner/canonical-repo",
        },
        "technical_authorization": {
            "verified": True,
            "required_capabilities": ["repo_write"],
            "available_capabilities": ["repo_write"],
            "interaction_flow": "none",
            "flow_process_alive": False,
        },
        "recovery": {
            "plan": "reviewable branch and revertable commit",
            "irreversible_acknowledged": False,
        },
        "preconditions": {
            "privacy_audit": True,
            "canonical_changes_recovered": True,
        },
        "postconditions": [
            {
                "name": "canonical_updated",
                "method": "authoritative API query",
                "authoritative": True,
            },
            {
                "name": "unrelated_resources_unchanged",
                "method": "namespace inventory diff",
                "authoritative": True,
            },
        ],
    }
