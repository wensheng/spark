"""
Dummy model
It just echoes the input back
"""

import json
import logging
from typing import Any, Optional, Type, TypeVar, override

from pydantic import BaseModel

from spark.models.types import ChatCompletionAssistantMessage, Messages
from spark.tools.types import ToolChoice, ToolSpec
from .base import Model

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class EchoModel(Model):
    """Emulate a LLM model"""

    def __init__(self, streaming: bool = False) -> None:
        """Initialize echo model"""
        self.streaming = streaming

    @override
    def update_config(self, **model_config) -> None:  # type: ignore
        """Dummy update config"""
        pass

    @override
    def get_config(self) -> dict[str, Any]:
        """Get the config"""
        return {
            "model_id": "echo",
            "streaming": self.streaming
        }

    @override
    async def get_text(
        self,
        messages: Messages,
        system_prompt: Optional[str] = None,
        tool_specs: list[ToolSpec] | None = None,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> ChatCompletionAssistantMessage:
        """Get the complete text response from the model."""
        txt = '\n'.join([' '.join([a['text'] for a in message['content'] if 'text' in a]) for message in messages])
        return {"role": "assistant", "content": txt}

    @override
    async def get_json(
        self,
        output_model: Type[T],
        messages: Messages,
        system_prompt: Optional[str] = None,
        tool_specs: list[ToolSpec] | None = None,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> ChatCompletionAssistantMessage:
        """Get the complete json response from the model."""
        return {
            "role": "assistant",
            "content": json.dumps(output_model(**{'role': messages[0]['role'], 'content': messages[0]['content']})),
        }

    @classmethod
    def from_spec_dict(cls, spec: dict[str, Any]) -> "EchoModel":
        """Deserialize EchoModel from spec dictionary.

        Args:
            spec: Dictionary containing model configuration

        Returns:
            EchoModel instance

        Example:
            spec = {"type": "EchoModel", "config": {"streaming": False}}
            model = EchoModel.from_spec_dict(spec)
        """
        config = spec.get("config", {})
        streaming = config.get("streaming", False)
        return cls(streaming=streaming)
