"""
Unit tests for Plugin SDK: PluginManifest parsing and config schema validation.
"""

import os
import tempfile
import textwrap
from typing import Any, Dict, Optional

import pytest
import jsonschema

from app.plugins.sdk import (
    PluginManifest,
    SourcePlugin,
    MarketPlugin,
    ActionPlugin,
    VALID_PLUGIN_TYPES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(content: str) -> str:
    """Write content to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(textwrap.dedent(content))
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# PluginManifest.from_yaml
# ---------------------------------------------------------------------------

class TestPluginManifestFromYaml:
    def test_valid_source_manifest(self):
        path = _write_yaml("""
            name: rss-source
            version: 1.0.0
            type: source
            entry_point: main:RssSourcePlugin
            description: Fetches RSS feeds
            author: MiroFish
            config_schema:
              type: object
              properties:
                feed_url:
                  type: string
                max_items:
                  type: integer
                  default: 10
              required: [feed_url]
        """)
        try:
            m = PluginManifest.from_yaml(path)
            assert m.name == "rss-source"
            assert m.version == "1.0.0"
            assert m.plugin_type == "source"
            assert m.entry_point == "main:RssSourcePlugin"
            assert m.description == "Fetches RSS feeds"
            assert m.author == "MiroFish"
            assert m.config_schema["type"] == "object"
            assert "feed_url" in m.config_schema["properties"]
        finally:
            os.unlink(path)

    def test_valid_market_manifest(self):
        path = _write_yaml("""
            name: crypto-market
            version: 2.1.0
            type: market
            entry_point: main:CryptoMarketPlugin
            description: Crypto market simulation template
            author: MiroFish
        """)
        try:
            m = PluginManifest.from_yaml(path)
            assert m.plugin_type == "market"
            assert m.config_schema == {}
        finally:
            os.unlink(path)

    def test_valid_action_manifest(self):
        path = _write_yaml("""
            name: sentiment-action
            version: 0.5.0
            type: action
            entry_point: main:SentimentActionPlugin
            description: Injects sentiment into agent actions
            author: MiroFish
        """)
        try:
            m = PluginManifest.from_yaml(path)
            assert m.plugin_type == "action"
        finally:
            os.unlink(path)

    def test_missing_required_field_raises(self):
        path = _write_yaml("""
            name: incomplete-plugin
            version: 1.0.0
            type: source
            entry_point: main:Plugin
            description: Missing author
        """)
        try:
            with pytest.raises(ValueError, match="author"):
                PluginManifest.from_yaml(path)
        finally:
            os.unlink(path)

    def test_invalid_plugin_type_raises(self):
        path = _write_yaml("""
            name: bad-type
            version: 1.0.0
            type: transformer
            entry_point: main:Plugin
            description: Bad type
            author: MiroFish
        """)
        try:
            with pytest.raises(ValueError, match="transformer"):
                PluginManifest.from_yaml(path)
        finally:
            os.unlink(path)

    def test_version_coerced_to_string(self):
        path = _write_yaml("""
            name: numeric-version
            version: 2
            type: source
            entry_point: main:Plugin
            description: Numeric version
            author: MiroFish
        """)
        try:
            m = PluginManifest.from_yaml(path)
            assert isinstance(m.version, str)
            assert m.version == "2"
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# PluginManifest.from_dict
# ---------------------------------------------------------------------------

class TestPluginManifestFromDict:
    def test_from_dict_with_type_key(self):
        d = {
            "name": "test",
            "version": "1.0",
            "type": "action",
            "entry_point": "main:P",
            "description": "desc",
            "author": "x",
        }
        m = PluginManifest.from_dict(d)
        assert m.plugin_type == "action"

    def test_from_dict_with_plugin_type_key(self):
        d = {
            "name": "test",
            "version": "1.0",
            "plugin_type": "market",
            "entry_point": "main:P",
        }
        m = PluginManifest.from_dict(d)
        assert m.plugin_type == "market"

    def test_from_dict_invalid_type_raises(self):
        d = {
            "name": "test",
            "version": "1.0",
            "type": "invalid",
            "entry_point": "main:P",
        }
        with pytest.raises(ValueError):
            PluginManifest.from_dict(d)


# ---------------------------------------------------------------------------
# PluginManifest.to_dict round-trip
# ---------------------------------------------------------------------------

class TestPluginManifestRoundTrip:
    def test_to_dict_round_trip(self):
        original = {
            "name": "round-trip",
            "version": "3.0.0",
            "type": "source",
            "entry_point": "main:P",
            "description": "desc",
            "author": "me",
            "config_schema": {"type": "object", "properties": {}},
        }
        m = PluginManifest.from_dict(original)
        result = m.to_dict()
        assert result["name"] == "round-trip"
        assert result["type"] == "source"
        assert result["config_schema"] == {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# PluginManifest.validate_config
# ---------------------------------------------------------------------------

class TestPluginManifestValidateConfig:
    def _manifest_with_schema(self) -> PluginManifest:
        return PluginManifest(
            name="test",
            version="1.0.0",
            plugin_type="source",
            entry_point="main:P",
            description="desc",
            author="MiroFish",
            config_schema={
                "type": "object",
                "properties": {
                    "feed_url": {"type": "string"},
                    "max_items": {"type": "integer", "default": 10},
                },
                "required": ["feed_url"],
            },
        )

    def test_valid_config_passes(self):
        m = self._manifest_with_schema()
        m.validate_config({"feed_url": "https://example.com/rss"})

    def test_valid_config_with_optional_field_passes(self):
        m = self._manifest_with_schema()
        m.validate_config({"feed_url": "https://example.com/rss", "max_items": 5})

    def test_missing_required_field_raises(self):
        m = self._manifest_with_schema()
        with pytest.raises(jsonschema.ValidationError):
            m.validate_config({})

    def test_wrong_type_raises(self):
        m = self._manifest_with_schema()
        with pytest.raises(jsonschema.ValidationError):
            m.validate_config({"feed_url": "https://example.com/rss", "max_items": "five"})

    def test_empty_schema_skips_validation(self):
        m = PluginManifest(
            name="no-schema",
            version="1.0.0",
            plugin_type="action",
            entry_point="main:P",
            description="desc",
            author="me",
            config_schema={},
        )
        # Should not raise
        m.validate_config({"anything": "goes"})


# ---------------------------------------------------------------------------
# VALID_PLUGIN_TYPES
# ---------------------------------------------------------------------------

class TestValidPluginTypes:
    def test_contains_all_three_types(self):
        assert VALID_PLUGIN_TYPES == {"source", "market", "action"}


# ---------------------------------------------------------------------------
# Abstract base classes enforce contracts
# ---------------------------------------------------------------------------

class TestAbstractBaseClasses:
    def test_source_plugin_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            SourcePlugin()  # type: ignore

    def test_market_plugin_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            MarketPlugin()  # type: ignore

    def test_action_plugin_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            ActionPlugin()  # type: ignore

    def test_source_plugin_concrete_impl(self):
        class ConcreteSource(SourcePlugin):
            def fetch_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
                return {"documents": [], "metadata": {}}

        plugin = ConcreteSource()
        result = plugin.fetch_data({})
        assert "documents" in result
        assert "metadata" in result

    def test_market_plugin_concrete_impl(self):
        class ConcreteMarket(MarketPlugin):
            def get_template(self, config: Dict[str, Any]) -> Dict[str, Any]:
                return {"num_agents": 10}

        plugin = ConcreteMarket()
        result = plugin.get_template({})
        assert result["num_agents"] == 10

    def test_action_plugin_concrete_impl(self):
        class ConcreteAction(ActionPlugin):
            def on_round_start(self, round_num: int, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                return None

            def on_action(self, agent_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
                return action

        plugin = ConcreteAction()
        assert plugin.on_round_start(0, {}) is None
        action = {"type": "post", "content": "hello"}
        assert plugin.on_action("agent_1", action) is action
