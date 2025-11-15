"""Reusable condition helpers for declarative edge routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from spark.nodes.base import EdgeCondition


def _literal(value: Any) -> str:
    """Render a Python literal suitable for EdgeCondition expressions."""

    if isinstance(value, str):
        return repr(value)
    return repr(value)


@dataclass(frozen=True)
class ConditionLibrary:
    """Collection of reusable condition factories."""

    @staticmethod
    def success(field: str = 'status', value: Any = 'success') -> EdgeCondition:
        """Match when a node reports a success status."""

        return EdgeCondition(equals={field: value})

    @staticmethod
    def failure(field: str = 'status', value: Any = 'failed') -> EdgeCondition:
        """Match when a node reports a failure status."""

        return EdgeCondition(equals={field: value})

    @staticmethod
    def threshold(field: str, *, op: str = '>=', value: Any = 0) -> EdgeCondition:
        """Match when a numeric field crosses a threshold."""

        allowed = {'>=', '>', '<=', '<', '==', '!='}
        if op not in allowed:
            raise ValueError(f"Unsupported operator {op!r}; choose from {sorted(allowed)}")
        expr = f"$.outputs.{field} {op} {_literal(value)}"
        return EdgeCondition(expr=expr)

    @staticmethod
    def human_approved(field: str = 'approved') -> EdgeCondition:
        """Match when a human approval flag is set in the outputs."""

        expr = f"$.outputs.{field}"
        return EdgeCondition(expr=expr)


# Convenience aliases for direct imports
when_success = ConditionLibrary.success
when_failure = ConditionLibrary.failure
when_threshold = ConditionLibrary.threshold
when_human_approved = ConditionLibrary.human_approved

__all__ = [
    'ConditionLibrary',
    'when_success',
    'when_failure',
    'when_threshold',
    'when_human_approved',
]
