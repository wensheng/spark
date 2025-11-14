"""OpenAI model provider.

- Docs: https://platform.openai.com/docs/overview
"""

import base64
import json
import logging
import mimetypes
from typing import Any, Optional, Protocol, Required, Type, TypedDict, TypeVar, cast

import openai
from openai.types.chat import ChatCompletion, ParsedChoice
from openai.types.chat.parsed_chat_completion import ParsedChatCompletion
from pydantic import BaseModel
from typing_extensions import Unpack, override

from spark.models.exceptions import ContextWindowOverflowException, ModelThrottledException
from spark.models.types import (
    ChatCompletionAssistantToolCall,
    ChatCompletionAssistantMessage,
    ContentBlock,
    Messages,
)
from spark.tools.types import ToolChoice, ToolSpec
from spark.models.base import Model
from spark.models.types import ToolUse, LlmToolResult
from spark.models.utils import validate_config_keys

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class Client(Protocol):
    """Protocol defining the OpenAI-compatible interface for the underlying provider client."""

    @property
    # pragma: no cover
    def chat(self) -> Any:
        """Chat completions interface."""
        ...


class OpenAIModel(Model):
    """OpenAI model provider implementation."""

    client: Client

    class OpenAIConfig(TypedDict, total=False):
        """Configuration options for OpenAI models.

        Attributes:
            model_id: Model ID (e.g., "gpt-4o").
                For a complete list of supported models, see https://platform.openai.com/docs/models.
            params: Model parameters (e.g., max_tokens).
                For a complete list of supported parameters, see
                https://platform.openai.com/docs/api-reference/chat/create.
            enable_cache: Enable response caching (default: False).
            cache_ttl_seconds: Time-to-live for cached responses in seconds (default: 86400 = 24 hours).
        """

        model_id: Required[str]
        params: Optional[dict[str, Any]]
        enable_cache: bool
        cache_ttl_seconds: int

    def __init__(self, client_args: Optional[dict[str, Any]] = None, **model_config: Unpack[OpenAIConfig]) -> None:
        """Initialize provider instance.

        Args:
            client_args: Arguments for the OpenAI client.
                For a complete list of supported arguments, see https://pypi.org/project/openai/.
            **model_config: Configuration options for the OpenAI model.
        """
        super().__init__()
        validate_config_keys(model_config, self.OpenAIConfig)
        self.config = dict(model_config)
        self.client_args = client_args or {}

        # Initialize cache if enabled
        self._cache_enabled = bool(self.config.get("enable_cache", False))
        cache_ttl = self.config.get("cache_ttl_seconds", 86400)
        self._cache_ttl_seconds = int(cache_ttl) if isinstance(cache_ttl, (int, str, float)) else 86400
        self._init_cache()

        logger.debug("config=<%s> | initializing", self.config)

    def _get_provider_name(self) -> str:
        """Get provider name for cache key generation."""
        return "openai"

    @override
    def update_config(self, **model_config: Unpack[OpenAIConfig]) -> None:  # type: ignore[override]
        """Update the OpenAI model configuration with the provided arguments.

        Args:
            **model_config: Configuration overrides.
        """
        validate_config_keys(model_config, self.OpenAIConfig)
        self.config.update(model_config)

    @override
    def get_config(self) -> OpenAIConfig:
        """Get the OpenAI model configuration.

        Returns:
            The OpenAI model configuration.
        """
        return cast(OpenAIModel.OpenAIConfig, self.config)

    @classmethod
    def format_request_message_content(cls, content: ContentBlock) -> Optional[dict[str, Any]]:
        """Format an OpenAI compatible content block.

        Args:
            content: Message content.

        Returns:
            OpenAI compatible content block.

        Raises:
            TypeError: If the content block type cannot be converted to an OpenAI-compatible format.
        """
        if "document" in content:
            mime_type = mimetypes.types_map.get(f".{content['document']['format']}", "application/octet-stream")
            file_data = base64.b64encode(content["document"]["source"]["bytes"]).decode("utf-8")
            return {
                "file": {
                    "file_data": f"data:{mime_type};base64,{file_data}",
                    "filename": content["document"]["name"],
                },
                "type": "file",
            }

        if "image" in content:
            mime_type = mimetypes.types_map.get(f".{content['image']['format']}", "application/octet-stream")
            image_data = base64.b64encode(content["image"]["source"]["bytes"]).decode("utf-8")

            return {
                "image_url": {
                    "detail": "auto",
                    "format": mime_type,
                    "url": f"data:{mime_type};base64,{image_data}",
                },
                "type": "image_url",
            }

        if "text" in content:
            return {"text": content["text"], "type": "text"}

        # raise TypeError(f"content_type=<{next(iter(content))}> | unsupported type")
        return None

    @classmethod
    def format_request_message_tool_call(cls, tool_use: ToolUse) -> dict[str, Any]:
        """Format an OpenAI compatible tool call.

        Args:
            tool_use: Tool use requested by the model.

        Returns:
            OpenAI compatible tool call.
        """
        return {
            "function": {
                "arguments": json.dumps(tool_use["input"]),
                "name": tool_use["name"],
            },
            "id": tool_use["toolUseId"],
            "type": "function",
        }

    @classmethod
    def format_request_tool_message(cls, tool_result: LlmToolResult) -> dict[str, Any]:
        """Format an OpenAI compatible tool message.

        Args:
            tool_result: Tool result collected from a tool execution.

        Returns:
            OpenAI compatible tool message.
        """
        contents = cast(
            list[ContentBlock],
            [
                {"text": json.dumps(content["json"])} if "json" in content else content
                for content in tool_result["content"]
            ],
        )
        formatted_contents = [cls.format_request_message_content(content) for content in contents]
        content = [a for a in formatted_contents if a]

        return {
            "role": "tool",
            "tool_call_id": tool_result["toolUseId"],
            "content": content,
        }

    @classmethod
    def _format_request_tool_choice(cls, tool_choice: ToolChoice | None) -> dict[str, Any]:
        """Format a tool choice for OpenAI compatibility.

        Args:
            tool_choice: Tool choice configuration in Bedrock format.

        Returns:
            OpenAI compatible tool choice format.
        """
        if not tool_choice:
            return {}

        match tool_choice:
            case {"auto": _}:
                return {"tool_choice": "auto"}  # OpenAI SDK doesn't define constants for these values
            case {"any": _}:
                return {"tool_choice": "required"}
            case {"tool": {"name": tool_name}}:
                return {"tool_choice": {"type": "function", "function": {"name": tool_name}}}
            case _:
                # This should not happen with proper typing, but handle gracefully
                return {"tool_choice": "auto"}

    @classmethod
    def format_request_messages(cls, messages: Messages, system_prompt: Optional[str] = None) -> list[dict[str, Any]]:
        """Format an OpenAI compatible messages array.

        Args:
            messages: List of message objects to be processed by the model.
            system_prompt: System prompt to provide context to the model.

        Returns:
            An OpenAI compatible messages array.
        """
        formatted_messages: list[dict[str, Any]]
        formatted_messages = [{"role": "system", "content": system_prompt}] if system_prompt else []

        for message in messages:
            contents = message["content"]

            formatted_contents = [
                cls.format_request_message_content(content)
                for content in contents
                if any(block_type in content for block_type in ["text", "document", "image"])
            ]
            formatted_tool_calls = [
                cls.format_request_message_tool_call(content["toolUse"]) for content in contents if "toolUse" in content
            ]
            formatted_tool_messages = [
                cls.format_request_tool_message(content["toolResult"])
                for content in contents
                if "toolResult" in content
            ]

            formatted_message = {
                "role": message["role"],
                "content": formatted_contents,
                **({"tool_calls": formatted_tool_calls} if formatted_tool_calls else {}),
            }
            formatted_messages.append(formatted_message)
            formatted_messages.extend(formatted_tool_messages)

        return [message for message in formatted_messages if message["content"] or "tool_calls" in message]

    def format_request(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        tool_choice: ToolChoice | None = None,
        stream: bool = True,
    ) -> dict[str, Any]:
        """Format an OpenAI compatible chat streaming request.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            tool_choice: Selection strategy for tool invocation.

        Returns:
            An OpenAI compatible chat streaming request.

        Raises:
            TypeError: If a message contains a content block type that cannot be converted to an OpenAI-compatible
                format.
        """
        return {
            "messages": self.format_request_messages(messages, system_prompt),
            "model": self.config["model_id"],
            "stream": stream,
            "stream_options": {"include_usage": True} if stream else None,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool_spec["name"],
                        "description": tool_spec["description"],
                        "parameters": tool_spec["parameters"]["json"],
                    },
                }
                for tool_spec in tool_specs or []
            ],
            **(self._format_request_tool_choice(tool_choice)),
            **cast(dict[str, Any], self.config.get("params", {})),
        }

    def _format_response(self, response: ChatCompletion) -> ChatCompletionAssistantMessage:
        # Defensive: default assistant message
        result: ChatCompletionAssistantMessage = {"role": "assistant"}

        if not response.choices:
            return result

        choice = response.choices[0]
        message = choice.message

        # Normalize stop reason for framework consistency
        # OpenAI returns 'tool_calls' when tools are requested; Spark expects 'tool_use'
        if choice.finish_reason == "tool_calls":
            result["stop_reason"] = "tool_use"
        else:
            result["stop_reason"] = choice.finish_reason
        # Map content (OpenAI returns a string or None)
        if getattr(message, "content", None) is not None:
            result["content"] = cast(Any, message.content)

        # Map tool calls (preferred) or legacy function_call
        tool_calls: list[dict[str, Any]] = []
        if getattr(message, "tool_calls", None):
            for call in cast(Any, message.tool_calls):
                if getattr(call, "type", None) == "function":
                    fn = call.function
                    tool_calls.append({
                        "id": getattr(call, "id", None),
                        "type": "function",
                        "function": {
                            "name": getattr(fn, "name", None),
                            "arguments": json.loads(getattr(fn, "arguments", "") or "{}"),
                        },
                    })

        if tool_calls:
            result["tool_calls"] = cast(Any, tool_calls)

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
        """Get text output from the model with caching support.

        Args:
            messages: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            tool_specs: List of tool specifications to make available to the model.
            tool_choice: Selection strategy for tool invocation.
            **kwargs: Additional keyword arguments for future extensibility.

        Returns:
            The text output from the model.

        Raises:
            ContextWindowOverflowException: If the input exceeds the model's context window.
            ModelThrottledException: If the request is throttled by OpenAI (rate limits).
        """
        # Check cache first
        cached_response = self._get_from_cache(
            messages=messages, system_prompt=system_prompt, tool_specs=tool_specs, tool_choice=tool_choice, **kwargs
        )

        if cached_response is not None:
            logger.info("Returning cached response for OpenAI model")
            return cached_response

        # Cache miss - call API
        request = self.format_request(
            messages, tool_specs=tool_specs, system_prompt=system_prompt, tool_choice=tool_choice, stream=False
        )
        response: ChatCompletion

        async with openai.AsyncOpenAI(**self.client_args) as client:
            try:
                if request["tools"]:
                    response = await client.chat.completions.create(
                        model=self.get_config()["model_id"],
                        messages=request["messages"],
                        tools=request["tools"],
                    )
                else:
                    response = await client.chat.completions.create(
                        model=self.get_config()["model_id"],
                        messages=request["messages"],
                    )
            except openai.BadRequestError as e:
                # Check if this is a context length exceeded error
                if hasattr(e, "code") and e.code == "context_length_exceeded":
                    logger.warning("OpenAI threw context window overflow error")
                    raise ContextWindowOverflowException(str(e)) from e
                # Re-raise other BadRequestError exceptions
                raise
            except openai.RateLimitError as e:
                # All rate limit errors should be treated as throttling, not context overflow
                # Rate limits (including TPM) require waiting/retrying, not context reduction
                logger.warning("OpenAI threw rate limit error")
                raise ModelThrottledException(str(e)) from e

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

    @classmethod
    def _add_additional_properties_false(cls, schema: dict[str, Any]) -> None:
        """Recursively add additionalProperties: false to all object schemas.

        OpenAI's strict mode requires additionalProperties: false at every level of the schema.
        This method modifies the schema in place.

        Args:
            schema: The JSON schema to modify
        """
        if not isinstance(schema, dict):
            return

        # Add additionalProperties: false to object types
        if schema.get("type") == "object":
            schema["additionalProperties"] = False

        # Recursively process properties
        if "properties" in schema and isinstance(schema["properties"], dict):
            for prop_schema in schema["properties"].values():
                if isinstance(prop_schema, dict):
                    cls._add_additional_properties_false(prop_schema)

        # Handle arrays
        if "items" in schema and isinstance(schema["items"], dict):
            cls._add_additional_properties_false(schema["items"])

        # Handle anyOf, allOf, oneOf
        for key in ["anyOf", "allOf", "oneOf"]:
            if key in schema and isinstance(schema[key], list):
                for sub_schema in schema[key]:
                    if isinstance(sub_schema, dict):
                        cls._add_additional_properties_false(sub_schema)

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
        """Get JSON output from the model with caching support."""
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
            logger.info("Returning cached response for OpenAI model (get_json)")
            return cached_response

        # Cache miss - call API
        # Build a non-streaming request similar to get_text
        request = self.format_request(messages, tool_specs=tool_specs, system_prompt=system_prompt, stream=False)

        # When using structured outputs with tools, OpenAI requires tools to be "strict"
        # Add strict: true and additionalProperties: false to all tool functions
        if request["tools"]:
            for tool in request["tools"]:
                if tool["type"] == "function":
                    tool["function"]["strict"] = True
                    # Recursively add additionalProperties: false to all object schemas
                    if "parameters" in tool["function"]:
                        self._add_additional_properties_false(tool["function"]["parameters"])

        # Convert Spark ToolChoice to OpenAI format
        formatted_tool_choice = self._format_request_tool_choice(tool_choice)
        # print('request:', json.dumps(request, indent=2))
        async with openai.AsyncOpenAI(**self.client_args) as client:
            try:
                parse_kwargs: dict[str, Any] = {
                    "model": self.get_config()["model_id"],
                    "messages": request["messages"],
                    "tools": request["tools"],
                    "response_format": output_model,
                }
                if formatted_tool_choice:
                    parse_kwargs["tool_choice"] = formatted_tool_choice["tool_choice"]
                response: ParsedChatCompletion = await client.chat.completions.parse(**parse_kwargs)
            except openai.BadRequestError as e:
                print('error:', e)
                # Check if this is a context length exceeded error
                if hasattr(e, "code") and e.code == "context_length_exceeded":
                    logger.warning("OpenAI threw context window overflow error")
                    raise ContextWindowOverflowException(str(e)) from e
                # Re-raise other BadRequestError exceptions
                raise
            except openai.RateLimitError as e:
                # All rate limit errors should be treated as throttling, not context overflow
                # Rate limits (including TPM) require waiting/retrying, not context reduction
                logger.warning("OpenAI threw rate limit error")
                raise ModelThrottledException(str(e)) from e

        # print('response:', response)
        parsed: T | None = None
        # Find the first choice with tool_calls
        if len(response.choices) > 1:
            raise ValueError("Multiple choices found in the OpenAI response.")

        choice: ParsedChoice | None = None

        for choice in response.choices:
            if isinstance(choice.message.parsed, output_model):
                parsed = choice.message.parsed
                break

        if isinstance(parsed, BaseModel):
            content_json = parsed.model_dump_json()
        else:
            content_json = json.dumps(parsed)
        result: ChatCompletionAssistantMessage = {"role": "assistant"}
        result["content"] = content_json

        # Map tool calls (preferred) or legacy function_call
        tool_calls: list[ChatCompletionAssistantToolCall] = []

        if choice:
            if choice.finish_reason == "tool_calls":
                result["stop_reason"] = "tool_use"
            else:
                result["stop_reason"] = choice.finish_reason
            if choice.message.tool_calls:
                for call in choice.message.tool_calls:
                    if getattr(call, "type", None) == "function":
                        fn = call.function
                        tool_calls.append({
                            "id": getattr(call, "id", None),
                            "type": "function",
                            "function": {
                                "name": getattr(fn, "name", None),
                                "arguments": getattr(fn, "arguments", None),
                            },
                        })

        if tool_calls:
            result["tool_calls"] = tool_calls

        # Save to cache
        self._save_to_cache(
            messages=messages,
            response=result,
            system_prompt=system_prompt,
            tool_specs=tool_specs,
            tool_choice=tool_choice,
            **kwargs_with_model,
        )

        return result

    @classmethod
    def from_spec_dict(cls, spec: dict[str, Any]) -> "OpenAIModel":
        """Deserialize OpenAIModel from spec dictionary.

        Args:
            spec: Dictionary containing model configuration

        Returns:
            OpenAIModel instance

        Example:
            spec = {
                "type": "OpenAIModel",
                "model_id": "gpt-4o-mini",
                "config": {
                    "model_id": "gpt-4o-mini",
                    "params": {"temperature": 0.7}
                }
            }
            model = OpenAIModel.from_spec_dict(spec)
        """
        config = spec.get("config", {})

        # Extract known config fields
        model_config = {}
        if "model_id" in config:
            model_config["model_id"] = config["model_id"]
        if "params" in config:
            model_config["params"] = config["params"]
        if "enable_cache" in config:
            model_config["enable_cache"] = config["enable_cache"]
        if "cache_ttl_seconds" in config:
            model_config["cache_ttl_seconds"] = config["cache_ttl_seconds"]

        # Client args not typically serialized, use defaults
        return cls(**model_config)
