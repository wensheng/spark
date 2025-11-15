"""Strategy registry for reasoning strategies.

This module provides a central registry for reasoning strategies, enabling
spec-compatible serialization using strategy names and string references.
"""

import logging
from typing import Any, Optional, Type

from spark.agents.strategies import (
    ReasoningStrategy,
    NoOpStrategy,
    ReActStrategy,
    ChainOfThoughtStrategy,
    PlanAndSolveStrategy,
)
from spark.utils.import_utils import import_class_from_ref, get_ref_for_class, validate_reference

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Central registry for reasoning strategies.

    This class manages strategy registration, validation, and discovery.
    Built-in strategies are auto-registered by name.
    """

    def __init__(self) -> None:
        """Initialize the strategy registry with built-in strategies."""
        self.registry: dict[str, Type[ReasoningStrategy]] = {}
        self.strategy_refs: dict[str, str] = {}  # name -> module:class reference

        # Auto-register built-in strategies
        self._register_builtin_strategies()

    def _register_builtin_strategies(self) -> None:
        """Register built-in strategies with standard names."""
        builtin_strategies = {
            "noop": NoOpStrategy,
            "react": ReActStrategy,
            "chain_of_thought": ChainOfThoughtStrategy,
            "plan_and_solve": PlanAndSolveStrategy,
        }

        for name, strategy_class in builtin_strategies.items():
            self.register_strategy(name, strategy_class)
            logger.debug("Built-in strategy registered: %s", name)

    def register_strategy(
        self,
        name: str,
        strategy_class: Type[ReasoningStrategy]
    ) -> None:
        """Register a strategy class with a given name.

        Args:
            name: Name to register the strategy under
            strategy_class: Strategy class (not instance) to register

        Raises:
            ValueError: If name already exists or class is invalid

        Example:
            registry.register_strategy("custom", MyCustomStrategy)
        """
        if not isinstance(strategy_class, type):
            raise ValueError(f"strategy_class must be a class, got {type(strategy_class)}")

        if not issubclass(strategy_class, ReasoningStrategy):
            raise ValueError(
                f"strategy_class must be a subclass of ReasoningStrategy, "
                f"got {strategy_class}"
            )

        if name in self.registry:
            logger.warning(
                "Strategy name '%s' already registered, overwriting with %s",
                name,
                strategy_class.__name__
            )

        self.registry[name] = strategy_class

        # Try to capture reference for serialization
        try:
            ref = get_ref_for_class(strategy_class)
            self.strategy_refs[name] = ref
            logger.debug("strategy_name=<%s>, ref=<%s> | captured strategy reference", name, ref)
        except Exception as e:
            logger.debug(
                "strategy_name=<%s> | could not capture strategy reference: %s",
                name,
                e
            )

    def register_strategy_by_ref(
        self,
        name: str,
        ref: str
    ) -> None:
        """Register a strategy by module:class string reference.

        Args:
            name: Name to register the strategy under
            ref: String reference in format "module.path:ClassName"

        Raises:
            ValueError: If reference is invalid or cannot be imported

        Example:
            registry.register_strategy_by_ref("custom", "myapp.strategies:CustomStrategy")
        """
        # Validate the reference
        valid, error = validate_reference(ref)
        if not valid:
            raise ValueError(f"Invalid strategy reference '{ref}': {error}")

        # Import the strategy class
        try:
            strategy_class = import_class_from_ref(ref)
        except Exception as e:
            raise ValueError(f"Failed to import strategy from '{ref}': {e}") from e

        # Check if it's a ReasoningStrategy subclass
        if not isinstance(strategy_class, type) or not issubclass(strategy_class, ReasoningStrategy):
            raise ValueError(
                f"Strategy at '{ref}' is not a ReasoningStrategy subclass"
            )

        # Register the strategy
        self.registry[name] = strategy_class
        self.strategy_refs[name] = ref

        logger.debug("strategy_name=<%s>, ref=<%s> | registered strategy by reference", name, ref)

    def get_strategy_class(self, name: str) -> Type[ReasoningStrategy]:
        """Get a strategy class by name.

        Args:
            name: Name of the strategy

        Returns:
            Strategy class

        Raises:
            KeyError: If strategy name not found

        Example:
            strategy_class = registry.get_strategy_class("react")
            strategy = strategy_class(verbose=True)
        """
        if name not in self.registry:
            raise KeyError(
                f"Strategy '{name}' not found in registry. "
                f"Available strategies: {list(self.registry.keys())}"
            )
        return self.registry[name]

    def create_strategy(
        self,
        name: str,
        **kwargs: Any
    ) -> ReasoningStrategy:
        """Create a strategy instance by name.

        Args:
            name: Name of the strategy
            **kwargs: Arguments to pass to strategy constructor

        Returns:
            Strategy instance

        Raises:
            KeyError: If strategy name not found

        Example:
            strategy = registry.create_strategy("react", verbose=True)
        """
        strategy_class = self.get_strategy_class(name)
        return strategy_class(**kwargs)

    def get_strategy_ref(self, name: str) -> Optional[str]:
        """Get the module:class reference for a strategy.

        Args:
            name: Name of the strategy

        Returns:
            Module:class reference string, or None if not available

        Example:
            ref = registry.get_strategy_ref("react")
            # Returns: "spark.agents.strategies:ReActStrategy"
        """
        return self.strategy_refs.get(name)

    def list_strategies(self) -> list[str]:
        """List all registered strategy names.

        Returns:
            List of strategy names

        Example:
            names = registry.list_strategies()
            # ['noop', 'react', 'chain_of_thought']
        """
        return list(self.registry.keys())

    def to_spec_dict(self) -> dict[str, Any]:
        """Serialize the registry to a spec-compatible dictionary.

        Returns:
            Dictionary containing strategy specifications and references

        Example:
            spec = registry.to_spec_dict()
            # {
            #   "strategies": [
            #     {"name": "react", "ref": "spark.agents.strategies:ReActStrategy"},
            #     ...
            #   ]
            # }
        """
        strategies_list = []

        for name, strategy_class in self.registry.items():
            strategy_dict: dict[str, Any] = {
                "name": name,
                "class_name": strategy_class.__name__
            }

            # Add reference if available
            if name in self.strategy_refs:
                strategy_dict["ref"] = self.strategy_refs[name]

            strategies_list.append(strategy_dict)

        return {"strategies": strategies_list}

    @classmethod
    def from_spec_dict(cls, spec: dict[str, Any]) -> "StrategyRegistry":
        """Deserialize a strategy registry from a spec dictionary.

        This creates a new StrategyRegistry with built-in strategies
        and registers any additional strategies from the spec.

        Args:
            spec: Dictionary containing strategy specifications

        Returns:
            New StrategyRegistry instance with registered strategies

        Example:
            spec = {
                "strategies": [
                    {"name": "custom", "ref": "myapp.strategies:CustomStrategy"},
                    ...
                ]
            }
            registry = StrategyRegistry.from_spec_dict(spec)
        """
        registry = cls()  # This auto-registers built-in strategies

        for strategy_dict in spec.get("strategies", []):
            name = strategy_dict["name"]

            # Skip built-in strategies (already registered)
            if name in ["noop", "react", "chain_of_thought"]:
                continue

            # Register custom strategies by reference
            if "ref" in strategy_dict:
                ref = strategy_dict["ref"]
                try:
                    registry.register_strategy_by_ref(name, ref)
                    logger.debug("strategy_name=<%s>, ref=<%s> | loaded strategy from spec", name, ref)
                except Exception as e:
                    logger.warning(
                        "strategy_name=<%s>, ref=<%s> | failed to load strategy from spec: %s",
                        name,
                        ref,
                        e
                    )
            else:
                logger.warning(
                    "strategy_name=<%s> | no reference available, cannot load strategy from spec",
                    name
                )

        return registry


# Global singleton registry
_global_registry: Optional[StrategyRegistry] = None


def get_global_registry() -> StrategyRegistry:
    """Get the global strategy registry singleton.

    Returns:
        Global StrategyRegistry instance

    Example:
        registry = get_global_registry()
        strategy = registry.create_strategy("react")
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = StrategyRegistry()
    return _global_registry


def register_strategy(name: str, strategy_class: Type[ReasoningStrategy]) -> None:
    """Register a strategy in the global registry.

    Convenience function for registering custom strategies.

    Args:
        name: Name to register the strategy under
        strategy_class: Strategy class to register

    Example:
        from spark.agents.strategy_registry import register_strategy

        class MyStrategy(ReasoningStrategy):
            ...

        register_strategy("my_strategy", MyStrategy)
    """
    registry = get_global_registry()
    registry.register_strategy(name, strategy_class)


def get_strategy(name: str, **kwargs: Any) -> ReasoningStrategy:
    """Create a strategy instance from the global registry.

    Convenience function for creating strategies.

    Args:
        name: Name of the strategy
        **kwargs: Arguments to pass to strategy constructor

    Returns:
        Strategy instance

    Example:
        from spark.agents.strategy_registry import get_strategy

        strategy = get_strategy("react", verbose=True)
    """
    registry = get_global_registry()
    return registry.create_strategy(name, **kwargs)
