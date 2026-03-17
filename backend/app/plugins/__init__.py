"""
MiroFish Plugin System
"""

from .sdk import (
    PluginManifest,
    SourcePlugin,
    MarketPlugin,
    ActionPlugin,
    VALID_PLUGIN_TYPES,
    validate_plugin_name,
)
from .registry import PluginRegistry
from .executor import PluginExecutor, PluginResult
from .hooks import PluginHooks, PluginContext

__all__ = [
    "PluginManifest",
    "SourcePlugin",
    "MarketPlugin",
    "ActionPlugin",
    "VALID_PLUGIN_TYPES",
    "validate_plugin_name",
    "PluginRegistry",
    "PluginExecutor",
    "PluginResult",
    "PluginHooks",
    "PluginContext",
]
