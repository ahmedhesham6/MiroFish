# Volatility Market Plugin

High-volatility simulation template for fast-moving, sentiment-extreme markets such as crypto, breaking-news cycles, and prediction-market events.

## Plugin Type

`market` — called before simulation start; overrides `SimulationParameters` fields via `PluginHooks.run_market_hooks`.

## Configuration

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `volatility_level` | string (`low`/`medium`/`high`) | no | `medium` | Controls round duration and platform algorithm aggressiveness |
| `enable_breaking_news` | boolean | no | `false` | Injects a breaking-news scheduled event at round 1 |

## Example Config

```json
{
  "volatility_level": "high",
  "enable_breaking_news": true
}
```

## Overrides by Volatility Level

| Parameter | low | medium | high |
|-----------|-----|--------|------|
| `minutes_per_round` | 45 | 30 | 15 |
| `total_simulation_hours` | 48 | 36 | 24 |
| `viral_threshold` (Twitter/Reddit) | 8 | 5 | 3 |
| `echo_chamber_strength` (Twitter/Reddit) | 0.4 | 0.65 | 0.85 |

## Breaking News Event

When `enable_breaking_news` is `true`, a scheduled event is injected at round 1:

```json
{
  "type": "scheduled",
  "round": 1,
  "content": "BREAKING: Major market-moving event detected. Sentiment spike imminent.",
  "tags": ["breaking", "volatility"]
}
```

## Notes

- All overrides are shallow-merged into the existing simulation parameters dict.
- Unknown `volatility_level` values fall back to `medium`.
- This plugin has no external dependencies.
