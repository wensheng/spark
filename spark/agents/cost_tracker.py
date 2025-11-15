"""
Cost tracking for agent LLM calls.

This module provides cost tracking capabilities for monitoring token usage
and estimating API costs across agent executions.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


# Pricing per 1M tokens (as of 2025-01-13)
# These are approximate values and should be updated based on actual pricing
MODEL_PRICING = {
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
    cost_by_model: Dict[str, float] = field(default_factory=dict)

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

    def __init__(self):
        """Initialize cost tracker."""
        self.calls: List[CallCost] = []
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost = 0.0
        self._cost_by_model: Dict[str, float] = {}
        self._stats_by_namespace: Dict[str, CostStats] = {}
        self._listeners: list[Callable[[CallCost, str], None]] = []

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

    def _get_pricing(self, model_id: str) -> Dict[str, float]:
        """Get pricing for a model.

        Args:
            model_id: Model identifier

        Returns:
            Dict with 'input' and 'output' pricing per 1M tokens
        """
        # Try exact match first
        if model_id in MODEL_PRICING:
            return MODEL_PRICING[model_id]

        # Try partial match (e.g., 'gpt-4o-2024-05-13' matches 'gpt-4o')
        for key in MODEL_PRICING:
            if model_id.startswith(key):
                return MODEL_PRICING[key]

        # Use default pricing
        logger.warning(
            f"Unknown model '{model_id}', using default pricing. "
            f"Update MODEL_PRICING in cost_tracker.py for accurate costs."
        )
        return MODEL_PRICING['default']

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

    def get_calls(self, model_id: Optional[str] = None, namespace: str | None = None) -> List[CallCost]:
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
