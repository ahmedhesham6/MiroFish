"""
Plugin SDK: base classes and YAML manifest format for MiroFish plugins.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import yaml
import jsonschema


VALID_PLUGIN_TYPES = {"source", "market", "action"}


@dataclass
class PluginManifest:
    """Parsed representation of a plugin.yaml manifest file."""

    name: str
    version: str
    plugin_type: str  # "source", "market", "action"
    entry_point: str  # e.g. "main:MyPlugin"
    description: str
    author: str
    config_schema: Dict[str, Any] = field(default_factory=dict)

    def validate_config(self, config: Dict[str, Any]) -> None:
        """Validate a tenant-supplied config dict against config_schema.

        Raises jsonschema.ValidationError if validation fails.
        Raises jsonschema.SchemaError if config_schema is invalid.
        """
        if self.config_schema:
            jsonschema.validate(instance=config, schema=self.config_schema)

    @classmethod
    def from_yaml(cls, path: str) -> "PluginManifest":
        """Load and parse a plugin.yaml file.

        Raises ValueError for missing required fields or invalid plugin_type.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        required = ("name", "version", "type", "entry_point", "description", "author")
        for key in required:
            if key not in data:
                raise ValueError(f"plugin.yaml missing required field: {key!r}")

        plugin_type = data["type"]
        if plugin_type not in VALID_PLUGIN_TYPES:
            raise ValueError(
                f"Invalid plugin type {plugin_type!r}. Must be one of: {sorted(VALID_PLUGIN_TYPES)}"
            )

        return cls(
            name=data["name"],
            version=str(data["version"]),
            plugin_type=plugin_type,
            entry_point=data["entry_point"],
            description=data["description"],
            author=data["author"],
            config_schema=data.get("config_schema", {}),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        """Construct a PluginManifest from a plain dict (e.g. loaded from JSON storage)."""
        plugin_type = data.get("type") or data.get("plugin_type", "")
        if plugin_type not in VALID_PLUGIN_TYPES:
            raise ValueError(
                f"Invalid plugin type {plugin_type!r}. Must be one of: {sorted(VALID_PLUGIN_TYPES)}"
            )
        return cls(
            name=data["name"],
            version=str(data["version"]),
            plugin_type=plugin_type,
            entry_point=data["entry_point"],
            description=data.get("description", ""),
            author=data.get("author", ""),
            config_schema=data.get("config_schema", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "type": self.plugin_type,
            "entry_point": self.entry_point,
            "description": self.description,
            "author": self.author,
            "config_schema": self.config_schema,
        }


class SourcePlugin(ABC):
    """Feeds external data into ontology generation."""

    @abstractmethod
    def fetch_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch data from the external source.

        Args:
            config: Tenant-supplied config validated against manifest config_schema.

        Returns:
            Dict with keys:
                documents (list): List of text/document dicts for ontology generation.
                metadata (dict): Arbitrary metadata about the fetch (timestamps, counts, etc.).
        """


class MarketPlugin(ABC):
    """Provides simulation environment templates."""

    @abstractmethod
    def get_template(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Return simulation parameter overrides for this market environment.

        Args:
            config: Tenant-supplied config validated against manifest config_schema.

        Returns:
            Dict of simulation parameter overrides (merged into base simulation config).
        """


class ActionPlugin(ABC):
    """Extends agent behavior during simulation."""

    @abstractmethod
    def on_round_start(self, round_num: int, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Called at the start of each simulation round.

        Args:
            round_num: Current round number (0-indexed).
            state: Current simulation state snapshot.

        Returns:
            Dict of action overrides to inject, or None to pass through unchanged.
        """

    @abstractmethod
    def on_action(self, agent_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
        """Transform or filter an agent action before it is applied.

        Args:
            agent_id: ID of the agent producing the action.
            action: The raw action dict from the simulation agent.

        Returns:
            Modified action dict (may be the same object).
        """
