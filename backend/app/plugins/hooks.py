"""
Plugin pipeline hooks: wires SourcePlugin, MarketPlugin, and ActionPlugin
into the MiroFish processing pipeline.

All plugin calls are wrapped via PluginExecutor — failures are logged but
never block the pipeline.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger
from .executor import PluginExecutor
from .registry import PluginRegistry

logger = get_logger("mirofish.plugins.hooks")

_executor = PluginExecutor()


@dataclass
class PluginContext:
    """Read-only context passed to plugins during pipeline execution."""

    tenant_id: str
    project_id: Optional[str] = None
    simulation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PluginHooks:
    """
    Centralises plugin hook execution at each pipeline stage.

    All methods are tolerant of plugin failures — a failed plugin is logged
    as a warning and skipped; the pipeline continues unchanged.
    """

    # ---------------------------------------------------------------------------
    # Source hooks — ontology / document pre-processing
    # ---------------------------------------------------------------------------

    @staticmethod
    def run_source_hooks(
        ctx: PluginContext,
        document_texts: List[str],
    ) -> List[str]:
        """
        Execute all enabled Source plugins for the tenant and merge their
        returned documents into the document_texts list.

        Args:
            ctx: Plugin context (tenant_id, optional project/sim ids, metadata).
            document_texts: Existing document texts passed to OntologyGenerator.

        Returns:
            Augmented list of document texts (originals + plugin-injected).
        """
        tenant_id = ctx.tenant_id
        enabled = _get_enabled_plugins(tenant_id, "source")
        if not enabled:
            return document_texts

        augmented = list(document_texts)
        for plugin_name in enabled:
            config = _load_plugin_config(tenant_id, plugin_name)
            try:
                plugin = PluginRegistry.load_plugin(tenant_id, plugin_name)
            except Exception as exc:
                logger.warning(f"[source hook] Failed to load plugin {plugin_name!r}: {exc}")
                continue

            result = _executor.execute(plugin, "fetch_data", timeout_sec=30, config=config)
            if not result.success:
                logger.warning(
                    f"[source hook] Plugin {plugin_name!r} fetch_data failed "
                    f"(elapsed={result.elapsed_ms:.0f}ms): {result.error}"
                )
                continue

            data = result.data or {}
            docs = data.get("documents", [])
            for doc in docs:
                if isinstance(doc, str):
                    augmented.append(doc)
                elif isinstance(doc, dict) and "text" in doc:
                    augmented.append(doc["text"])

            logger.info(
                f"[source hook] Plugin {plugin_name!r} injected {len(docs)} document(s) "
                f"(elapsed={result.elapsed_ms:.0f}ms)"
            )

        return augmented

    # ---------------------------------------------------------------------------
    # Market hooks — simulation config overrides
    # ---------------------------------------------------------------------------

    @staticmethod
    def run_market_hooks(
        ctx: PluginContext,
        sim_params_dict: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute all enabled Market plugins and merge their template overrides
        into the simulation parameters dict (plugin values override defaults).

        Args:
            ctx: Plugin context.
            sim_params_dict: The simulation parameters dict (from SimulationParameters.to_dict()).

        Returns:
            Merged simulation parameters dict.
        """
        tenant_id = ctx.tenant_id
        enabled = _get_enabled_plugins(tenant_id, "market")
        if not enabled:
            return sim_params_dict

        merged = dict(sim_params_dict)
        for plugin_name in enabled:
            config = _load_plugin_config(tenant_id, plugin_name)
            try:
                plugin = PluginRegistry.load_plugin(tenant_id, plugin_name)
            except Exception as exc:
                logger.warning(f"[market hook] Failed to load plugin {plugin_name!r}: {exc}")
                continue

            result = _executor.execute(plugin, "get_template", timeout_sec=30, config=config)
            if not result.success:
                logger.warning(
                    f"[market hook] Plugin {plugin_name!r} get_template failed "
                    f"(elapsed={result.elapsed_ms:.0f}ms): {result.error}"
                )
                continue

            overrides = result.data or {}
            if isinstance(overrides, dict):
                merged.update(overrides)
                logger.info(
                    f"[market hook] Plugin {plugin_name!r} applied {len(overrides)} override(s) "
                    f"(elapsed={result.elapsed_ms:.0f}ms)"
                )

        return merged

    # ---------------------------------------------------------------------------
    # Action hooks — simulation round/action transformation
    # ---------------------------------------------------------------------------

    @staticmethod
    def run_round_start_hooks(
        ctx: PluginContext,
        round_num: int,
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Called at the start of each simulation round.
        Collects action overrides from enabled Action plugins.

        Args:
            ctx: Plugin context.
            round_num: Current round number (0-indexed).
            state: Current simulation state snapshot.

        Returns:
            Merged round-start overrides dict (empty dict if none).
        """
        tenant_id = ctx.tenant_id
        enabled = _get_enabled_plugins(tenant_id, "action")
        if not enabled:
            return {}

        merged_overrides: Dict[str, Any] = {}
        for plugin_name in enabled:
            config = _load_plugin_config(tenant_id, plugin_name)
            try:
                plugin = PluginRegistry.load_plugin(tenant_id, plugin_name)
            except Exception as exc:
                logger.warning(f"[action hook] Failed to load plugin {plugin_name!r}: {exc}")
                continue

            result = _executor.execute(
                plugin, "on_round_start", timeout_sec=10,
                round_num=round_num, state=state
            )
            if not result.success:
                logger.warning(
                    f"[action hook] Plugin {plugin_name!r} on_round_start failed "
                    f"(elapsed={result.elapsed_ms:.0f}ms): {result.error}"
                )
                continue

            overrides = result.data
            if isinstance(overrides, dict):
                merged_overrides.update(overrides)

        return merged_overrides

    @staticmethod
    def run_action_hooks(
        ctx: PluginContext,
        agent_id: str,
        action: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Transform an agent action through all enabled Action plugins.

        Args:
            ctx: Plugin context.
            agent_id: ID of the agent producing the action.
            action: Raw action dict.

        Returns:
            Transformed action dict (may be unchanged if no plugins or all failed).
        """
        tenant_id = ctx.tenant_id
        enabled = _get_enabled_plugins(tenant_id, "action")
        if not enabled:
            return action

        current_action = dict(action)
        for plugin_name in enabled:
            config = _load_plugin_config(tenant_id, plugin_name)
            try:
                plugin = PluginRegistry.load_plugin(tenant_id, plugin_name)
            except Exception as exc:
                logger.warning(f"[action hook] Failed to load plugin {plugin_name!r}: {exc}")
                continue

            result = _executor.execute(
                plugin, "on_action", timeout_sec=10,
                agent_id=agent_id, action=current_action
            )
            if not result.success:
                logger.warning(
                    f"[action hook] Plugin {plugin_name!r} on_action failed "
                    f"(elapsed={result.elapsed_ms:.0f}ms): {result.error}"
                )
                continue

            if isinstance(result.data, dict):
                current_action = result.data

        return current_action


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_enabled_plugins(tenant_id: str, plugin_type: str) -> List[str]:
    """Return names of enabled plugins of the given type for this tenant."""
    from ..models.tenant import TenantManager
    tenant = TenantManager.get_tenant(tenant_id)
    if not tenant or not tenant.enabled_plugins:
        return []

    # Filter to only plugins of the requested type
    result = []
    for name in tenant.enabled_plugins:
        from ..plugins.registry import PluginRegistry, _tenant_plugins_dir
        import os
        manifest_path = os.path.join(_tenant_plugins_dir(tenant_id), name, "plugin.yaml")
        if not os.path.isfile(manifest_path):
            continue
        try:
            manifest = PluginRegistry.validate_manifest(manifest_path)
            if manifest.plugin_type == plugin_type:
                result.append(name)
        except Exception:
            pass
    return result


def _load_plugin_config(tenant_id: str, plugin_name: str) -> Dict[str, Any]:
    """Load per-tenant plugin config from filesystem."""
    import json
    import os
    from ..plugins.registry import _tenant_plugins_dir
    path = os.path.join(_tenant_plugins_dir(tenant_id), plugin_name, "config.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
