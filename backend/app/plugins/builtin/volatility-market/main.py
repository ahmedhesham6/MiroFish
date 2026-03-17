"""
Volatility Market Plugin — high-volatility simulation template.

Overrides simulation parameters to model fast-moving, sentiment-extreme
markets (e.g. crypto, breaking news cycles, Polymarket events).
"""

from typing import Any, Dict

from app.plugins.sdk import MarketPlugin


# Preset overrides per volatility level.
# Keys map to SimulationParameters.to_dict() field paths supported by
# PluginHooks.run_market_hooks (flat merge into the params dict).
_PRESETS: Dict[str, Dict[str, Any]] = {
    "low": {
        # Slightly shorter rounds, mild amplification
        "time_config": {
            "minutes_per_round": 45,
            "total_simulation_hours": 48,
        },
        "twitter_config": {
            "viral_threshold": 8,
            "echo_chamber_strength": 0.4,
        },
        "reddit_config": {
            "viral_threshold": 8,
            "echo_chamber_strength": 0.4,
        },
    },
    "medium": {
        # Balanced: shorter rounds, moderate amplification
        "time_config": {
            "minutes_per_round": 30,
            "total_simulation_hours": 36,
        },
        "twitter_config": {
            "viral_threshold": 5,
            "echo_chamber_strength": 0.65,
        },
        "reddit_config": {
            "viral_threshold": 5,
            "echo_chamber_strength": 0.65,
        },
    },
    "high": {
        # Aggressive: very short rounds, extreme amplification
        "time_config": {
            "minutes_per_round": 15,
            "total_simulation_hours": 24,
        },
        "twitter_config": {
            "viral_threshold": 3,
            "echo_chamber_strength": 0.85,
        },
        "reddit_config": {
            "viral_threshold": 3,
            "echo_chamber_strength": 0.85,
        },
    },
}

_BREAKING_NEWS_EVENT = {
    "type": "scheduled",
    "round": 1,
    "content": "BREAKING: Major market-moving event detected. Sentiment spike imminent.",
    "tags": ["breaking", "volatility"],
}


class VolatilityMarketPlugin(MarketPlugin):
    """Returns SimulationParameters overrides for a high-volatility market environment."""

    def get_template(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Build and return simulation parameter overrides.

        Args:
            config:
                volatility_level (str): "low", "medium", or "high". Default "medium".
                enable_breaking_news (bool): Inject a breaking-news event. Default False.

        Returns:
            Dict of simulation parameter overrides merged by PluginHooks.run_market_hooks.
        """
        level: str = config.get("volatility_level", "medium")
        if level not in _PRESETS:
            level = "medium"

        overrides: Dict[str, Any] = {}
        preset = _PRESETS[level]
        overrides.update(preset)

        if config.get("enable_breaking_news", False):
            overrides["event_config"] = {
                "scheduled_events": [_BREAKING_NEWS_EVENT],
            }

        return overrides
