"""Agent governance — model, prompt, tool, knowledge, and policy registries (P2-08).

Every agent run records the exact versions of all assets used.
Governance enables:
- Reproducibility: Re-run with the exact same versions
- Audit: Know which model/prompt/tool version produced each answer
- Rollback: Revert to a known-good version bundle
- Approval: Changes to high-risk assets require review
"""

from fxfill_banking_agent.governance.models import (
    AgentReleaseManifest,
    AssetType,
    AssetVersion,
    GovernanceRegistry,
    build_release_manifest,
)

__all__ = [
    "AssetType",
    "AssetVersion",
    "AgentReleaseManifest",
    "GovernanceRegistry",
    "build_release_manifest",
]
