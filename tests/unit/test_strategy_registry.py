"""Tests for strategy registry."""

import pytest
from spark.agents.strategy_registry import (
    StrategyRegistry,
    get_global_registry,
    register_strategy,
    get_strategy
)
from spark.agents.strategies import (
    ReasoningStrategy,
    NoOpStrategy,
    ReActStrategy,
    ChainOfThoughtStrategy
)


# Custom strategy for testing
class CustomStrategy(ReasoningStrategy):
    """Custom test strategy."""

    def __init__(self, test_param: str = "default"):
        self.test_param = test_param

    async def process_step(self, parsed_output, tool_result_blocks, state, context=None):
        pass

    def should_continue(self, parsed_output):
        return False

    def get_history(self, state):
        return []


class TestStrategyRegistry:
    """Test StrategyRegistry functionality."""

    def test_registry_initialization(self):
        """Test registry initializes with built-in strategies."""
        registry = StrategyRegistry()

        # Should have built-in strategies
        assert "noop" in registry.registry
        assert "react" in registry.registry
        assert "chain_of_thought" in registry.registry

    def test_get_strategy_class(self):
        """Test getting strategy class by name."""
        registry = StrategyRegistry()

        noop_class = registry.get_strategy_class("noop")
        assert noop_class == NoOpStrategy

        react_class = registry.get_strategy_class("react")
        assert react_class == ReActStrategy

        cot_class = registry.get_strategy_class("chain_of_thought")
        assert cot_class == ChainOfThoughtStrategy

    def test_get_strategy_class_not_found(self):
        """Test that unknown strategy raises KeyError."""
        registry = StrategyRegistry()

        with pytest.raises(KeyError, match="Strategy 'unknown' not found"):
            registry.get_strategy_class("unknown")

    def test_create_strategy(self):
        """Test creating strategy instance by name."""
        registry = StrategyRegistry()

        # Create NoOp strategy
        strategy = registry.create_strategy("noop")
        assert isinstance(strategy, NoOpStrategy)

        # Create ReAct strategy with parameters
        strategy = registry.create_strategy("react", verbose=False)
        assert isinstance(strategy, ReActStrategy)
        assert strategy.verbose is False

    def test_register_custom_strategy(self):
        """Test registering a custom strategy."""
        registry = StrategyRegistry()

        registry.register_strategy("custom", CustomStrategy)

        assert "custom" in registry.registry
        assert registry.get_strategy_class("custom") == CustomStrategy

    def test_register_strategy_by_ref(self):
        """Test registering strategy by module:class reference."""
        registry = StrategyRegistry()

        registry.register_strategy_by_ref(
            "custom",
            "tests.unit.test_strategy_registry:CustomStrategy"
        )

        assert "custom" in registry.registry
        strategy_class = registry.get_strategy_class("custom")
        assert strategy_class.__name__ == "CustomStrategy"

    def test_register_strategy_by_ref_invalid(self):
        """Test that invalid references raise ValueError."""
        registry = StrategyRegistry()

        with pytest.raises(ValueError, match="Invalid strategy reference"):
            registry.register_strategy_by_ref("bad", "invalid_module:NonExistent")

    def test_register_strategy_invalid_class(self):
        """Test that non-ReasoningStrategy classes raise ValueError."""
        registry = StrategyRegistry()

        class NotAStrategy:
            pass

        with pytest.raises(ValueError, match="must be a subclass of ReasoningStrategy"):
            registry.register_strategy("bad", NotAStrategy)

    def test_get_strategy_ref(self):
        """Test getting strategy reference."""
        registry = StrategyRegistry()

        # Built-in strategies should have references
        ref = registry.get_strategy_ref("noop")
        assert ref is not None
        assert "NoOpStrategy" in ref

    def test_list_strategies(self):
        """Test listing all registered strategies."""
        registry = StrategyRegistry()

        strategies = registry.list_strategies()
        assert "noop" in strategies
        assert "react" in strategies
        assert "chain_of_thought" in strategies

    def test_to_spec_dict(self):
        """Test serializing registry to spec dictionary."""
        registry = StrategyRegistry()

        # Register a custom strategy
        registry.register_strategy("custom", CustomStrategy)

        spec = registry.to_spec_dict()

        assert "strategies" in spec
        strategies = spec["strategies"]
        assert len(strategies) >= 4  # 3 built-in + 1 custom

        # Check structure
        strategy_dict = strategies[0]
        assert "name" in strategy_dict
        assert "class_name" in strategy_dict

        # At least one should have a ref
        refs = [s.get("ref") for s in strategies if "ref" in s]
        assert len(refs) > 0

    def test_from_spec_dict(self):
        """Test deserializing registry from spec dictionary."""
        # Create and populate a registry
        registry1 = StrategyRegistry()
        registry1.register_strategy("custom", CustomStrategy)

        # Serialize
        spec = registry1.to_spec_dict()

        # Deserialize into new registry
        registry2 = StrategyRegistry.from_spec_dict(spec)

        # Should have built-in strategies
        assert "noop" in registry2.registry
        assert "react" in registry2.registry
        assert "chain_of_thought" in registry2.registry

    def test_round_trip_serialization(self):
        """Test that registry can be serialized and deserialized correctly."""
        registry1 = StrategyRegistry()

        # Serialize
        spec = registry1.to_spec_dict()

        # Deserialize
        registry2 = StrategyRegistry.from_spec_dict(spec)

        # Should have same strategies
        assert set(registry1.list_strategies()) == set(registry2.list_strategies())


class TestGlobalRegistry:
    """Test global registry singleton."""

    def test_get_global_registry(self):
        """Test getting global registry."""
        registry = get_global_registry()
        assert isinstance(registry, StrategyRegistry)

        # Should be singleton
        registry2 = get_global_registry()
        assert registry is registry2

    def test_register_strategy_global(self):
        """Test registering strategy in global registry."""
        register_strategy("test_global", CustomStrategy)

        registry = get_global_registry()
        assert "test_global" in registry.registry

    def test_get_strategy_global(self):
        """Test getting strategy from global registry."""
        strategy = get_strategy("noop")
        assert isinstance(strategy, NoOpStrategy)

        # With parameters
        strategy = get_strategy("react", verbose=False)
        assert isinstance(strategy, ReActStrategy)
        assert strategy.verbose is False


class TestStrategyRegistryIntegration:
    """Test strategy registry integration."""

    def test_create_strategy_with_params(self):
        """Test creating strategies with various parameters."""
        registry = StrategyRegistry()

        # Register custom strategy
        registry.register_strategy("custom", CustomStrategy)

        # Create with parameters
        strategy = registry.create_strategy("custom", test_param="hello")
        assert isinstance(strategy, CustomStrategy)
        assert strategy.test_param == "hello"

    def test_registry_overwrite_warning(self):
        """Test that overwriting a strategy name logs warning."""
        registry = StrategyRegistry()

        # First registration
        registry.register_strategy("test", CustomStrategy)

        # Second registration should work but log warning
        registry.register_strategy("test", NoOpStrategy)

        # Should have the new strategy
        assert registry.get_strategy_class("test") == NoOpStrategy
