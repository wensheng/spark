"""
Utility functions for model management.
"""

import warnings
from typing import Any, Mapping, Type, get_type_hints

from spark.tools.types import ToolChoice
from spark.models.base import Model


def get_model_from_id(model_id: str, **kwargs) -> Model:
    """
    get model instance from model_id
    """
    if model_id == 'echo':
        from spark.models.echo import EchoModel
        return EchoModel(model_id=model_id, **kwargs)

    model_id_no_prefix = model_id.split("/", 1)[1]  # Extract the part after the prefix
    if model_id.startswith("openai/"):
        from spark.models.openai import OpenAIModel

        return OpenAIModel(model_id=model_id_no_prefix, **kwargs)

    if model_id.startswith("bedrock/"):
        from spark.models.bedrock import BedrockModel

        return BedrockModel(model_id=model_id_no_prefix, **kwargs)

    if model_id.startswith("gemini/"):
        from spark.models.gemini import GeminiModel

        return GeminiModel(model_id=model_id_no_prefix, **kwargs)

    raise ValueError(f"Unknown model ID prefix: {model_id}")


def validate_config_keys(config_dict: Mapping[str, Any], config_class: Type) -> None:
    """Validate that config keys match the TypedDict fields.

    Args:
        config_dict: Dictionary of configuration parameters
        config_class: TypedDict class to validate against
    """
    valid_keys = set(get_type_hints(config_class).keys())
    provided_keys = set(config_dict.keys())
    invalid_keys = provided_keys - valid_keys

    if invalid_keys:
        warnings.warn(
            f"Invalid configuration parameters: {sorted(invalid_keys)}.\nValid parameters are: {sorted(valid_keys)}.",
            stacklevel=4,
        )


def warn_on_tool_choice_not_supported(tool_choice: ToolChoice | None) -> None:
    """Emits a warning if a tool choice is provided but not supported by the provider.

    Args:
        tool_choice: the tool_choice provided to the provider
    """
    if tool_choice:
        warnings.warn(
            "A ToolChoice was provided to this provider but is not supported and will be ignored",
            stacklevel=4,
        )
