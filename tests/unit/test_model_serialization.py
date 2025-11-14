"""Tests for model serialization."""

import pytest
from spark.models.echo import EchoModel
from spark.models.base import Model


class TestModelSerialization:
    """Test Model serialization functionality."""

    def test_echo_model_to_spec_dict(self):
        """Test serializing EchoModel to spec dict."""
        model = EchoModel(streaming=False)

        spec = model.to_spec_dict()

        assert "type" in spec
        assert spec["type"] == "EchoModel"
        assert "provider" in spec
        assert "model_id" in spec
        assert spec["model_id"] == "echo"
        assert "config" in spec
        assert spec["config"]["streaming"] is False

    def test_echo_model_from_spec_dict(self):
        """Test deserializing EchoModel from spec dict."""
        spec = {
            "type": "EchoModel",
            "provider": "echo",
            "model_id": "echo",
            "config": {
                "model_id": "echo",
                "streaming": True
            }
        }

        model = EchoModel.from_spec_dict(spec)

        assert isinstance(model, EchoModel)
        assert model.streaming is True

    def test_echo_model_round_trip(self):
        """Test round-trip serialization for EchoModel."""
        model1 = EchoModel(streaming=True)

        # Serialize
        spec = model1.to_spec_dict()

        # Deserialize
        model2 = EchoModel.from_spec_dict(spec)

        # Check that properties match
        assert model2.streaming == model1.streaming

        # Serialize again
        spec2 = model2.to_spec_dict()

        # Should be equivalent
        assert spec2["type"] == spec["type"]
        assert spec2["model_id"] == spec["model_id"]
        assert spec2["config"]["streaming"] == spec["config"]["streaming"]

    def test_spec_dict_provider_name(self):
        """Test that provider name is correctly extracted."""
        model = EchoModel()

        spec = model.to_spec_dict()

        assert spec["provider"] == "echo"

    def test_spec_dict_structure(self):
        """Test that spec dict has correct structure."""
        model = EchoModel(streaming=False)

        spec = model.to_spec_dict()

        # Check required fields
        assert "type" in spec
        assert "provider" in spec
        assert "model_id" in spec
        assert "config" in spec

        # Check types
        assert isinstance(spec["type"], str)
        assert isinstance(spec["provider"], str)
        assert isinstance(spec["config"], dict)

    def test_base_model_from_spec_dict_not_implemented(self):
        """Test that base Model.from_spec_dict() raises NotImplementedError."""
        spec = {"type": "Model", "config": {}}

        with pytest.raises(NotImplementedError, match="must be implemented by subclass"):
            Model.from_spec_dict(spec)


class TestModelSerializationIntegration:
    """Test model serialization integration with other components."""

    def test_model_in_agent_config_spec(self):
        """Test that models work with AgentConfig spec serialization."""
        from spark.agents.config import AgentConfig

        model = EchoModel()
        config = AgentConfig(
            model=model,
            system_prompt="Test"
        )

        spec = config.to_spec_dict()

        # Check that model info is in spec
        assert "model" in spec
        assert isinstance(spec["model"], dict)
        assert spec["model"]["type"] == "EchoModel"

    def test_multiple_model_types(self):
        """Test serialization with different model types."""
        # EchoModel
        echo_model = EchoModel(streaming=False)
        echo_spec = echo_model.to_spec_dict()
        assert echo_spec["type"] == "EchoModel"

        # Should be able to recreate
        echo_model2 = EchoModel.from_spec_dict(echo_spec)
        assert isinstance(echo_model2, EchoModel)
        assert echo_model2.streaming == echo_model.streaming
