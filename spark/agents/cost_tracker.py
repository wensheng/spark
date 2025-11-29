"""
Cost tracking for agent LLM calls.

This module provides cost tracking capabilities for monitoring token usage
and estimating API costs across agent executions.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional
import logging
import json
import os
from pathlib import Path

logger = logging.getLogger(__name__)


# Fallback pricing per 1M tokens (used if config file not found)
# These are approximate values and should be updated based on actual pricing
_FALLBACK_MODEL_PRICING = {
    # OpenAI models
    'gpt-4-turbo': {'input': 10.00, 'output': 30.00},
    'gpt-4': {'input': 30.00, 'output': 60.00},
    'gpt-4-32k': {'input': 60.00, 'output': 120.00},
    'gpt-4o': {'input': 5.00, 'output': 15.00},
    'gpt-4o-mini': {'input': 0.15, 'output': 0.60},
    'gpt-3.5-turbo': {'input': 0.50, 'output': 1.50},
    'gpt-3.5-turbo-16k': {'input': 3.00, 'output': 4.00},

    # Anthropic Claude models
    'claude-3-opus': {'input': 15.00, 'output': 75.00},
    'claude-3-sonnet': {'input': 3.00, 'output': 15.00},
    'claude-3-haiku': {'input': 0.25, 'output': 1.25},
    'claude-3-5-sonnet': {'input': 3.00, 'output': 15.00},
    'claude-sonnet-4': {'input': 3.00, 'output': 15.00},

    # AWS Bedrock (similar to Anthropic)
    'us.anthropic.claude-3-opus': {'input': 15.00, 'output': 75.00},
    'us.anthropic.claude-3-sonnet': {'input': 3.00, 'output': 15.00},
    'us.anthropic.claude-3-haiku': {'input': 0.25, 'output': 1.25},
    'us.anthropic.claude-sonnet-4-5': {'input': 3.00, 'output': 15.00},

    # Default for unknown models
    'default': {'input': 5.00, 'output': 15.00},
}


def _load_pricing_config(config_path: Optional[str] = None) -> dict[str, dict[str, float]]:
    """Load model pricing from a config file.

    Args:
        config_path: Optional path to pricing config file. If None, looks for:
                    1. Environment variable SPARK_PRICING_CONFIG
                    2. ./model_pricing.json (current directory)
                    3. ~/.spark/model_pricing.json (user home)
                    4. <package>/agents/model_pricing.json (package default)

    Returns:
        Dictionary mapping model IDs to pricing info with 'input' and 'output' keys
    """
    # Determine config file path
    if config_path is None:
        # Try environment variable
        config_path = os.environ.get('SPARK_PRICING_CONFIG')

        if config_path is None:
            # Try current directory
            if os.path.exists('model_pricing.json'):
                config_path = 'model_pricing.json'
            # Try user home directory
            elif os.path.exists(os.path.expanduser('~/.spark/model_pricing.json')):
                config_path = os.path.expanduser('~/.spark/model_pricing.json')
            else:
                # Use package default
                package_dir = Path(__file__).parent
                default_config = package_dir / 'model_pricing.json'
                if default_config.exists():
                    config_path = str(default_config)

    # Try to load from config file
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)

            # Flatten the nested structure (provider -> models)
            pricing = {}
            for provider_key, provider_data in config.items():
                if provider_key.startswith('_'):  # Skip metadata keys like _comment
                    continue
                if provider_key == 'default':
                    pricing['default'] = provider_data
                elif isinstance(provider_data, dict):
                    pricing.update(provider_data)

            logger.info(f"Loaded model pricing from {config_path}")
            return pricing
        except Exception as e:
            logger.warning(
                f"Failed to load pricing config from {config_path}: {e}. "
                f"Using fallback pricing."
            )
    else:
        logger.debug(
            f"No pricing config file found (tried {config_path}). "
            f"Using fallback pricing. Set SPARK_PRICING_CONFIG environment variable "
            f"or place model_pricing.json in current directory, ~/.spark/, "
            f"or use the package default."
        )

    # Return fallback pricing
    return _FALLBACK_MODEL_PRICING


# Load pricing on module import
MODEL_PRICING = _load_pricing_config()


@dataclass
class CallCost:
    """Cost information for a single LLM call.

    Attributes:
        model_id: Model identifier
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        input_cost: Cost of input tokens in USD
        output_cost: Cost of output tokens in USD
        total_cost: Total cost in USD
        timestamp: When the call was made
    """
    model_id: str
    input_tokens: int
    output_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float
    timestamp: float
    namespace: str = "default"

    def __repr__(self) -> str:
        return (
            f"CallCost(model={self.model_id}, "
            f"tokens={self.input_tokens + self.output_tokens}, "
            f"cost=${self.total_cost:.6f})"
        )


@dataclass
class CostStats:
    """Aggregated cost statistics.

    Attributes:
        total_calls: Total number of LLM calls
        total_input_tokens: Total input tokens across all calls
        total_output_tokens: Total output tokens across all calls
        total_tokens: Total tokens (input + output)
        total_cost: Total cost in USD
        cost_by_model: Cost breakdown by model
    """
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    cost_by_model: dict[str, float] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"CostStats(calls={self.total_calls}, "
            f"tokens={self.total_tokens}, "
            f"cost=${self.total_cost:.6f})"
        )


class CostTracker:
    """Track costs for LLM API calls.

    Usage:
        tracker = CostTracker()
        tracker.record_call('gpt-4o', input_tokens=100, output_tokens=50)
        stats = tracker.get_stats()
        print(f"Total cost: ${stats.total_cost:.4f}")
    """

    def __init__(self, pricing_config_path: Optional[str] = None):
        """Initialize cost tracker.

        Args:
            pricing_config_path: Optional path to custom pricing config file.
                                If None, uses the default pricing lookup order.
        """
        self.calls: list[CallCost] = []
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost = 0.0
        self._cost_by_model: dict[str, float] = {}
        self._stats_by_namespace: dict[str, CostStats] = {}
        self._listeners: list[Callable[[CallCost, str], None]] = []
        self._pricing_config_path = pricing_config_path
        self._pricing: dict[str, dict[str, float]] = {}
        self._load_pricing()

    def record_call(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        timestamp: Optional[float] = None,
        *,
        namespace: str | None = None,
    ) -> CallCost:
        """Record an LLM API call and calculate cost.

        Args:
            model_id: Model identifier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            timestamp: When the call was made (defaults to current time)

        Returns:
            CallCost object with cost breakdown
        """
        import time

        if timestamp is None:
            timestamp = time.time()

        # Get pricing for this model
        pricing = self._get_pricing(model_id)

        # Calculate costs (pricing is per 1M tokens)
        input_cost = (input_tokens / 1_000_000) * pricing['input']
        output_cost = (output_tokens / 1_000_000) * pricing['output']
        total_cost = input_cost + output_cost

        ns = namespace or "default"

        # Create cost record
        call_cost = CallCost(
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            timestamp=timestamp,
            namespace=ns,
        )

        # Update totals
        self.calls.append(call_cost)
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._total_cost += total_cost
        self._cost_by_model[model_id] = self._cost_by_model.get(model_id, 0.0) + total_cost

        stats = self._stats_by_namespace.setdefault(ns, CostStats())
        stats.total_calls += 1
        stats.total_input_tokens += input_tokens
        stats.total_output_tokens += output_tokens
        stats.total_tokens = stats.total_input_tokens + stats.total_output_tokens
        stats.total_cost += total_cost
        stats.cost_by_model[model_id] = stats.cost_by_model.get(model_id, 0.0) + total_cost

        self._notify_listeners(call_cost, ns)

        logger.debug(
            f"Recorded call: {model_id}, "
            f"tokens={input_tokens + output_tokens}, "
            f"cost=${total_cost:.6f}"
        )

        return call_cost

    def _load_pricing(self) -> None:
        """Load pricing configuration from file or use defaults."""
        self._pricing = _load_pricing_config(self._pricing_config_path)

    def reload_pricing(self, config_path: Optional[str] = None) -> None:
        """Reload pricing configuration from file.

        Args:
            config_path: Optional path to pricing config file. If None, uses
                        the path specified during initialization or default lookup.
        """
        if config_path is not None:
            self._pricing_config_path = config_path
        self._load_pricing()
        logger.info("Pricing configuration reloaded")

    def _get_pricing(self, model_id: str) -> dict[str, float]:
        """Get pricing for a model.

        Args:
            model_id: Model identifier

        Returns:
            Dict with 'input' and 'output' pricing per 1M tokens
        """
        # Try exact match first
        if model_id in self._pricing:
            return self._pricing[model_id]

        # Try partial match (e.g., 'gpt-4o-2024-05-13' matches 'gpt-4o')
        for key in self._pricing:
            if model_id.startswith(key):
                return self._pricing[key]

        # Use default pricing
        logger.warning(
            f"Unknown model '{model_id}', using default pricing. "
            f"Update model_pricing.json config file for accurate costs."
        )
        return self._pricing.get('default', {'input': 5.00, 'output': 15.00})

    def add_listener(self, listener: Callable[[CallCost, str], None]) -> None:
        """Register a callback invoked whenever a call is recorded."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[CallCost, str], None]) -> None:
        """Remove a previously registered listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify_listeners(self, call_cost: CallCost, namespace: str) -> None:
        for listener in list(self._listeners):
            try:
                listener(call_cost, namespace)
            except Exception:
                logger.exception("Cost tracker listener failed for namespace=%s", namespace)

    def get_stats(self, namespace: str | None = None) -> CostStats:
        """Get aggregated cost statistics.

        Returns:
            CostStats object with totals and breakdowns
        """
        if namespace:
            stats = self._stats_by_namespace.get(namespace)
            if stats:
                return CostStats(
                    total_calls=stats.total_calls,
                    total_input_tokens=stats.total_input_tokens,
                    total_output_tokens=stats.total_output_tokens,
                    total_tokens=stats.total_tokens,
                    total_cost=stats.total_cost,
                    cost_by_model=dict(stats.cost_by_model),
                )
            return CostStats()

        return CostStats(
            total_calls=len(self.calls),
            total_input_tokens=self._total_input_tokens,
            total_output_tokens=self._total_output_tokens,
            total_tokens=self._total_input_tokens + self._total_output_tokens,
            total_cost=self._total_cost,
            cost_by_model=dict(self._cost_by_model)
        )

    def get_calls(self, model_id: Optional[str] = None, namespace: str | None = None) -> list[CallCost]:
        """Get call history, optionally filtered by model.

        Args:
            model_id: Optional model ID to filter by
            namespace: Optional namespace to filter by

        Returns:
            List of CallCost objects
        """
        calls = list(self.calls)
        if model_id is not None:
            calls = [c for c in calls if c.model_id == model_id]
        if namespace is not None:
            calls = [c for c in calls if c.namespace == namespace]
        return calls

    def reset(self) -> None:
        """Reset all tracking data."""
        self.calls.clear()
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost = 0.0
        self._cost_by_model.clear()
        self._stats_by_namespace.clear()
        logger.debug("Cost tracker reset")

    def format_summary(self, namespace: str | None = None) -> str:
        """Format a human-readable cost summary.

        Returns:
            Formatted string with cost breakdown
        """
        stats = self.get_stats(namespace)

        lines = [
            "Cost Summary",
            "=" * 50,
            f"Total Calls: {stats.total_calls}",
            f"Total Tokens: {stats.total_tokens:,}",
            f"  - Input: {stats.total_input_tokens:,}",
            f"  - Output: {stats.total_output_tokens:,}",
            f"Total Cost: ${stats.total_cost:.6f}",
        ]

        if stats.cost_by_model:
            lines.append("")
            lines.append("Cost by Model:")
            for model, cost in sorted(stats.cost_by_model.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  - {model}: ${cost:.6f}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        stats = self.get_stats()
        return f"CostTracker(calls={stats.total_calls}, cost=${stats.total_cost:.6f})"
