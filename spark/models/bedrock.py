"""AWS Bedrock model provider.
Adapted from Strands-SDK.

- Docs: https://aws.amazon.com/bedrock/
"""

import json
import logging
import os
from textwrap import dedent
import warnings
from typing import (
    Any,
    Literal,
    Optional,
    Type,
    TypedDict,
    TypeVar,
    Unpack,
    cast,
    override,
)

import boto3
from botocore.config import Config as BotocoreConfig
from pydantic import BaseModel
import json_repair

from spark.models.types import (
    ChatCompletionAssistantMessage,
    ChatCompletionAssistantToolCall,
    Message as LlmMessage,
    Messages,
    ContentBlock,
)
from spark.tools.types import ToolChoice, ToolSpec
from spark.models.utils import validate_config_keys
from spark.models.base import Model

logger = logging.getLogger(__name__)

# See: `BedrockModel._get_default_model_with_warning` for why we need both
DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
_DEFAULT_BEDROCK_MODEL_ID = "{}.us.anthropic.claude-sonnet-4-5-20250929-v1:0"
DEFAULT_BEDROCK_REGION = "us-west-2"

BEDROCK_CONTEXT_WINDOW_OVERFLOW_MESSAGES = [
    "Input is too long for requested model",
    "input length and `max_tokens` exceed context limit",
    "too many total text bytes",
]

# Models that should include tool result status (include_tool_result_status = True)
_MODELS_INCLUDE_STATUS = [
    "anthropic.claude",
]

T = TypeVar("T", bound=BaseModel)

DEFAULT_READ_TIMEOUT = 120


class BedrockModel(Model):
    """AWS Bedrock model provider implementation.

    The implementation handles Bedrock-specific features such as:

    - Tool configuration for function calling
    - Guardrails integration
    - Caching points for system prompts and tools
    - Context window overflow detection
    """

    class BedrockConfig(TypedDict, total=False):
        """Configuration options for Bedrock models.

        Attributes:
            additional_args: Any additional arguments to include in the request
            additional_request_fields: Additional fields to include in the Bedrock request
            additional_response_field_paths: Additional response field paths to extract
            cache_prompt: Cache point type for the system prompt
            cache_tools: Cache point type for tools
            guardrail_id: ID of the guardrail to apply
            guardrail_trace: Guardrail trace mode. Defaults to enabled.
            guardrail_version: Version of the guardrail to apply
            guardrail_stream_processing_mode: The guardrail processing mode
            max_tokens: Maximum number of tokens to generate in the response
            model_id: The Bedrock model ID (e.g., "us.anthropic.claude-sonnet-4-20250514-v1:0")
            include_tool_result_status: Flag to include status field in tool results.
                True includes status, False removes status, "auto" determines based on model_id. Defaults to "auto".
            stop_sequences: List of sequences that will stop generation when encountered
            streaming: Flag to enable/disable streaming. Defaults to True.
            temperature: Controls randomness in generation (higher = more random)
            top_p: Controls diversity via nucleus sampling (alternative to temperature)
            enable_cache: Enable response caching (default: False).
            cache_ttl_seconds: Time-to-live for cached responses in seconds (default: 86400 = 24 hours).
        """

        additional_args: Optional[dict[str, Any]]
        additional_request_fields: Optional[dict[str, Any]]
        additional_response_field_paths: Optional[list[str]]
        cache_prompt: Optional[str]
        cache_tools: Optional[str]
        guardrail_id: Optional[str]
        guardrail_trace: Optional[Literal["enabled", "disabled", "enabled_full"]]
        guardrail_stream_processing_mode: Optional[Literal["sync", "async"]]
        guardrail_version: Optional[str]
        max_tokens: Optional[int]
        model_id: str
        include_tool_result_status: Optional[Literal["auto"] | bool]
        stop_sequences: Optional[list[str]]
        streaming: Optional[bool]
        temperature: Optional[float]
        top_p: Optional[float]
        enable_cache: bool
        cache_ttl_seconds: int

    def __init__(
        self,
        *,
        boto_session: Optional[boto3.Session] = None,
        boto_client_config: Optional[BotocoreConfig] = None,
        region_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        **model_config: Unpack[BedrockConfig],
    ):
        """Initialize provider instance.

        Args:
            boto_session: Boto Session to use when calling the Bedrock Model.
            boto_client_config: Configuration to use when creating the Bedrock-Runtime Boto Client.
            region_name: AWS region to use for the Bedrock service.
                Defaults to the AWS_REGION environment variable if set, or "us-west-2" if not set.
            endpoint_url: Custom endpoint URL for VPC endpoints (PrivateLink)
            **model_config: Configuration options for the Bedrock model.
        """
        super().__init__()

        if region_name and boto_session:
            raise ValueError("Cannot specify both `region_name` and `boto_session`.")

        session = boto_session or boto3.Session()
        resolved_region = region_name or session.region_name or os.environ.get("AWS_REGION") or DEFAULT_BEDROCK_REGION
        self.config = BedrockModel.BedrockConfig(
            model_id=BedrockModel._get_default_model_with_warning(resolved_region, model_config),
            include_tool_result_status="auto",
        )
        self.update_config(**model_config)

        # Initialize cache if enabled
        self._cache_enabled = self.config.get("enable_cache", False)
        self._cache_ttl_seconds = self.config.get("cache_ttl_seconds", 86400)
        self._init_cache()

        logger.debug("config=<%s> | initializing", self.config)

        if boto_client_config:
            existing_user_agent = getattr(boto_client_config, "user_agent_extra", None)

            if existing_user_agent:
                new_user_agent = f"{existing_user_agent} spark-agents"
            else:
                new_user_agent = "spark-agents"

            client_config = boto_client_config.merge(BotocoreConfig(user_agent_extra=new_user_agent))
        else:
            client_config = BotocoreConfig(user_agent_extra="spark-agents", read_timeout=DEFAULT_READ_TIMEOUT)

        self.client = session.client(
            service_name="bedrock-runtime",
            config=client_config,
            endpoint_url=endpoint_url,
            region_name=resolved_region,
        )

        logger.debug("region=<%s> | bedrock client created", self.client.meta.region_name)

    @override
    def update_config(self, **model_config: Unpack[BedrockConfig]) -> None:  # type: ignore
        """Update the Bedrock Model configuration with the provided arguments.

        Args:
            **model_config: Configuration overrides.
        """
        validate_config_keys(model_config, self.BedrockConfig)
        self.config.update(model_config)

    @override
    def get_config(self) -> BedrockConfig:
        """Get the current Bedrock Model configuration.

        Returns:
            The Bedrock model configuration.
        """
        return self.config

    def _get_provider_name(self) -> str:
        """Get provider name for cache key generation."""
        return "bedrock"

    def _convert_pydantic_to_content_block(self, model: Type[BaseModel]) -> ContentBlock:
        """Convert a Pydantic model to a Bedrock message content block.

        Bedrock does not have a built-in way to specify output schema like other providers.
        We convert the Pydantic model to a user message.

        Args:
            model: The Pydantic model class to convert.

        Returns:
            A user message content block representing the Pydantic model.
        """
        input_schema = model.model_json_schema()
        model_name = model.__name__
        schema_string = json.dumps(input_schema, indent=2)

        return ContentBlock(text=dedent(f"""
            Please provide a response in a valid JSON format. The JSON object must strictly adhere to the following
            JSON Schema, which defines the structure for a '{model_name}' object.
            Ensure that:
            1.  The output is a single, valid JSON object.
            2.  All required fields (as specified in the 'required' array) are present.
            3.  All field types match the 'type' specified in the schema.
            4.  Field descriptions and validation rules (like 'pattern', 'minimum',
                'maxLength') are respected.

            JSON Schema:
            {schema_string}
        """).strip())

    def format_request(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        tool_choice: ToolChoice | None = None,
        output_model: Type[T] | None = None,
    ) -> dict[str, Any]:
        """Format a Bedrock converse stream request.

        Args:
            messages: List of message objects to be processed by the model.
            tool_specs: List of tool specifications to make available to the model.
            system_prompt: System prompt to provide context to the model.
            tool_choice: Selection strategy for tool invocation.

        Returns:
            A Bedrock converse stream request.
        """
        if output_model is not None:
            block = self._convert_pydantic_to_content_block(output_model)
            messages.append(LlmMessage(role="user", content=[block]))
        return {
            "modelId": self.config["model_id"],
            "messages": self._format_bedrock_messages(messages),
            "system": [
                *([{"text": system_prompt}] if system_prompt else []),
                *([{"cachePoint": {"type": self.config["cache_prompt"]}}] if self.config.get("cache_prompt") else []),
            ],
            **(
                {
                    "toolConfig": {
                        "tools": [
                            *[
                                {
                                    "toolSpec": {
                                        "name": tool_spec["name"],
                                        "description": tool_spec["description"],
                                        "inputSchema": tool_spec["parameters"],
                                    }
                                }
                                for tool_spec in tool_specs
                            ],
                            *(
                                [{"cachePoint": {"type": self.config["cache_tools"]}}]
                                if self.config.get("cache_tools")
                                else []
                            ),
                        ],
                        **({"toolChoice": tool_choice if tool_choice else {"auto": {}}}),
                    }
                }
                if tool_specs
                else {}
            ),
            **(
                {"additionalModelRequestFields": self.config["additional_request_fields"]}
                if self.config.get("additional_request_fields")
                else {}
            ),
            **(
                {"additionalModelResponseFieldPaths": self.config["additional_response_field_paths"]}
                if self.config.get("additional_response_field_paths")
                else {}
            ),
            **(
                {
                    "guardrailConfig": {
                        "guardrailIdentifier": self.config["guardrail_id"],
                        "guardrailVersion": self.config["guardrail_version"],
                        "trace": self.config.get("guardrail_trace", "enabled"),
                        **(
                            {"streamProcessingMode": self.config.get("guardrail_stream_processing_mode")}
                            if self.config.get("guardrail_stream_processing_mode")
                            else {}
                        ),
                    }
                }
                if self.config.get("guardrail_id") and self.config.get("guardrail_version")
                else {}
            ),
            "inferenceConfig": {
                key: value
                for key, value in [
                    ("maxTokens", self.config.get("max_tokens")),
                    ("temperature", self.config.get("temperature")),
                    ("topP", self.config.get("top_p")),
                    ("stopSequences", self.config.get("stop_sequences")),
                ]
                if value is not None
            },
            **(
                self.config["additional_args"]
                if "additional_args" in self.config and self.config["additional_args"] is not None
                else {}
            ),
        }

    def _format_bedrock_messages(self, messages: Messages) -> list[dict[str, Any]]:
        """Format messages for Bedrock API compatibility.

        This function ensures messages conform to Bedrock's expected format by:
        - Filtering out SDK_UNKNOWN_MEMBER content blocks
        - Eagerly filtering content blocks to only include Bedrock-supported fields
        - Ensuring all message content blocks are properly formatted for the Bedrock API

        Args:
            messages: List of messages to format

        Returns:
            Messages formatted for Bedrock API compatibility

        Note:
            Unlike other APIs that ignore unknown fields, Bedrock only accepts a strict
            subset of fields for each content block type and throws validation exceptions
            when presented with unexpected fields. Therefore, we must eagerly filter all
            content blocks to remove any additional fields before sending to Bedrock.
            https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ContentBlock.html
        """
        cleaned_messages: list[dict[str, Any]] = []

        filtered_unknown_members = False
        dropped_deepseek_reasoning_content = False

        for message in messages:
            cleaned_content: list[dict[str, Any]] = []

            for content_block in message["content"]:
                # Filter out SDK_UNKNOWN_MEMBER content blocks
                if "SDK_UNKNOWN_MEMBER" in content_block:
                    filtered_unknown_members = True
                    continue

                # DeepSeek models have issues with reasoningContent
                # TODO: Replace with systematic model configuration registry
                # (https://github.com/strands-agents/sdk-python/issues/780)
                if "deepseek" in self.config["model_id"].lower() and "reasoningContent" in content_block:
                    dropped_deepseek_reasoning_content = True
                    continue

                # Format content blocks for Bedrock API compatibility
                formatted_content = self._format_request_message_content(content_block)
                cleaned_content.append(formatted_content)

            # Create new message with cleaned content (skip if empty)
            if cleaned_content:
                cleaned_messages.append({"content": cleaned_content, "role": message["role"]})

        if filtered_unknown_members:
            logger.warning(
                "Filtered out SDK_UNKNOWN_MEMBER content blocks from messages, consider upgrading boto3 version"
            )
        if dropped_deepseek_reasoning_content:
            logger.debug(
                "Filtered DeepSeek reasoningContent content blocks from messages -"
                " https://api-docs.deepseek.com/guides/reasoning_model#multi-round-conversation"
            )

        return cleaned_messages

    def _should_include_tool_result_status(self) -> bool:
        """Determine whether to include tool result status based on current config."""
        include_status = self.config.get("include_tool_result_status", "auto")

        if include_status is True:
            return True
        if include_status is False:
            return False
        return any(model in self.config["model_id"] for model in _MODELS_INCLUDE_STATUS)

    def _format_request_message_content(self, content: ContentBlock) -> dict[str, Any]:
        """Format a Bedrock content block.

        Bedrock strictly validates content blocks and throws exceptions for unknown fields.
        This function extracts only the fields that Bedrock supports for each content type.

        Args:
            content: Content block to format.

        Returns:
            Bedrock formatted content block.

        Raises:
            TypeError: If the content block type is not supported by Bedrock.
        """
        # https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_CachePointBlock.html
        if "cachePoint" in content:
            return {"cachePoint": {"type": content["cachePoint"]["type"]}}

        # https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_DocumentBlock.html
        if "document" in content:
            document = content["document"]
            result: dict[str, Any] = {}

            # Handle required fields (all optional due to total=False)
            if "name" in document:
                result["name"] = document["name"]
            if "format" in document:
                result["format"] = document["format"]

            # Handle source
            if "source" in document:
                result["source"] = {"bytes": document["source"]["bytes"]}

            # Handle optional fields
            if "context" in document:
                result["context"] = document["context"]

            return {"document": result}

        # https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_GuardrailConverseContentBlock.html
        if "guardContent" in content:
            guard = content["guardContent"]
            guard_text = guard["text"]
            result = {"text": {"text": guard_text["text"], "qualifiers": guard_text["qualifiers"]}}
            return {"guardContent": result}

        # https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ImageBlock.html
        if "image" in content:
            image = content["image"]
            source = image["source"]
            formatted_source = {}
            if "bytes" in source:
                formatted_source = {"bytes": source["bytes"]}
            result = {"format": image["format"], "source": formatted_source}
            return {"image": result}

        # https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ReasoningContentBlock.html
        if "reasoningContent" in content:
            reasoning = content["reasoningContent"]
            result = {}

            if "reasoningText" in reasoning:
                reasoning_text = reasoning["reasoningText"]
                result["reasoningText"] = {}
                if "text" in reasoning_text:
                    result["reasoningText"]["text"] = reasoning_text["text"]
                # Only include signature if truthy (avoid empty strings)
                if reasoning_text.get("signature"):
                    result["reasoningText"]["signature"] = reasoning_text["signature"]

            if "redactedContent" in reasoning:
                result["redactedContent"] = reasoning["redactedContent"]

            return {"reasoningContent": result}

        # Pass through text and other simple content types
        if "text" in content:
            return {"text": content["text"]}

        # https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolResultBlock.html
        if "toolResult" in content:
            tool_result = content["toolResult"]
            formatted_content: list[dict[str, Any]] = []
            for tool_result_content in tool_result["content"]:
                if "json" in tool_result_content:
                    # Handle json field since not in ContentBlock but valid in ToolResultContent
                    formatted_content.append({"json": tool_result_content["json"]})
                else:
                    formatted_content.append(
                        self._format_request_message_content(cast(ContentBlock, tool_result_content))
                    )

            result = {
                "content": formatted_content,
                "toolUseId": tool_result["toolUseId"],
            }
            if "status" in tool_result and self._should_include_tool_result_status():
                result["status"] = tool_result["status"]
            return {"toolResult": result}

        # https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolUseBlock.html
        if "toolUse" in content:
            tool_use = content["toolUse"]
            return {
                "toolUse": {
                    "input": tool_use["input"],
                    "name": tool_use["name"],
                    "toolUseId": tool_use["toolUseId"],
                }
            }

        # https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_VideoBlock.html
        if "video" in content:
            video = content["video"]
            source = video["source"]
            formatted_source = {}
            if "bytes" in source:
                formatted_source = {"bytes": source["bytes"]}
            result = {"format": video["format"], "source": formatted_source}
            return {"video": result}

        # https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_CitationsContentBlock.html
        # if "citationsContent" in content:
        #     WONT DO

        raise TypeError(f"content_type=<{next(iter(content))}> | unsupported type")

    def _has_blocked_guardrail(self, guardrail_data: dict[str, Any]) -> bool:
        """Check if guardrail data contains any blocked policies.

        Args:
            guardrail_data: Guardrail data from trace information.

        Returns:
            True if any blocked guardrail is detected, False otherwise.
        """
        input_assessment = guardrail_data.get("inputAssessment", {})
        output_assessments = guardrail_data.get("outputAssessments", {})

        # Check input assessments
        if any(self._find_detected_and_blocked_policy(assessment) for assessment in input_assessment.values()):
            return True

        # Check output assessments
        if any(self._find_detected_and_blocked_policy(assessment) for assessment in output_assessments.values()):
            return True

        return False

    def _find_detected_and_blocked_policy(self, inputs: Any) -> bool:
        """Recursively checks if the assessment contains a detected and blocked guardrail.

        Args:
            input: The assessment to check.

        Returns:
            True if the input contains a detected and blocked guardrail, False otherwise.

        """
        # Check if input is a dictionary
        if isinstance(inputs, dict):
            # Check if current dictionary has action: BLOCKED and detected: true
            if (
                inputs.get("action") == "BLOCKED"
                and inputs.get("detected")
                and isinstance(inputs.get("detected"), bool)
            ):
                return True

            # Recursively check all values in the dictionary
            for value in inputs.values():
                if isinstance(value, dict):
                    return self._find_detected_and_blocked_policy(value)
                # Handle case where value is a list of dictionaries
                if isinstance(value, list):
                    for item in value:
                        return self._find_detected_and_blocked_policy(item)
        elif isinstance(inputs, list):
            # Handle case where input is a list of dictionaries
            for item in inputs:
                return self._find_detected_and_blocked_policy(item)
        # Otherwise return False
        return False

    @staticmethod
    def _get_default_model_with_warning(region_name: str, model_config: Optional[BedrockConfig] = None) -> str:
        """Get the default Bedrock modelId based on region.

        If the region is not **known** to support inference then we show a helpful warning
        that compliments the exception that Bedrock will throw.
        If the customer provided a model_id in their config or they overrode the `DEFAULT_BEDROCK_MODEL_ID`
        then we should not process further.

        Args:
            region_name (str): region for bedrock model
            model_config (Optional[dict[str, Any]]): Model Config that caller passes in on init
        """
        if DEFAULT_BEDROCK_MODEL_ID != _DEFAULT_BEDROCK_MODEL_ID.format("us"):
            return DEFAULT_BEDROCK_MODEL_ID

        model_config = model_config or {}
        if model_config.get("model_id"):
            return model_config["model_id"]

        prefix_inference_map = {"ap": "apac"}  # some inference endpoints can be a bit different than the region prefix

        prefix = "-".join(region_name.split("-")[:-2]).lower()  # handles `us-east-1` or `us-gov-east-1`
        if prefix not in {"us", "eu", "ap", "us-gov"}:
            warnings.warn(
                f"""
            ================== WARNING ==================

                This region {region_name} does not support
                our default inference endpoint: {_DEFAULT_BEDROCK_MODEL_ID.format(prefix)}.
                Update the agent to pass in a 'model_id' like so:
                ```
                Agent(..., model='valid_model_id', ...)
                ````
                Documentation: https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html

            ==================================================
            """,
                stacklevel=2,
            )

        return _DEFAULT_BEDROCK_MODEL_ID.format(prefix_inference_map.get(prefix, prefix))

    def _format_response(
        self, response: dict[str, Any], output_model: Type[BaseModel] | None = None
    ) -> ChatCompletionAssistantMessage:
        """Format the Bedrock response into a Spark response."""
        # Defensive: default assistant message
        result: ChatCompletionAssistantMessage = {"role": "assistant"}

        # Extract stop reason
        result["stop_reason"] = response.get("stopReason")

        # Extract content blocks from response
        content_blocks = response.get("output", {}).get("message", {}).get("content", [])

        # Collect text content
        text_parts: list[str] = []
        tool_calls: list[ChatCompletionAssistantToolCall] = []

        for content in content_blocks:
            if "text" in content:
                text_parts.append(content["text"])
            elif "toolUse" in content:
                tool_use = content["toolUse"]
                tool_calls.append({
                    "id": tool_use.get("toolUseId"),
                    "type": "function",
                    "function": {
                        "name": tool_use.get("name"),
                        "arguments": tool_use.get("input", {}),
                    },
                })

        # Set content if there's any text
        if text_parts:
            combined_text = "".join(text_parts)
            if output_model is not None:
                combined_text = json_repair.repair_json(combined_text)
            result["content"] = combined_text

        # Set tool_calls if there are any
        if tool_calls:
            result["tool_calls"] = tool_calls

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
        """
        # Check cache first
        cached_response = self._get_from_cache(
            messages=messages, system_prompt=system_prompt, tool_specs=tool_specs, tool_choice=tool_choice, **kwargs
        )

        if cached_response is not None:
            logger.info("Returning cached response for Bedrock model")
            return cached_response

        # Cache miss - call API
        specs = tool_specs or []
        tool_choice = kwargs.get('tool_choice')
        request = self.format_request(
            messages=messages,
            tool_specs=specs,
            system_prompt=system_prompt,
            tool_choice=tool_choice,
        )
        response = self.client.converse(**request)
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
        """Get JSON output from the model with caching support.

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
            logger.info("Returning cached response for Bedrock model (get_json)")
            return cached_response

        # Cache miss - call API
        specs = tool_specs or []
        tool_choice = kwargs.get('tool_choice')
        request = self.format_request(messages, specs, system_prompt, tool_choice, output_model)
        response = self.client.converse(**request)
        formatted_response = self._format_response(response, output_model)

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
