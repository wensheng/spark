"""Google Gemini model provider.

- Docs: https://ai.google.dev/api
"""

import logging
import mimetypes
import uuid
from typing import Any, Optional, Required, Type, TypedDict, TypeVar, Unpack, cast, override

from google import genai
from pydantic import BaseModel
import json_repair

from spark.models.types import (
    ChatCompletionAssistantToolCall,
    ChatCompletionTextObject,
    ChatCompletionAssistantMessage,
    ContentBlock,
    Messages,
)
from spark.tools.types import ToolChoice, ToolSpec
from spark.models.base import Model
from spark.models.utils import validate_config_keys

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class GeminiModel(Model):
    """Google Gemini model provider implementation.

    - Docs: https://ai.google.dev/api
    """

    class GeminiConfig(TypedDict, total=False):
        """Configuration options for Gemini models.

        Attributes:
            model_id: Gemini model ID (e.g., "gemini-2.5-flash").
                For a complete list of supported models, see
                https://ai.google.dev/gemini-api/docs/models
            params: Additional model parameters (e.g., temperature).
                For a complete list of supported parameters, see
                https://ai.google.dev/api/generate-content#generationconfig.
            enable_cache: Enable response caching (default: False).
            cache_ttl_seconds: Time-to-live for cached responses in seconds (default: 86400 = 24 hours).
        """

        model_id: Required[str]
        params: dict[str, Any]
        enable_cache: bool
        cache_ttl_seconds: int

    def __init__(
        self,
        *,
        client_args: Optional[dict[str, Any]] = None,
        **model_config: Unpack[GeminiConfig],
    ) -> None:
        """Initialize provider instance.

        Args:
            client_args: Arguments for the underlying Gemini client (e.g., api_key).
                For a complete list of supported arguments, see https://googleapis.github.io/python-genai/.
            **model_config: Configuration options for the Gemini model.
        """
        super().__init__()
        validate_config_keys(model_config, GeminiModel.GeminiConfig)
        self.config = GeminiModel.GeminiConfig(**model_config)

        # Initialize cache if enabled
        self._cache_enabled = self.config.get("enable_cache", False)
        self._cache_ttl_seconds = self.config.get("cache_ttl_seconds", 86400)
        self._init_cache()

        logger.debug("config=<%s> | initializing", self.config)

        self.client_args = client_args or {}

    @override
    def update_config(self, **model_config: Unpack[GeminiConfig]) -> None:  # type: ignore[override]
        """Update the Gemini model configuration with the provided arguments.

        Args:
            **model_config: Configuration overrides.
        """
        self.config.update(model_config)

    @override
    def get_config(self) -> GeminiConfig:
        """Get the Gemini model configuration.

        Returns:
            The Gemini model configuration.
        """
        return self.config

    def _get_provider_name(self) -> str:
        """Get provider name for cache key generation."""
        return "gemini"

    def _format_request_content_part(self, content: ContentBlock) -> genai.types.Part:
        """Format content block into a Gemini part instance.

        - Docs: https://googleapis.github.io/python-genai/genai.html#genai.types.Part

        Args:
            content: Message content to format.

        Returns:
            Gemini part.
        """
        if "document" in content:
            return genai.types.Part(
                inline_data=genai.types.Blob(
                    data=content["document"]["source"]["bytes"],
                    mime_type=mimetypes.types_map.get(f".{content['document']['format']}", "application/octet-stream"),
                ),
            )

        if "image" in content:
            return genai.types.Part(
                inline_data=genai.types.Blob(
                    data=content["image"]["source"]["bytes"],
                    mime_type=mimetypes.types_map.get(f".{content['image']['format']}", "application/octet-stream"),
                ),
            )

        if "reasoningContent" in content:
            thought_signature = content["reasoningContent"]["reasoningText"].get("signature")

            return genai.types.Part(
                text=content["reasoningContent"]["reasoningText"]["text"],
                thought=True,
                thought_signature=thought_signature.encode("utf-8") if thought_signature else None,
            )

        if "text" in content:
            return genai.types.Part(text=content["text"])

        if "toolResult" in content:
            tool_result = content["toolResult"]
            tool_use_id = str(tool_result["toolUseId"]) if tool_result["toolUseId"] else None
            return genai.types.Part(
                function_response=genai.types.FunctionResponse(
                    id=tool_result["toolUseId"],
                    name=tool_use_id,
                    response={
                        "output": [
                            (
                                tool_result_content
                                if "json" in tool_result_content
                                else self._format_request_content_part(
                                    cast(ContentBlock, tool_result_content)
                                ).to_json_dict()
                            )
                            for tool_result_content in tool_result["content"]
                        ],
                    },
                ),
            )

        if "toolUse" in content:
            return genai.types.Part(
                function_call=genai.types.FunctionCall(
                    args=content["toolUse"]["input"],
                    id=content["toolUse"]["toolUseId"],
                    name=content["toolUse"]["name"],
                ),
            )

        raise TypeError(f"content_type=<{next(iter(content))}> | unsupported type")

    def _format_request_content(self, messages: Messages) -> list[genai.types.Content]:
        """Format message content into Gemini content instances.

        - Docs: https://googleapis.github.io/python-genai/genai.html#genai.types.Content

        Args:
            messages: List of message objects to be processed by the model.

        Returns:
            Gemini content list.
        """
        return [
            genai.types.Content(
                parts=[self._format_request_content_part(content) for content in message["content"]],
                role="user" if message["role"] == "user" else "model",
            )
            for message in messages
        ]

    def _format_request_tools(self, tool_specs: Optional[list[ToolSpec]]) -> Optional[list[genai.types.Tool | Any]]:
        """Format tool specs into Gemini tools.

        - Docs: https://googleapis.github.io/python-genai/genai.html#genai.types.Tool

        Args:
            tool_specs: List of tool specifications to make available to the model.

        Return:
            Gemini tool list or None if no tools are provided.
        """
        if not tool_specs:
            return None

        return [
            genai.types.Tool(
                function_declarations=[
                    genai.types.FunctionDeclaration(
                        description=tool_spec["description"],
                        name=tool_spec["name"],
                        parameters=genai.types.Schema.model_validate(tool_spec["parameters"]["json"]),
                    )
                    for tool_spec in tool_specs
                ],
            ),
        ]

    def _format_request_tool_config(self, tool_choice: ToolChoice | None) -> Optional[dict[str, Any]]:
        """Format tool choice into Gemini tool_config.

        Args:
            tool_choice: Tool choice configuration.

        Returns:
            Gemini tool_config dict or None.
        """
        if not tool_choice:
            return None

        match tool_choice:
            case {"auto": _}:
                return {"function_calling_config": {"mode": "AUTO"}}
            case {"any": _}:
                return {"function_calling_config": {"mode": "ANY"}}
            case {"tool": {"name": tool_name}}:
                return {"function_calling_config": {"mode": "ANY", "allowed_function_names": [tool_name]}}
            case _:
                return {"function_calling_config": {"mode": "AUTO"}}

    def _format_request_config(
        self,
        tool_specs: Optional[list[ToolSpec]],
        system_prompt: Optional[str],
        params: Optional[dict[str, Any]],
        tool_choice: ToolChoice | None = None,
    ) -> genai.types.GenerateContentConfig:
        """Format Gemini request config.

        - Docs: https://googleapis.github.io/python-genai/genai.html#genai.types.GenerateContentConfig

        Args:
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            params: Additional model parameters (e.g., temperature).
            tool_choice: Selection strategy for tool invocation.

        Returns:
            Gemini request config.
        """
        config_dict = {
            "system_instruction": system_prompt,
            "tools": self._format_request_tools(tool_specs),
            **(params or {}),
        }

        # Add tool_config if tool_choice is specified and we have tools
        if tool_choice and tool_specs:
            tool_config = self._format_request_tool_config(tool_choice)
            if tool_config:
                config_dict["tool_config"] = tool_config

        return genai.types.GenerateContentConfig(**config_dict)

    def _format_request(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]],
        system_prompt: Optional[str],
        params: Optional[dict[str, Any]],
        tool_choice: ToolChoice | None = None,
    ) -> dict[str, Any]:
        """Format a Gemini streaming request.

        - Docs: https://ai.google.dev/api/generate-content#endpoint_1

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            params: Additional model parameters (e.g., temperature).
            tool_choice: Selection strategy for tool invocation.

        Returns:
            A Gemini streaming request.
        """
        return {
            "config": self._format_request_config(tool_specs, system_prompt, params, tool_choice).to_json_dict(),
            "contents": [content.to_json_dict() for content in self._format_request_content(messages)],
            "model": self.config["model_id"],
        }

    def _format_response(
        self, response: genai.types.GenerateContentResponse, output_model: Optional[Type[BaseModel]] = None
    ) -> ChatCompletionAssistantMessage:
        """Format the Gemini response into a Spark response."""
        result: ChatCompletionAssistantMessage = {"role": "assistant"}

        if not response.candidates:
            return result

        candidate = response.candidates[0]
        if candidate.finish_reason:
            result["stop_reason"] = candidate.finish_reason.name.lower()

        tool_calls: list[ChatCompletionAssistantToolCall] = []
        content_parts: list[ChatCompletionTextObject] = []
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if part.function_call:
                    result["stop_reason"] = "tool_use"
                    tool_calls.append({
                        "id": str(uuid.uuid4()),  # Gemini doesn't provide a toolUseId, so generate one
                        "type": "function",
                        "function": {
                            "name": part.function_call.name,
                            "arguments": part.function_call.args,
                        },
                    })
                elif part.text:
                    content_parts.append({"type": "text", "text": part.text})

        if tool_calls:
            result["tool_calls"] = tool_calls
        if content_parts:
            if output_model is not None:
                combined_text = "".join(part["text"] for part in content_parts)
                result["content"] = json_repair.repair_json(combined_text)
            else:
                result["content"] = content_parts

        return result

    @override
    async def get_text(
        self,
        messages: Messages,
        system_prompt: Optional[str] = None,
        tool_specs: list[ToolSpec] | None = None,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> ChatCompletionAssistantMessage:
        """Get text output from the model using Gemini's default text generation with caching support.

        Args:
            messages: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            tool_specs: List of tool specifications to make available to the model.
            tool_choice: Selection strategy for tool invocation.
            **kwargs: Additional keyword arguments for future extensibility.

        Returns:
            The text output from the model.
        """
        # Check cache first
        cached_response = self._get_from_cache(
            messages=messages, system_prompt=system_prompt, tool_specs=tool_specs, tool_choice=tool_choice, **kwargs
        )

        if cached_response is not None:
            logger.info("Returning cached response for Gemini model")
            return cached_response

        # Cache miss - call API
        params = {
            **(self.config.get("params") or {}),
        }
        request = self._format_request(messages, tool_specs, system_prompt, params, tool_choice)
        client = genai.Client(**self.client_args)
        response = client.models.generate_content(**request)
        formatted_response = self._format_response(response)

        # Save to cache
        self._save_to_cache(
            messages=messages,
            response=formatted_response,
            system_prompt=system_prompt,
            tool_specs=tool_specs,
            tool_choice=tool_choice,
            **kwargs,
        )

        return formatted_response

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
        """Get JSON output from the model using Gemini's native JSON output with caching support.

        - Docs: https://ai.google.dev/gemini-api/docs/structured-output

        Args:
            output_model: The output model to use for the agent.
            messages: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            tool_specs: List of tool specifications to make available to the model.
            tool_choice: Selection strategy for tool invocation.
            **kwargs: Additional keyword arguments for future extensibility.

        Returns:
            The JSON output from the model.
        """
        # Include output_model schema in cache key
        kwargs_with_model = {**kwargs, "output_model_schema": output_model.model_json_schema()}

        # Check cache first
        cached_response = self._get_from_cache(
            messages=messages,
            system_prompt=system_prompt,
            tool_specs=tool_specs,
            tool_choice=tool_choice,
            **kwargs_with_model,
        )

        if cached_response is not None:
            logger.info("Returning cached response for Gemini model (get_json)")
            return cached_response

        # Cache miss - call API
        params = {
            **(self.config.get("params") or {}),
            "response_mime_type": "application/json",
            "response_schema": output_model.model_json_schema(),
        }
        request = self._format_request(messages, tool_specs, system_prompt, params, tool_choice)
        client = genai.Client(**self.client_args).aio
        response = await client.models.generate_content(**request)
        formatted_response = self._format_response(response, output_model=output_model)

        # Save to cache
        self._save_to_cache(
            messages=messages,
            response=formatted_response,
            system_prompt=system_prompt,
            tool_specs=tool_specs,
            tool_choice=tool_choice,
            **kwargs_with_model,
        )

        return formatted_response
