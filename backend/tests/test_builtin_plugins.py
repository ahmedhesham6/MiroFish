"""
Unit tests for built-in example plugins:
  - rss-source  (SourcePlugin)
  - volatility-market  (MarketPlugin)

These tests cover:
  - Manifest validation
  - Plugin loading via PluginRegistry
  - Core behaviour of each plugin
  - Edge cases (missing/invalid config, feedparser errors)
"""

import os
import sys
import tempfile
import shutil
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import pytest

import app.config as _cfg

_TEMP_DIR = tempfile.mkdtemp()
_cfg.Config.UPLOAD_FOLDER = _TEMP_DIR

from app.plugins.registry import PluginRegistry, _tenant_plugins_dir  # noqa: E402
from app.plugins.sdk import SourcePlugin, MarketPlugin  # noqa: E402

# ---------------------------------------------------------------------------
# Paths to the built-in plugin directories (relative to this repo)
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BUILTIN_DIR = os.path.join(_REPO_ROOT, "app", "plugins", "builtin")
_RSS_DIR = os.path.join(_BUILTIN_DIR, "rss-source")
_VOL_DIR = os.path.join(_BUILTIN_DIR, "volatility-market")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _install_builtin(tenant_id: str, plugin_dir: str, plugin_name: str) -> None:
    """Copy a built-in plugin into the tenant plugin directory."""
    dest = os.path.join(_tenant_plugins_dir(tenant_id), plugin_name)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(plugin_dir, dest)


def _clear_module_cache(tenant_id: str) -> None:
    for key in list(sys.modules.keys()):
        if tenant_id in key:
            del sys.modules[key]


# ===========================================================================
# RSS Source Plugin
# ===========================================================================

class TestRssSourceManifest:
    def test_manifest_is_valid(self):
        manifest = PluginRegistry.validate_manifest(os.path.join(_RSS_DIR, "plugin.yaml"))
        assert manifest.name == "rss-source"
        assert manifest.plugin_type == "source"
        assert manifest.entry_point == "main:RssSourcePlugin"
        assert manifest.version == "1.0.0"

    def test_manifest_requires_feed_url(self):
        manifest = PluginRegistry.validate_manifest(os.path.join(_RSS_DIR, "plugin.yaml"))
        assert "feed_url" in manifest.config_schema.get("required", [])

    def test_manifest_config_validates_good_config(self):
        manifest = PluginRegistry.validate_manifest(os.path.join(_RSS_DIR, "plugin.yaml"))
        # Should not raise
        manifest.validate_config({"feed_url": "https://example.com/feed.rss"})

    def test_manifest_config_rejects_missing_feed_url(self):
        import jsonschema
        manifest = PluginRegistry.validate_manifest(os.path.join(_RSS_DIR, "plugin.yaml"))
        with pytest.raises(jsonschema.ValidationError):
            manifest.validate_config({})


class TestRssSourceLoading:
    TENANT = "tn_rss_load"

    def setup_method(self):
        _install_builtin(self.TENANT, _RSS_DIR, "rss-source")
        _clear_module_cache(self.TENANT)

    def test_loads_as_source_plugin(self):
        plugin = PluginRegistry.load_plugin(self.TENANT, "rss-source")
        assert isinstance(plugin, SourcePlugin)

    def test_fetch_data_method_exists(self):
        plugin = PluginRegistry.load_plugin(self.TENANT, "rss-source")
        assert callable(getattr(plugin, "fetch_data", None))


class TestRssSourceFetchData:
    TENANT = "tn_rss_fetch"

    def setup_method(self):
        _install_builtin(self.TENANT, _RSS_DIR, "rss-source")
        _clear_module_cache(self.TENANT)

    def _make_feed(self, entries):
        """Build a minimal feedparser-style result object."""
        feed_obj = MagicMock()
        feed_obj.feed.get.side_effect = lambda key, default="": {
            "title": "Test Feed"
        }.get(key, default)
        feed_obj.entries = entries
        return feed_obj

    def _make_entry(self, title="Title", summary="Summary text", content=None, link="https://example.com"):
        entry = MagicMock()
        entry.get.side_effect = lambda key, default="": {
            "title": title,
            "summary": summary,
            "link": link,
        }.get(key, default)
        entry.__getitem__ = lambda self, key: {
            "title": title,
            "summary": summary,
            "link": link,
        }[key]
        if content is not None:
            entry.get.side_effect = lambda key, default="": {
                "title": title,
                "summary": summary,
                "link": link,
                "content": content,
            }.get(key, default)
        else:
            # content not in entry
            original = entry.get.side_effect
            def side_effect(key, default=""):
                if key == "content":
                    return []
                return {"title": title, "summary": summary, "link": link}.get(key, default)
            entry.get.side_effect = side_effect
        return entry

    def test_returns_documents_and_metadata(self):
        plugin = PluginRegistry.load_plugin(self.TENANT, "rss-source")
        entry = self._make_entry(title="Article 1", summary="Some news content")
        mock_feed = self._make_feed([entry])
        with patch("feedparser.parse", return_value=mock_feed):
            result = plugin.fetch_data({"feed_url": "https://example.com/feed.rss"})
        assert "documents" in result
        assert "metadata" in result

    def test_document_structure(self):
        plugin = PluginRegistry.load_plugin(self.TENANT, "rss-source")
        entry = self._make_entry(title="Headline", summary="Body of article")
        mock_feed = self._make_feed([entry])
        with patch("feedparser.parse", return_value=mock_feed):
            result = plugin.fetch_data({"feed_url": "https://example.com/feed.rss"})
        docs = result["documents"]
        assert len(docs) == 1
        doc = docs[0]
        assert "title" in doc
        assert "text" in doc
        assert "link" in doc
        assert "Headline" in doc["text"]

    def test_max_items_limits_results(self):
        plugin = PluginRegistry.load_plugin(self.TENANT, "rss-source")
        entries = [self._make_entry(title=f"Article {i}") for i in range(15)]
        mock_feed = self._make_feed(entries)
        with patch("feedparser.parse", return_value=mock_feed):
            result = plugin.fetch_data({"feed_url": "https://example.com/feed.rss", "max_items": 5})
        assert len(result["documents"]) <= 5

    def test_default_max_items_is_ten(self):
        plugin = PluginRegistry.load_plugin(self.TENANT, "rss-source")
        entries = [self._make_entry(title=f"Article {i}") for i in range(20)]
        mock_feed = self._make_feed(entries)
        with patch("feedparser.parse", return_value=mock_feed):
            result = plugin.fetch_data({"feed_url": "https://example.com/feed.rss"})
        assert len(result["documents"]) <= 10

    def test_metadata_contains_feed_url(self):
        plugin = PluginRegistry.load_plugin(self.TENANT, "rss-source")
        mock_feed = self._make_feed([])
        with patch("feedparser.parse", return_value=mock_feed):
            result = plugin.fetch_data({"feed_url": "https://example.com/feed.rss"})
        assert result["metadata"]["feed_url"] == "https://example.com/feed.rss"

    def test_html_stripped_from_body(self):
        plugin = PluginRegistry.load_plugin(self.TENANT, "rss-source")
        entry = self._make_entry(title="Title", summary="<p>Hello <b>world</b></p>")
        mock_feed = self._make_feed([entry])
        with patch("feedparser.parse", return_value=mock_feed):
            result = plugin.fetch_data({"feed_url": "https://example.com/feed.rss"})
        doc_text = result["documents"][0]["text"]
        assert "<p>" not in doc_text
        assert "<b>" not in doc_text
        assert "Hello" in doc_text

    def test_empty_feed_returns_empty_documents(self):
        plugin = PluginRegistry.load_plugin(self.TENANT, "rss-source")
        mock_feed = self._make_feed([])
        with patch("feedparser.parse", return_value=mock_feed):
            result = plugin.fetch_data({"feed_url": "https://example.com/empty.rss"})
        assert result["documents"] == []
        assert result["metadata"]["entry_count"] == 0


# ===========================================================================
# Volatility Market Plugin
# ===========================================================================

class TestVolatilityMarketManifest:
    def test_manifest_is_valid(self):
        manifest = PluginRegistry.validate_manifest(os.path.join(_VOL_DIR, "plugin.yaml"))
        assert manifest.name == "volatility-market"
        assert manifest.plugin_type == "market"
        assert manifest.entry_point == "main:VolatilityMarketPlugin"
        assert manifest.version == "1.0.0"

    def test_manifest_config_validates_empty_config(self):
        manifest = PluginRegistry.validate_manifest(os.path.join(_VOL_DIR, "plugin.yaml"))
        # All fields optional — should not raise
        manifest.validate_config({})

    def test_manifest_config_validates_full_config(self):
        manifest = PluginRegistry.validate_manifest(os.path.join(_VOL_DIR, "plugin.yaml"))
        manifest.validate_config({"volatility_level": "high", "enable_breaking_news": True})

    def test_manifest_rejects_invalid_volatility_level(self):
        import jsonschema
        manifest = PluginRegistry.validate_manifest(os.path.join(_VOL_DIR, "plugin.yaml"))
        with pytest.raises(jsonschema.ValidationError):
            manifest.validate_config({"volatility_level": "extreme"})


class TestVolatilityMarketLoading:
    TENANT = "tn_vol_load"

    def setup_method(self):
        _install_builtin(self.TENANT, _VOL_DIR, "volatility-market")
        _clear_module_cache(self.TENANT)

    def test_loads_as_market_plugin(self):
        plugin = PluginRegistry.load_plugin(self.TENANT, "volatility-market")
        assert isinstance(plugin, MarketPlugin)

    def test_get_template_method_exists(self):
        plugin = PluginRegistry.load_plugin(self.TENANT, "volatility-market")
        assert callable(getattr(plugin, "get_template", None))


class TestVolatilityMarketTemplate:
    TENANT = "tn_vol_template"

    def setup_method(self):
        _install_builtin(self.TENANT, _VOL_DIR, "volatility-market")
        _clear_module_cache(self.TENANT)

    def _plugin(self):
        _clear_module_cache(self.TENANT)
        return PluginRegistry.load_plugin(self.TENANT, "volatility-market")

    def test_returns_dict(self):
        plugin = self._plugin()
        result = plugin.get_template({})
        assert isinstance(result, dict)

    def test_default_medium_level(self):
        plugin = self._plugin()
        result = plugin.get_template({})
        # medium preset: minutes_per_round=30
        assert result["time_config"]["minutes_per_round"] == 30

    def test_low_volatility_longer_rounds(self):
        plugin = self._plugin()
        result = plugin.get_template({"volatility_level": "low"})
        assert result["time_config"]["minutes_per_round"] == 45

    def test_high_volatility_shortest_rounds(self):
        plugin = self._plugin()
        result = plugin.get_template({"volatility_level": "high"})
        assert result["time_config"]["minutes_per_round"] == 15

    def test_high_volatility_lower_viral_threshold(self):
        plugin = self._plugin()
        result = plugin.get_template({"volatility_level": "high"})
        assert result["twitter_config"]["viral_threshold"] < 10
        assert result["reddit_config"]["viral_threshold"] < 10

    def test_high_volatility_stronger_echo_chamber(self):
        plugin = self._plugin()
        result = plugin.get_template({"volatility_level": "high"})
        assert result["twitter_config"]["echo_chamber_strength"] > 0.7

    def test_breaking_news_disabled_by_default(self):
        plugin = self._plugin()
        result = plugin.get_template({})
        assert "event_config" not in result

    def test_breaking_news_injects_event(self):
        plugin = self._plugin()
        result = plugin.get_template({"enable_breaking_news": True})
        assert "event_config" in result
        events = result["event_config"].get("scheduled_events", [])
        assert len(events) == 1
        event = events[0]
        assert event["round"] == 1
        assert "breaking" in event.get("tags", [])

    def test_invalid_level_falls_back_to_medium(self):
        plugin = self._plugin()
        result = plugin.get_template({"volatility_level": "catastrophic"})
        # Falls back to medium: minutes_per_round=30
        assert result["time_config"]["minutes_per_round"] == 30

    def test_all_three_levels_have_different_round_durations(self):
        plugin = self._plugin()
        low = plugin.get_template({"volatility_level": "low"})["time_config"]["minutes_per_round"]
        _clear_module_cache(self.TENANT)
        plugin = PluginRegistry.load_plugin(self.TENANT, "volatility-market")
        med = plugin.get_template({"volatility_level": "medium"})["time_config"]["minutes_per_round"]
        _clear_module_cache(self.TENANT)
        plugin = PluginRegistry.load_plugin(self.TENANT, "volatility-market")
        high = plugin.get_template({"volatility_level": "high"})["time_config"]["minutes_per_round"]
        assert high < med < low
