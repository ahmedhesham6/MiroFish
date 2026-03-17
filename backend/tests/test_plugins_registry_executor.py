"""
Unit tests for PluginRegistry and PluginExecutor.
"""

import os
import sys
import tempfile
import textwrap
import time
from typing import Any, Dict, Optional

import pytest

import app.config as _cfg

# Use a temp dir so we don't touch real uploads
_TEMP_DIR = tempfile.mkdtemp()
_cfg.Config.UPLOAD_FOLDER = _TEMP_DIR

from app.plugins.registry import PluginRegistry, _tenant_plugins_dir  # noqa: E402
from app.plugins.executor import PluginExecutor, PluginResult  # noqa: E402
from app.plugins.sdk import SourcePlugin, MarketPlugin, ActionPlugin  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plugin_dir(tenant_id: str, plugin_name: str, manifest: str, module_src: str) -> str:
    """Create a plugin directory with plugin.yaml and a module file."""
    plugin_dir = os.path.join(_tenant_plugins_dir(tenant_id), plugin_name)
    os.makedirs(plugin_dir, exist_ok=True)
    with open(os.path.join(plugin_dir, "plugin.yaml"), "w") as f:
        f.write(textwrap.dedent(manifest))
    # Derive module filename from entry_point in manifest
    for line in manifest.splitlines():
        line = line.strip()
        if line.startswith("entry_point:"):
            ep = line.split(":", 1)[1].strip()
            module_name = ep.split(":")[0]
            break
    else:
        module_name = "main"
    with open(os.path.join(plugin_dir, f"{module_name}.py"), "w") as f:
        f.write(textwrap.dedent(module_src))
    return plugin_dir


# ---------------------------------------------------------------------------
# PluginRegistry.discover_plugins
# ---------------------------------------------------------------------------

class TestPluginRegistryDiscover:
    def test_discover_returns_empty_for_missing_dir(self):
        manifests = PluginRegistry.discover_plugins("nonexistent_tenant")
        assert manifests == []

    def test_discover_finds_valid_plugins(self):
        tenant_id = "tn_discover_test"
        _make_plugin_dir(
            tenant_id, "rss-plugin",
            """
            name: rss-plugin
            version: 1.0.0
            type: source
            entry_point: main:RssPlugin
            description: RSS source
            author: MiroFish
            """,
            """
            from app.plugins.sdk import SourcePlugin
            from typing import Any, Dict
            class RssPlugin(SourcePlugin):
                def fetch_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
                    return {"documents": [], "metadata": {}}
            """,
        )
        manifests = PluginRegistry.discover_plugins(tenant_id)
        names = [m.name for m in manifests]
        assert "rss-plugin" in names

    def test_discover_skips_invalid_manifests(self):
        tenant_id = "tn_skip_invalid"
        plugins_dir = _tenant_plugins_dir(tenant_id)
        bad_dir = os.path.join(plugins_dir, "bad-plugin")
        os.makedirs(bad_dir, exist_ok=True)
        with open(os.path.join(bad_dir, "plugin.yaml"), "w") as f:
            f.write("name: bad\n")  # missing required fields
        manifests = PluginRegistry.discover_plugins(tenant_id)
        assert all(m.name != "bad" for m in manifests)

    def test_discover_skips_dirs_without_manifest(self):
        tenant_id = "tn_no_manifest"
        plugins_dir = _tenant_plugins_dir(tenant_id)
        no_manifest_dir = os.path.join(plugins_dir, "no-yaml")
        os.makedirs(no_manifest_dir, exist_ok=True)
        manifests = PluginRegistry.discover_plugins(tenant_id)
        assert manifests == []


# ---------------------------------------------------------------------------
# PluginRegistry.validate_manifest
# ---------------------------------------------------------------------------

class TestPluginRegistryValidateManifest:
    def test_validate_valid_manifest(self, tmp_path):
        p = tmp_path / "plugin.yaml"
        p.write_text(textwrap.dedent("""
            name: test
            version: 1.0.0
            type: market
            entry_point: main:P
            description: d
            author: a
        """))
        manifest = PluginRegistry.validate_manifest(str(p))
        assert manifest.plugin_type == "market"

    def test_validate_invalid_manifest_raises(self, tmp_path):
        p = tmp_path / "plugin.yaml"
        p.write_text("name: only-name\n")
        with pytest.raises(ValueError):
            PluginRegistry.validate_manifest(str(p))


# ---------------------------------------------------------------------------
# PluginRegistry.load_plugin
# ---------------------------------------------------------------------------

class TestPluginRegistryLoad:
    def test_load_source_plugin(self):
        tenant_id = "tn_load_source"
        _make_plugin_dir(
            tenant_id, "my-source",
            """
            name: my-source
            version: 1.0.0
            type: source
            entry_point: main:MySource
            description: test source
            author: MiroFish
            """,
            """
            from app.plugins.sdk import SourcePlugin
            from typing import Any, Dict
            class MySource(SourcePlugin):
                def fetch_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
                    return {"documents": ["doc1"], "metadata": {"count": 1}}
            """,
        )
        # Remove cached module if any
        for key in list(sys.modules.keys()):
            if "tn_load_source" in key:
                del sys.modules[key]

        plugin = PluginRegistry.load_plugin(tenant_id, "my-source")
        assert isinstance(plugin, SourcePlugin)
        result = plugin.fetch_data({})
        assert result["documents"] == ["doc1"]

    def test_load_market_plugin(self):
        tenant_id = "tn_load_market"
        _make_plugin_dir(
            tenant_id, "my-market",
            """
            name: my-market
            version: 1.0.0
            type: market
            entry_point: main:MyMarket
            description: test market
            author: MiroFish
            """,
            """
            from app.plugins.sdk import MarketPlugin
            from typing import Any, Dict
            class MyMarket(MarketPlugin):
                def get_template(self, config: Dict[str, Any]) -> Dict[str, Any]:
                    return {"num_agents": 5}
            """,
        )
        for key in list(sys.modules.keys()):
            if "tn_load_market" in key:
                del sys.modules[key]

        plugin = PluginRegistry.load_plugin(tenant_id, "my-market")
        assert isinstance(plugin, MarketPlugin)

    def test_load_action_plugin(self):
        tenant_id = "tn_load_action"
        _make_plugin_dir(
            tenant_id, "my-action",
            """
            name: my-action
            version: 1.0.0
            type: action
            entry_point: main:MyAction
            description: test action
            author: MiroFish
            """,
            """
            from app.plugins.sdk import ActionPlugin
            from typing import Any, Dict, Optional
            class MyAction(ActionPlugin):
                def on_round_start(self, round_num: int, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                    return None
                def on_action(self, agent_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
                    return action
            """,
        )
        for key in list(sys.modules.keys()):
            if "tn_load_action" in key:
                del sys.modules[key]

        plugin = PluginRegistry.load_plugin(tenant_id, "my-action")
        assert isinstance(plugin, ActionPlugin)

    def test_load_missing_plugin_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            PluginRegistry.load_plugin("nonexistent", "nonexistent-plugin")

    def test_load_wrong_base_class_raises(self):
        tenant_id = "tn_wrong_base"
        _make_plugin_dir(
            tenant_id, "bad-base",
            """
            name: bad-base
            version: 1.0.0
            type: source
            entry_point: main:NotAPlugin
            description: wrong base
            author: MiroFish
            """,
            """
            class NotAPlugin:
                def fetch_data(self, config):
                    return {}
            """,
        )
        for key in list(sys.modules.keys()):
            if "tn_wrong_base" in key:
                del sys.modules[key]

        with pytest.raises(TypeError):
            PluginRegistry.load_plugin(tenant_id, "bad-base")

    def test_load_missing_class_raises(self):
        tenant_id = "tn_missing_class"
        _make_plugin_dir(
            tenant_id, "missing-class",
            """
            name: missing-class
            version: 1.0.0
            type: source
            entry_point: main:DoesNotExist
            description: missing class
            author: MiroFish
            """,
            """
            from app.plugins.sdk import SourcePlugin
            from typing import Any, Dict
            class SomeOtherClass(SourcePlugin):
                def fetch_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
                    return {"documents": [], "metadata": {}}
            """,
        )
        for key in list(sys.modules.keys()):
            if "tn_missing_class" in key:
                del sys.modules[key]

        with pytest.raises(ValueError, match="DoesNotExist"):
            PluginRegistry.load_plugin(tenant_id, "missing-class")

    def test_load_invalid_entry_point_format_raises(self):
        tenant_id = "tn_bad_ep"
        _make_plugin_dir(
            tenant_id, "bad-ep",
            """
            name: bad-ep
            version: 1.0.0
            type: source
            entry_point: mainMyPlugin
            description: bad entry_point
            author: MiroFish
            """,
            """
            pass
            """,
        )
        with pytest.raises(ValueError, match="entry_point"):
            PluginRegistry.load_plugin(tenant_id, "bad-ep")


# ---------------------------------------------------------------------------
# PluginExecutor
# ---------------------------------------------------------------------------

class _FastSource(SourcePlugin):
    def fetch_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return {"documents": ["hello"], "metadata": {}}


class _ErrorSource(SourcePlugin):
    def fetch_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
        raise RuntimeError("intentional error")


class _SlowSource(SourcePlugin):
    def fetch_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
        time.sleep(10)
        return {"documents": [], "metadata": {}}


class TestPluginExecutor:
    def test_successful_execution(self):
        executor = PluginExecutor()
        plugin = _FastSource()
        result = executor.execute(plugin, "fetch_data", timeout_sec=5, config={})
        assert result.success is True
        assert result.data == {"documents": ["hello"], "metadata": {}}
        assert result.error is None
        assert result.elapsed_ms >= 0

    def test_error_captured_not_raised(self):
        executor = PluginExecutor()
        plugin = _ErrorSource()
        result = executor.execute(plugin, "fetch_data", timeout_sec=5, config={})
        assert result.success is False
        assert result.data is None
        assert "intentional error" in result.error
        assert "RuntimeError" in result.error

    def test_timeout_returns_failure(self):
        executor = PluginExecutor()
        plugin = _SlowSource()
        result = executor.execute(plugin, "fetch_data", timeout_sec=0.1, config={})
        assert result.success is False
        assert result.error is not None
        assert "timed out" in result.error

    def test_missing_method_returns_failure(self):
        executor = PluginExecutor()
        plugin = _FastSource()
        result = executor.execute(plugin, "nonexistent_method", timeout_sec=5)
        assert result.success is False
        assert "nonexistent_method" in result.error

    def test_elapsed_ms_is_positive(self):
        executor = PluginExecutor()
        plugin = _FastSource()
        result = executor.execute(plugin, "fetch_data", timeout_sec=5, config={})
        assert result.elapsed_ms >= 0
