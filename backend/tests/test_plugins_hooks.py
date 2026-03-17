"""
Integration tests for plugin pipeline hooks (PluginHooks).
"""

import os
import json
import shutil
import sys
import tempfile
import textwrap
from typing import Any, Dict, Optional

import pytest

# Patch Config before importing app
_TEMP_DIR = tempfile.mkdtemp()
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

import app.config as _cfg  # noqa: E402
_cfg.Config.UPLOAD_FOLDER = _TEMP_DIR

from app.models.tenant import TenantManager  # noqa: E402
from app.plugins.hooks import PluginHooks, PluginContext  # noqa: E402
from app.plugins.registry import _tenant_plugins_dir  # noqa: E402
from app.plugins.sdk import SourcePlugin, MarketPlugin, ActionPlugin  # noqa: E402

TenantManager.TENANTS_DIR = os.path.join(_TEMP_DIR, "tenants")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_tenant(name: str = "HookTest") -> str:
    tenant, _ = TenantManager.create_tenant(
        name=name,
        owner_email=f"{name.lower()}@test.com",
        owner_password="pw",
        owner_name=name,
    )
    return tenant.tenant_id


def _install_plugin(tenant_id: str, plugin_name: str, plugin_type: str, module_src: str) -> None:
    """Install a plugin for a tenant by writing files to disk."""
    plugin_dir = os.path.join(_tenant_plugins_dir(tenant_id), plugin_name)
    os.makedirs(plugin_dir, exist_ok=True)
    manifest = textwrap.dedent(f"""
        name: {plugin_name}
        version: 1.0.0
        type: {plugin_type}
        entry_point: main:{plugin_name.replace("-", "_").title().replace("_", "")}
        description: test
        author: test
    """)
    with open(os.path.join(plugin_dir, "plugin.yaml"), "w") as f:
        f.write(manifest)
    with open(os.path.join(plugin_dir, "main.py"), "w") as f:
        f.write(textwrap.dedent(module_src))


def _enable_plugin(tenant_id: str, plugin_name: str) -> None:
    tenant = TenantManager.get_tenant(tenant_id)
    if plugin_name not in tenant.enabled_plugins:
        tenant.enabled_plugins.append(plugin_name)
        TenantManager.save_tenant(tenant)


def _flush_module_cache(tenant_id: str, plugin_name: str) -> None:
    for key in list(sys.modules.keys()):
        if tenant_id in key and plugin_name in key:
            del sys.modules[key]


@pytest.fixture(autouse=True)
def clean_state():
    yield
    if os.path.exists(TenantManager.TENANTS_DIR):
        shutil.rmtree(TenantManager.TENANTS_DIR)


# ---------------------------------------------------------------------------
# Source hook tests
# ---------------------------------------------------------------------------

class TestRunSourceHooks:
    def test_no_enabled_plugins_returns_unchanged(self):
        tenant_id = _create_tenant("NoSourcePlugins")
        ctx = PluginContext(tenant_id=tenant_id)
        docs = ["doc1", "doc2"]
        result = PluginHooks.run_source_hooks(ctx, docs)
        assert result == docs

    def test_source_plugin_injects_documents(self):
        tenant_id = _create_tenant("SourceInject")
        plugin_name = "inject-source"
        class_name = "InjectSource"
        _install_plugin(
            tenant_id, plugin_name, "source",
            f"""
            from app.plugins.sdk import SourcePlugin
            from typing import Any, Dict
            class {class_name}(SourcePlugin):
                def fetch_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
                    return {{"documents": ["injected-doc"], "metadata": {{}}}}
            """,
        )
        _enable_plugin(tenant_id, plugin_name)
        # patch entry_point in manifest
        manifest_path = os.path.join(_tenant_plugins_dir(tenant_id), plugin_name, "plugin.yaml")
        with open(manifest_path, "w") as f:
            f.write(textwrap.dedent(f"""
                name: {plugin_name}
                version: 1.0.0
                type: source
                entry_point: main:{class_name}
                description: test
                author: test
            """))
        _flush_module_cache(tenant_id, plugin_name)

        ctx = PluginContext(tenant_id=tenant_id)
        result = PluginHooks.run_source_hooks(ctx, ["original"])
        assert "original" in result
        assert "injected-doc" in result

    def test_source_plugin_failure_does_not_block_pipeline(self):
        tenant_id = _create_tenant("SourceFail")
        plugin_name = "fail-source"
        class_name = "FailSource"
        _install_plugin(
            tenant_id, plugin_name, "source",
            f"""
            from app.plugins.sdk import SourcePlugin
            from typing import Any, Dict
            class {class_name}(SourcePlugin):
                def fetch_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
                    raise RuntimeError("intentional source failure")
            """,
        )
        _enable_plugin(tenant_id, plugin_name)
        manifest_path = os.path.join(_tenant_plugins_dir(tenant_id), plugin_name, "plugin.yaml")
        with open(manifest_path, "w") as f:
            f.write(textwrap.dedent(f"""
                name: {plugin_name}
                version: 1.0.0
                type: source
                entry_point: main:{class_name}
                description: test
                author: test
            """))
        _flush_module_cache(tenant_id, plugin_name)

        ctx = PluginContext(tenant_id=tenant_id)
        docs = ["original"]
        result = PluginHooks.run_source_hooks(ctx, docs)
        # Pipeline must continue with original docs
        assert result == docs

    def test_market_plugins_are_not_run_as_source_hooks(self):
        """A market plugin should not be picked up by source hooks."""
        tenant_id = _create_tenant("MarketAsSource")
        plugin_name = "market-plugin"
        class_name = "MarketPlugin_"
        _install_plugin(
            tenant_id, plugin_name, "market",
            f"""
            from app.plugins.sdk import MarketPlugin
            from typing import Any, Dict
            class {class_name}(MarketPlugin):
                def get_template(self, config: Dict[str, Any]) -> Dict[str, Any]:
                    return {{"num_agents": 99}}
            """,
        )
        _enable_plugin(tenant_id, plugin_name)
        manifest_path = os.path.join(_tenant_plugins_dir(tenant_id), plugin_name, "plugin.yaml")
        with open(manifest_path, "w") as f:
            f.write(textwrap.dedent(f"""
                name: {plugin_name}
                version: 1.0.0
                type: market
                entry_point: main:{class_name}
                description: test
                author: test
            """))

        ctx = PluginContext(tenant_id=tenant_id)
        docs = ["original"]
        result = PluginHooks.run_source_hooks(ctx, docs)
        assert result == docs  # No injection from market plugin


# ---------------------------------------------------------------------------
# Market hook tests
# ---------------------------------------------------------------------------

class TestRunMarketHooks:
    def test_no_enabled_plugins_returns_unchanged(self):
        tenant_id = _create_tenant("NoMarketPlugins")
        ctx = PluginContext(tenant_id=tenant_id)
        params = {"num_agents": 10, "platform": "twitter"}
        result = PluginHooks.run_market_hooks(ctx, params)
        assert result == params

    def test_market_plugin_overrides_params(self):
        tenant_id = _create_tenant("MarketOverride")
        plugin_name = "override-market"
        class_name = "OverrideMarket"
        _install_plugin(
            tenant_id, plugin_name, "market",
            f"""
            from app.plugins.sdk import MarketPlugin
            from typing import Any, Dict
            class {class_name}(MarketPlugin):
                def get_template(self, config: Dict[str, Any]) -> Dict[str, Any]:
                    return {{"num_agents": 999, "extra_field": "injected"}}
            """,
        )
        _enable_plugin(tenant_id, plugin_name)
        manifest_path = os.path.join(_tenant_plugins_dir(tenant_id), plugin_name, "plugin.yaml")
        with open(manifest_path, "w") as f:
            f.write(textwrap.dedent(f"""
                name: {plugin_name}
                version: 1.0.0
                type: market
                entry_point: main:{class_name}
                description: test
                author: test
            """))
        _flush_module_cache(tenant_id, plugin_name)

        ctx = PluginContext(tenant_id=tenant_id)
        params = {"num_agents": 10}
        result = PluginHooks.run_market_hooks(ctx, params)
        assert result["num_agents"] == 999
        assert result["extra_field"] == "injected"

    def test_market_plugin_failure_returns_original_params(self):
        tenant_id = _create_tenant("MarketFail")
        plugin_name = "fail-market"
        class_name = "FailMarket"
        _install_plugin(
            tenant_id, plugin_name, "market",
            f"""
            from app.plugins.sdk import MarketPlugin
            from typing import Any, Dict
            class {class_name}(MarketPlugin):
                def get_template(self, config: Dict[str, Any]) -> Dict[str, Any]:
                    raise RuntimeError("market failure")
            """,
        )
        _enable_plugin(tenant_id, plugin_name)
        manifest_path = os.path.join(_tenant_plugins_dir(tenant_id), plugin_name, "plugin.yaml")
        with open(manifest_path, "w") as f:
            f.write(textwrap.dedent(f"""
                name: {plugin_name}
                version: 1.0.0
                type: market
                entry_point: main:{class_name}
                description: test
                author: test
            """))
        _flush_module_cache(tenant_id, plugin_name)

        ctx = PluginContext(tenant_id=tenant_id)
        params = {"num_agents": 10}
        result = PluginHooks.run_market_hooks(ctx, params)
        assert result == params


# ---------------------------------------------------------------------------
# Action hook tests
# ---------------------------------------------------------------------------

class TestRunActionHooks:
    def test_no_enabled_plugins_returns_unchanged(self):
        tenant_id = _create_tenant("NoActionPlugins")
        ctx = PluginContext(tenant_id=tenant_id)
        action = {"agent_id": "1", "action_type": "CREATE_POST", "content": "hello"}
        result = PluginHooks.run_action_hooks(ctx, "agent_1", action)
        assert result == action

    def test_action_plugin_transforms_action(self):
        tenant_id = _create_tenant("ActionTransform")
        plugin_name = "transform-action"
        class_name = "TransformAction"
        _install_plugin(
            tenant_id, plugin_name, "action",
            f"""
            from app.plugins.sdk import ActionPlugin
            from typing import Any, Dict, Optional
            class {class_name}(ActionPlugin):
                def on_round_start(self, round_num: int, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                    return None
                def on_action(self, agent_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
                    action["transformed"] = True
                    return action
            """,
        )
        _enable_plugin(tenant_id, plugin_name)
        manifest_path = os.path.join(_tenant_plugins_dir(tenant_id), plugin_name, "plugin.yaml")
        with open(manifest_path, "w") as f:
            f.write(textwrap.dedent(f"""
                name: {plugin_name}
                version: 1.0.0
                type: action
                entry_point: main:{class_name}
                description: test
                author: test
            """))
        _flush_module_cache(tenant_id, plugin_name)

        ctx = PluginContext(tenant_id=tenant_id)
        action = {"agent_id": "1", "action_type": "CREATE_POST"}
        result = PluginHooks.run_action_hooks(ctx, "agent_1", action)
        assert result["transformed"] is True

    def test_action_plugin_failure_returns_original_action(self):
        tenant_id = _create_tenant("ActionFail")
        plugin_name = "fail-action"
        class_name = "FailAction"
        _install_plugin(
            tenant_id, plugin_name, "action",
            f"""
            from app.plugins.sdk import ActionPlugin
            from typing import Any, Dict, Optional
            class {class_name}(ActionPlugin):
                def on_round_start(self, round_num: int, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                    return None
                def on_action(self, agent_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
                    raise RuntimeError("action failure")
            """,
        )
        _enable_plugin(tenant_id, plugin_name)
        manifest_path = os.path.join(_tenant_plugins_dir(tenant_id), plugin_name, "plugin.yaml")
        with open(manifest_path, "w") as f:
            f.write(textwrap.dedent(f"""
                name: {plugin_name}
                version: 1.0.0
                type: action
                entry_point: main:{class_name}
                description: test
                author: test
            """))
        _flush_module_cache(tenant_id, plugin_name)

        ctx = PluginContext(tenant_id=tenant_id)
        action = {"agent_id": "1", "action_type": "CREATE_POST"}
        result = PluginHooks.run_action_hooks(ctx, "agent_1", action)
        assert result == action

    def test_round_start_hook_collects_overrides(self):
        tenant_id = _create_tenant("RoundStart")
        plugin_name = "round-action"
        class_name = "RoundAction"
        _install_plugin(
            tenant_id, plugin_name, "action",
            f"""
            from app.plugins.sdk import ActionPlugin
            from typing import Any, Dict, Optional
            class {class_name}(ActionPlugin):
                def on_round_start(self, round_num: int, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                    return {{"round_override": round_num * 10}}
                def on_action(self, agent_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
                    return action
            """,
        )
        _enable_plugin(tenant_id, plugin_name)
        manifest_path = os.path.join(_tenant_plugins_dir(tenant_id), plugin_name, "plugin.yaml")
        with open(manifest_path, "w") as f:
            f.write(textwrap.dedent(f"""
                name: {plugin_name}
                version: 1.0.0
                type: action
                entry_point: main:{class_name}
                description: test
                author: test
            """))
        _flush_module_cache(tenant_id, plugin_name)

        ctx = PluginContext(tenant_id=tenant_id)
        overrides = PluginHooks.run_round_start_hooks(ctx, round_num=5, state={})
        assert overrides["round_override"] == 50

    def test_round_start_no_plugins_returns_empty(self):
        tenant_id = _create_tenant("RoundStartEmpty")
        ctx = PluginContext(tenant_id=tenant_id)
        overrides = PluginHooks.run_round_start_hooks(ctx, round_num=0, state={})
        assert overrides == {}
