"""Tests for AgentConfig with hook string references."""

import pytest
from spark.agents.config import AgentConfig
from spark.models.echo import EchoModel


# Test hooks defined at module level (can be imported by reference)
def before_hook_example():
    """Example before hook."""
    pass


async def before_hook_async():
    """Example async before hook."""
    pass


def after_hook_example():
    """Example after hook."""
    pass


class TestAgentConfigHooks:
    """Test AgentConfig hook functionality."""

    def test_config_with_callable_hooks(self):
        """Test config with callable hooks."""
        config = AgentConfig(
            model=EchoModel(),
            before_llm_hooks=[before_hook_example],
            after_llm_hooks=[after_hook_example]
        )

        assert len(config.before_llm_hooks) == 1
        assert len(config.after_llm_hooks) == 1
        assert callable(config.before_llm_hooks[0])
        assert callable(config.after_llm_hooks[0])

    def test_config_with_string_hook_references(self):
        """Test config with string hook references."""
        config = AgentConfig(
            model=EchoModel(),
            before_llm_hooks=["tests.unit.test_agent_config:before_hook_example"],
            after_llm_hooks=["tests.unit.test_agent_config:after_hook_example"]
        )

        assert len(config.before_llm_hooks) == 1
        assert len(config.after_llm_hooks) == 1
        assert isinstance(config.before_llm_hooks[0], str)
        assert isinstance(config.after_llm_hooks[0], str)

    def test_config_with_mixed_hooks(self):
        """Test config with both callable and string reference hooks."""
        config = AgentConfig(
            model=EchoModel(),
            before_llm_hooks=[
                before_hook_example,
                "tests.unit.test_agent_config:before_hook_async"
            ],
            after_llm_hooks=[after_hook_example]
        )

        assert len(config.before_llm_hooks) == 2
        assert callable(config.before_llm_hooks[0])
        assert isinstance(config.before_llm_hooks[1], str)

    def test_resolve_callable_hook(self):
        """Test resolving a callable hook (pass-through)."""
        config = AgentConfig(
            model=EchoModel(),
            before_llm_hooks=[before_hook_example]
        )

        resolved = config.resolve_hook(before_hook_example)
        assert resolved == before_hook_example
        assert callable(resolved)

    def test_resolve_string_hook(self):
        """Test resolving a string hook reference."""
        config = AgentConfig(model=EchoModel())

        resolved = config.resolve_hook("tests.unit.test_agent_config:before_hook_example")
        assert callable(resolved)
        assert resolved.__name__ == "before_hook_example"

    def test_resolve_string_hook_invalid(self):
        """Test that invalid string references raise ValueError."""
        config = AgentConfig(model=EchoModel())

        with pytest.raises(ValueError, match="Failed to import hook"):
            config.resolve_hook("invalid_module:nonexistent_hook")

    def test_resolve_hooks_list(self):
        """Test resolving a list of mixed hooks."""
        config = AgentConfig(
            model=EchoModel(),
            before_llm_hooks=[
                before_hook_example,
                "tests.unit.test_agent_config:after_hook_example"
            ]
        )

        resolved = config.resolve_hooks(config.before_llm_hooks)

        assert len(resolved) == 2
        assert all(callable(h) for h in resolved)
        assert resolved[0] == before_hook_example
        assert resolved[1].__name__ == "after_hook_example"

    def test_get_hook_ref(self):
        """Test getting reference from callable hook."""
        config = AgentConfig(model=EchoModel())

        ref = config.get_hook_ref(before_hook_example)

        assert ref is not None
        assert "test_agent_config:before_hook_example" in ref

    def test_get_hook_ref_lambda(self):
        """Test that lambdas return None for reference."""
        config = AgentConfig(model=EchoModel())

        lambda_hook = lambda: None
        ref = config.get_hook_ref(lambda_hook)

        assert ref is None

    def test_to_spec_dict_with_callable_hooks(self):
        """Test serializing config with callable hooks."""
        config = AgentConfig(
            model=EchoModel(),
            system_prompt="Test system",
            before_llm_hooks=[before_hook_example],
            after_llm_hooks=[after_hook_example]
        )

        spec = config.to_spec_dict()

        assert "before_llm_hooks" in spec
        assert "after_llm_hooks" in spec
        assert len(spec["before_llm_hooks"]) == 1
        assert len(spec["after_llm_hooks"]) == 1
        # Should be serialized as string references
        assert isinstance(spec["before_llm_hooks"][0], str)
        assert isinstance(spec["after_llm_hooks"][0], str)

    def test_to_spec_dict_with_string_hooks(self):
        """Test serializing config with string hook references."""
        config = AgentConfig(
            model=EchoModel(),
            before_llm_hooks=["tests.unit.test_agent_config:before_hook_example"],
            after_llm_hooks=["tests.unit.test_agent_config:after_hook_example"]
        )

        spec = config.to_spec_dict()

        assert "before_llm_hooks" in spec
        assert "after_llm_hooks" in spec
        # Should preserve string references
        assert spec["before_llm_hooks"][0] == "tests.unit.test_agent_config:before_hook_example"
        assert spec["after_llm_hooks"][0] == "tests.unit.test_agent_config:after_hook_example"

    def test_to_spec_dict_no_hooks(self):
        """Test serializing config without hooks."""
        config = AgentConfig(
            model=EchoModel(),
            system_prompt="Test system"
        )

        spec = config.to_spec_dict()

        # Empty hook lists should not be in spec
        assert "before_llm_hooks" not in spec
        assert "after_llm_hooks" not in spec

    def test_from_spec_dict(self):
        """Test deserializing config from spec dictionary."""
        spec = {
            "system_prompt": "Test system",
            "prompt_template": "User: {{ query }}",
            "before_llm_hooks": ["tests.unit.test_agent_config:before_hook_example"],
            "after_llm_hooks": ["tests.unit.test_agent_config:after_hook_example"],
            "memory_config": {
                "policy": "null",
                "window": 10,
                "summary_max_chars": 1000
            },
            "output_mode": "text",
            "tool_choice": "auto",
            "max_steps": 50
        }

        model = EchoModel()
        config = AgentConfig.from_spec_dict(spec, model)

        assert config.system_prompt == "Test system"
        assert config.prompt_template == "User: {{ query }}"
        assert len(config.before_llm_hooks) == 1
        assert len(config.after_llm_hooks) == 1
        assert config.before_llm_hooks[0] == "tests.unit.test_agent_config:before_hook_example"
        assert config.after_llm_hooks[0] == "tests.unit.test_agent_config:after_hook_example"
        assert config.max_steps == 50

    def test_round_trip_serialization(self):
        """Test that config can be serialized and deserialized correctly."""
        config1 = AgentConfig(
            model=EchoModel(),
            system_prompt="Test system",
            before_llm_hooks=[before_hook_example],
            after_llm_hooks=[after_hook_example],
            max_steps=75
        )

        # Serialize
        spec = config1.to_spec_dict()

        # Deserialize
        model = EchoModel()
        config2 = AgentConfig.from_spec_dict(spec, model)

        # Check that key properties match
        assert config2.system_prompt == config1.system_prompt
        assert config2.max_steps == config1.max_steps
        assert len(config2.before_llm_hooks) == len(config1.before_llm_hooks)
        assert len(config2.after_llm_hooks) == len(config1.after_llm_hooks)

        # Hooks should be string references after round-trip
        assert isinstance(config2.before_llm_hooks[0], str)
        assert isinstance(config2.after_llm_hooks[0], str)

        # Should be able to resolve them
        resolved_before = config2.resolve_hooks(config2.before_llm_hooks)
        resolved_after = config2.resolve_hooks(config2.after_llm_hooks)
        assert all(callable(h) for h in resolved_before)
        assert all(callable(h) for h in resolved_after)

    def test_spec_dict_structure(self):
        """Test that spec dict has correct structure."""
        config = AgentConfig(
            model=EchoModel(),
            name="test_agent",
            description="Test agent description",
            system_prompt="Test system",
            parallel_tool_execution=True
        )

        spec = config.to_spec_dict()

        # Check required fields
        assert "model" in spec
        assert "name" in spec
        assert "description" in spec
        assert "system_prompt" in spec
        assert "memory_config" in spec
        assert "output_mode" in spec
        assert "tool_choice" in spec
        assert "max_steps" in spec
        assert "parallel_tool_execution" in spec

        # Check types
        assert isinstance(spec["model"], dict)
        assert isinstance(spec["memory_config"], dict)
        assert spec["parallel_tool_execution"] is True


class TestAgentConfigBackwardCompatibility:
    """Test that existing code continues to work."""

    def test_existing_callable_hooks_still_work(self):
        """Test that existing code using callables still works."""
        # This is how users currently use hooks
        config = AgentConfig(
            model=EchoModel(),
            before_llm_hooks=[before_hook_example, before_hook_async],
            after_llm_hooks=[after_hook_example]
        )

        # Should work exactly as before
        assert len(config.before_llm_hooks) == 2
        assert len(config.after_llm_hooks) == 1
        assert all(callable(h) for h in config.before_llm_hooks)
        assert callable(config.after_llm_hooks[0])

    def test_empty_hooks_list(self):
        """Test that empty hooks list works."""
        config = AgentConfig(
            model=EchoModel(),
            before_llm_hooks=[],
            after_llm_hooks=[]
        )

        assert config.before_llm_hooks == []
        assert config.after_llm_hooks == []

        spec = config.to_spec_dict()
        assert "before_llm_hooks" not in spec
        assert "after_llm_hooks" not in spec


class TestAgentConfigStrategies:
    """Test AgentConfig reasoning strategy support."""

    def test_config_with_strategy_instance(self):
        """Test config with strategy instance."""
        from spark.agents.strategies import ReActStrategy

        config = AgentConfig(
            model=EchoModel(),
            reasoning_strategy=ReActStrategy(verbose=False)
        )

        assert config.reasoning_strategy is not None
        assert isinstance(config.reasoning_strategy, ReActStrategy)

    def test_config_with_strategy_name(self):
        """Test config with strategy name string."""
        config = AgentConfig(
            model=EchoModel(),
            reasoning_strategy="react"
        )

        assert config.reasoning_strategy == "react"

    def test_resolve_strategy_instance(self):
        """Test resolving strategy instance (pass-through)."""
        from spark.agents.strategies import NoOpStrategy

        config = AgentConfig(model=EchoModel())
        strategy_instance = NoOpStrategy()

        resolved = config.resolve_strategy(strategy_instance)
        assert resolved is strategy_instance

    def test_resolve_strategy_name(self):
        """Test resolving strategy by name."""
        from spark.agents.strategies import ReActStrategy

        config = AgentConfig(model=EchoModel())

        resolved = config.resolve_strategy("react")
        assert isinstance(resolved, ReActStrategy)

    def test_resolve_strategy_from_config(self):
        """Test resolving strategy from config's reasoning_strategy."""
        from spark.agents.strategies import NoOpStrategy

        config = AgentConfig(
            model=EchoModel(),
            reasoning_strategy="noop"
        )

        resolved = config.resolve_strategy()
        assert isinstance(resolved, NoOpStrategy)

    def test_resolve_strategy_invalid_name(self):
        """Test that invalid strategy name raises ValueError."""
        config = AgentConfig(model=EchoModel())

        with pytest.raises(ValueError, match="Failed to resolve strategy"):
            config.resolve_strategy("nonexistent_strategy")

    def test_get_strategy_spec_from_instance(self):
        """Test getting strategy spec from instance."""
        from spark.agents.strategies import ReActStrategy

        config = AgentConfig(
            model=EchoModel(),
            reasoning_strategy=ReActStrategy()
        )

        spec = config.get_strategy_spec()
        assert spec is not None
        assert "name" in spec
        assert spec["name"] == "react"

    def test_get_strategy_spec_from_name(self):
        """Test getting strategy spec from name."""
        config = AgentConfig(
            model=EchoModel(),
            reasoning_strategy="chain_of_thought"
        )

        spec = config.get_strategy_spec()
        assert spec is not None
        assert "name" in spec
        assert spec["name"] == "chain_of_thought"

    def test_get_strategy_spec_none(self):
        """Test getting strategy spec when no strategy."""
        config = AgentConfig(model=EchoModel())

        spec = config.get_strategy_spec()
        assert spec is None

    def test_to_spec_dict_with_strategy_instance(self):
        """Test serializing config with strategy instance."""
        from spark.agents.strategies import ReActStrategy

        config = AgentConfig(
            model=EchoModel(),
            system_prompt="Test",
            reasoning_strategy=ReActStrategy()
        )

        spec = config.to_spec_dict()

        assert "reasoning_strategy" in spec
        strategy_spec = spec["reasoning_strategy"]
        assert "name" in strategy_spec
        assert strategy_spec["name"] == "react"

    def test_to_spec_dict_with_strategy_name(self):
        """Test serializing config with strategy name."""
        config = AgentConfig(
            model=EchoModel(),
            reasoning_strategy="noop"
        )

        spec = config.to_spec_dict()

        assert "reasoning_strategy" in spec
        assert spec["reasoning_strategy"]["name"] == "noop"

    def test_to_spec_dict_without_strategy(self):
        """Test serializing config without strategy."""
        config = AgentConfig(model=EchoModel())

        spec = config.to_spec_dict()

        assert "reasoning_strategy" not in spec

    def test_from_spec_dict_with_strategy(self):
        """Test deserializing config with strategy."""
        spec = {
            "system_prompt": "Test",
            "reasoning_strategy": {"name": "react"},
            "memory_config": {
                "policy": "null",
                "window": 10,
                "summary_max_chars": 1000
            },
            "output_mode": "text",
            "tool_choice": "auto",
            "max_steps": 100
        }

        model = EchoModel()
        config = AgentConfig.from_spec_dict(spec, model)

        assert config.reasoning_strategy == "react"

        # Should be able to resolve it
        from spark.agents.strategies import ReActStrategy
        resolved = config.resolve_strategy()
        assert isinstance(resolved, ReActStrategy)

    def test_round_trip_with_strategy(self):
        """Test round-trip serialization with strategy."""
        from spark.agents.strategies import ChainOfThoughtStrategy

        config1 = AgentConfig(
            model=EchoModel(),
            system_prompt="Test",
            reasoning_strategy=ChainOfThoughtStrategy()
        )

        # Serialize
        spec = config1.to_spec_dict()

        # Deserialize
        model = EchoModel()
        config2 = AgentConfig.from_spec_dict(spec, model)

        # Should have strategy as name
        assert config2.reasoning_strategy == "chain_of_thought"

        # Should be able to resolve
        from spark.agents.strategies import ChainOfThoughtStrategy
        resolved = config2.resolve_strategy()
        assert isinstance(resolved, ChainOfThoughtStrategy)
