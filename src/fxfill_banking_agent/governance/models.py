"""Governance models — asset versioning, release manifests (P2-08)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AssetType(str, Enum):
    """Types of governed assets."""

    MODEL = "model"
    PROMPT = "prompt"
    TOOL = "tool"
    POLICY = "policy"
    KNOWLEDGE_INDEX = "knowledge_index"
    WORKFLOW = "workflow"
    EVALUATION_DATASET = "evaluation_dataset"


@dataclass(frozen=True)
class AssetVersion:
    """A specific version of a governed asset.

    Attributes:
        asset_type: What kind of asset.
        asset_id: Unique asset identifier.
        version: Version string (semver).
        hash: Content hash for integrity verification.
        owner: Responsible team/person.
        approved_by: Who approved this version.
        approved_at: When it was approved.
        change_description: Why this version exists.
        metadata: Arbitrary additional data.
    """

    asset_type: AssetType
    asset_id: str
    version: str = "1.0.0"
    hash: str = ""
    owner: str = ""
    approved_by: str = ""
    approved_at: str = ""
    change_description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentReleaseManifest:
    """Immutable snapshot of all asset versions for one agent release.

    This manifest enables exact reproduction of any agent run.
    """

    release_id: str
    model: AssetVersion | None = None
    prompt: AssetVersion | None = None
    tool_registry_version: str = ""
    policy_version: str = ""
    knowledge_index_version: str = ""
    workflow_version: str = ""
    evaluation_dataset_version: str = ""
    released_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_by: str = ""
    rollback_target: str | None = None  # Release ID to roll back to

    @property
    def fingerprint(self) -> str:
        """Unique fingerprint of this release."""
        parts = [
            self.model.hash if self.model else "",
            self.prompt.hash if self.prompt else "",
            self.tool_registry_version,
            self.policy_version,
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


class GovernanceRegistry:
    """Registry of all governed asset versions.

    Every agent run records which versions were active.
    """

    def __init__(self) -> None:
        self._assets: dict[tuple[AssetType, str, str], AssetVersion] = {}

    def register(self, asset: AssetVersion) -> None:
        """Register an asset version."""
        key = (asset.asset_type, asset.asset_id, asset.version)
        self._assets[key] = asset

    def get(
        self, asset_type: AssetType, asset_id: str, version: str | None = None
    ) -> AssetVersion | None:
        """Get an asset version. Latest if version is None."""
        if version:
            return self._assets.get((asset_type, asset_id, version))

        # Find latest
        candidates = [
            (k, v) for k, v in self._assets.items() if k[0] == asset_type and k[1] == asset_id
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0][2], reverse=True)
        return candidates[0][1]

    def list_by_type(self, asset_type: AssetType) -> list[AssetVersion]:
        """List all versions of a given asset type."""
        return [v for (at, _, _), v in self._assets.items() if at == asset_type]

    @property
    def count(self) -> int:
        return len(self._assets)


def build_release_manifest(
    release_id: str,
    governance: GovernanceRegistry,
    model_id: str = "",
    prompt_id: str = "",
) -> AgentReleaseManifest:
    """Build a release manifest from the current governance registry state."""
    model = governance.get(AssetType.MODEL, model_id) if model_id else None
    prompt = governance.get(AssetType.PROMPT, prompt_id) if prompt_id else None
    return AgentReleaseManifest(
        release_id=release_id,
        model=model,
        prompt=prompt,
    )
