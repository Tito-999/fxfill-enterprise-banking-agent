"""Unit tests for governance models and registry."""

from __future__ import annotations

from fxfill_banking_agent.governance.models import (
    AgentReleaseManifest,
    AssetType,
    AssetVersion,
    GovernanceRegistry,
)


class TestAssetVersion:
    def test_model_asset(self) -> None:
        av = AssetVersion(
            asset_type=AssetType.MODEL,
            asset_id="deepseek-v4",
            version="1.0.0",
            hash="abc123",
            owner="ai-team",
        )
        assert av.asset_type == AssetType.MODEL
        assert av.hash == "abc123"

    def test_prompt_asset(self) -> None:
        av = AssetVersion(
            asset_type=AssetType.PROMPT,
            asset_id="banking_agent_system",
            version="1.0.0",
            approved_by="security-team",
        )
        assert av.asset_type == AssetType.PROMPT
        assert av.approved_by == "security-team"


class TestGovernanceRegistry:
    def test_register_and_get(self) -> None:
        reg = GovernanceRegistry()
        av = AssetVersion(asset_type=AssetType.MODEL, asset_id="gpt-4", version="1.0")
        reg.register(av)
        found = reg.get(AssetType.MODEL, "gpt-4", "1.0")
        assert found is not None
        assert found.version == "1.0"

    def test_get_nonexistent(self) -> None:
        reg = GovernanceRegistry()
        assert reg.get(AssetType.MODEL, "nonexistent") is None

    def test_list_by_type(self) -> None:
        reg = GovernanceRegistry()
        reg.register(AssetVersion(asset_type=AssetType.PROMPT, asset_id="p1", version="1.0"))
        reg.register(AssetVersion(asset_type=AssetType.PROMPT, asset_id="p2", version="1.0"))
        reg.register(AssetVersion(asset_type=AssetType.MODEL, asset_id="m1", version="1.0"))
        prompts = reg.list_by_type(AssetType.PROMPT)
        assert len(prompts) == 2

    def test_count(self) -> None:
        reg = GovernanceRegistry()
        assert reg.count == 0
        reg.register(AssetVersion(asset_type=AssetType.MODEL, asset_id="m1", version="1.0"))
        assert reg.count == 1


class TestAgentReleaseManifest:
    def test_fingerprint(self) -> None:
        model = AssetVersion(
            asset_type=AssetType.MODEL, asset_id="deepseek", version="1.0", hash="abc"
        )
        prompt = AssetVersion(
            asset_type=AssetType.PROMPT, asset_id="system", version="1.0", hash="def"
        )
        manifest = AgentReleaseManifest(release_id="rel-1", model=model, prompt=prompt)
        fingerprint = manifest.fingerprint
        assert len(fingerprint) == 16  # hex digest

    def test_rollback_target(self) -> None:
        manifest = AgentReleaseManifest(release_id="rel-2", rollback_target="rel-1")
        assert manifest.rollback_target == "rel-1"
