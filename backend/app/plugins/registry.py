"""
Plugin registry: discover, load, and validate plugins from the tenant filesystem.
"""

import importlib.util
import os
import sys
from typing import List, Union

from ..config import Config
from .sdk import ActionPlugin, MarketPlugin, PluginManifest, SourcePlugin

BasePlugin = Union[SourcePlugin, MarketPlugin, ActionPlugin]

_PLUGIN_TYPE_TO_BASE = {
    "source": SourcePlugin,
    "market": MarketPlugin,
    "action": ActionPlugin,
}


def _tenant_plugins_dir(tenant_id: str) -> str:
    return os.path.join(Config.UPLOAD_FOLDER, "tenants", tenant_id, "plugins")


class PluginRegistry:
    """Discovers, validates, and loads plugins for a tenant."""

    @staticmethod
    def discover_plugins(tenant_id: str) -> List[PluginManifest]:
        """Scan the tenant plugin directory and return manifests for all valid plugins.

        Invalid or unreadable plugin directories are silently skipped.
        """
        plugins_dir = _tenant_plugins_dir(tenant_id)
        if not os.path.isdir(plugins_dir):
            return []

        manifests: List[PluginManifest] = []
        for entry in os.listdir(plugins_dir):
            plugin_dir = os.path.join(plugins_dir, entry)
            if not os.path.isdir(plugin_dir):
                continue
            manifest_path = os.path.join(plugin_dir, "plugin.yaml")
            if not os.path.isfile(manifest_path):
                continue
            try:
                manifest = PluginManifest.from_yaml(manifest_path)
                manifests.append(manifest)
            except Exception:
                # Skip plugins with invalid manifests
                pass

        return manifests

    @staticmethod
    def validate_manifest(manifest_path: str) -> PluginManifest:
        """Parse and validate a plugin.yaml file.

        Raises ValueError or yaml.YAMLError on failure.
        """
        return PluginManifest.from_yaml(manifest_path)

    @staticmethod
    def load_plugin(tenant_id: str, plugin_name: str) -> BasePlugin:
        """Import and instantiate the plugin class for the given tenant and plugin name.

        Args:
            tenant_id: The tenant owning this plugin.
            plugin_name: The plugin directory name (must match manifest name).

        Returns:
            An instantiated plugin object (subclass of SourcePlugin, MarketPlugin, or ActionPlugin).

        Raises:
            FileNotFoundError: plugin directory or plugin.yaml not found.
            ValueError: manifest is invalid or entry_point cannot be resolved.
            ImportError: the plugin module cannot be imported.
            TypeError: entry_point class does not subclass the expected base.
        """
        plugins_dir = _tenant_plugins_dir(tenant_id)
        plugin_dir = os.path.join(plugins_dir, plugin_name)

        if not os.path.isdir(plugin_dir):
            raise FileNotFoundError(f"Plugin directory not found: {plugin_dir}")

        manifest_path = os.path.join(plugin_dir, "plugin.yaml")
        if not os.path.isfile(manifest_path):
            raise FileNotFoundError(f"plugin.yaml not found in: {plugin_dir}")

        manifest = PluginManifest.from_yaml(manifest_path)

        # Parse entry_point: "module:ClassName"
        if ":" not in manifest.entry_point:
            raise ValueError(
                f"entry_point must be in 'module:ClassName' format, got: {manifest.entry_point!r}"
            )
        module_name, class_name = manifest.entry_point.split(":", 1)

        module_file = os.path.join(plugin_dir, f"{module_name}.py")
        if not os.path.isfile(module_file):
            raise FileNotFoundError(f"Plugin module file not found: {module_file}")

        # Use a unique module key to avoid collisions between tenants
        unique_module_key = f"_mirofish_plugin_{tenant_id}_{plugin_name}_{module_name}"
        if unique_module_key in sys.modules:
            mod = sys.modules[unique_module_key]
        else:
            spec = importlib.util.spec_from_file_location(unique_module_key, module_file)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create module spec from: {module_file}")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[unique_module_key] = mod
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

        if not hasattr(mod, class_name):
            raise ValueError(f"Class {class_name!r} not found in module {module_file}")

        cls = getattr(mod, class_name)
        expected_base = _PLUGIN_TYPE_TO_BASE[manifest.plugin_type]
        if not (isinstance(cls, type) and issubclass(cls, expected_base)):
            raise TypeError(
                f"{class_name} must be a subclass of {expected_base.__name__} "
                f"for plugin type {manifest.plugin_type!r}"
            )

        return cls()
