"""Abstract base class for Spark ADK model providers."""

from abc import ABC, abstractmethod
import logging
import os
from pathlib import Path
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

from spark.models.types import Messages, ChatCompletionAssistantMessage
from spark.tools.types import ToolChoice, ToolSpec

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
ModelType = TypeVar("ModelType", bound="Model")


class Model(ABC):
    """Abstract base class for Agent model providers.

    This class defines the interface for all model implementations in the Strands Agents SDK. It provides a
    standardized way to configure and process requests for different AI model providers.

    Supports optional response caching to avoid redundant API calls.
    """

    def __init__(self):
        """Initialize model with optional cache support."""
        self._cache_manager: Optional[Any] = None
        self._cache_enabled: bool = False
        self._cache_ttl_seconds: int = 86400  # 24 hours default

    def _get_provider_name(self) -> str:
        """Get provider name for cache key generation.

        Returns:
            Provider name string (e.g., "openai", "bedrock", "gemini").
        """
        # Default implementation: derive from class name
        class_name = self.__class__.__name__
        if class_name.endswith("Model"):
            return class_name[:-5].lower()
        return class_name.lower()

    def _init_cache(self, cache_config: Optional[Any] = None) -> None:
        """Initialize cache manager if caching is enabled.

        Args:
            cache_config: Optional CacheConfig instance. If None, uses default config.
        """
        if self._cache_enabled:
            from spark.models.cache import CacheManager, CacheConfig

            config = cache_config or CacheConfig(enabled=True, ttl_seconds=self._cache_ttl_seconds)
            cache_dir_override = os.getenv("SPARK_CACHE_DIR")
            if cache_dir_override:
                config = CacheConfig(
                    enabled=config.enabled,
                    cache_dir=Path(cache_dir_override),
                    ttl_seconds=config.ttl_seconds,
                    max_cache_size_mb=config.max_cache_size_mb,
                    cleanup_interval_seconds=config.cleanup_interval_seconds,
                )
            self._cache_manager = CacheManager.get_instance(config)
            logger.debug(
                "Cache enabled for %s with TTL=%ss (dir=%s)",
                self._get_provider_name(),
                self._cache_ttl_seconds,
                config.cache_dir or "default",
            )

    def _get_from_cache(
        self,
        messages: Messages,
        system_prompt: Optional[str] = None,
        tool_specs: Optional[list[ToolSpec]] = None,
        **kwargs: Any,
    ) -> Optional[ChatCompletionAssistantMessage]:
        """Try to retrieve response from cache.

        Args:
            messages: The messages array
            system_prompt: Optional system prompt
            tool_specs: Optional tool specifications
            **kwargs: Additional parameters

        Returns:
            Cached response if found and not expired, None otherwise.
        """
        if not self._cache_enabled or self._cache_manager is None:
            return None

        try:
            model_id = self.get_config().get("model_id", "unknown")
            cache_key = self._cache_manager.generate_cache_key(
                provider=self._get_provider_name(),
                model_id=model_id,
                messages=messages,
                system_prompt=system_prompt,
                tool_specs=tool_specs,
                **kwargs,
            )

            cached_response = self._cache_manager.get(cache_key=cache_key, provider=self._get_provider_name())

            return cached_response
        except Exception as e:
            logger.warning(f"Error retrieving from cache: {e}")
            return None

    def _save_to_cache(
        self,
        messages: Messages,
        response: ChatCompletionAssistantMessage,
        system_prompt: Optional[str] = None,
        tool_specs: Optional[list[ToolSpec]] = None,
        **kwargs: Any,
    ) -> None:
        """Save response to cache.

        Args:
            messages: The messages array
            response: The response to cache
            system_prompt: Optional system prompt
            tool_specs: Optional tool specifications
            **kwargs: Additional parameters
        """
        if not self._cache_enabled or self._cache_manager is None:
            return

        try:
            model_id = self.get_config().get("model_id", "unknown")
            cache_key = self._cache_manager.generate_cache_key(
                provider=self._get_provider_name(),
                model_id=model_id,
                messages=messages,
                system_prompt=system_prompt,
                tool_specs=tool_specs,
                **kwargs,
            )

            request_data = {
                "messages": messages,
                "system_prompt": system_prompt,
                "tool_specs": tool_specs,
                "kwargs": kwargs,
            }

            self._cache_manager.set(
                cache_key=cache_key,
                provider=self._get_provider_name(),
                model_id=model_id,
                request=request_data,
                response=response,
            )
        except Exception as e:
            logger.warning(f"Error saving to cache: {e}")

    @abstractmethod
    # pragma: no cover
    def update_config(self, **model_config: Any) -> None:
        """Update the model configuration with the provided arguments.

        Args:
            **model_config: Configuration overrides.
        """
        pass

    @abstractmethod
    # pragma: no cover
    def get_config(self) -> Any:
        """Return the model configuration.

        Returns:
            The model's configuration.
        """
        pass

    @abstractmethod
    async def get_text(
        self,
        messages: Messages,
        system_prompt: Optional[str] = None,
        tool_specs: list[ToolSpec] | None = None,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> ChatCompletionAssistantMessage:
        """Get the complete text response from the model"""
        pass

    @abstractmethod
    async def get_json(
        self,
        output_model: Type[T],
        messages: Messages,
        system_prompt: Optional[str] = None,
        tool_specs: list[ToolSpec] | None = None,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> ChatCompletionAssistantMessage:
        """Get JSON output from the model.

        Args:
            output_model: The output model to use for the agent.
            messages: The messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            tool_specs: List of tool specifications to make available to the model.
            tool_choice: Selection strategy for tool invocation.
            **kwargs: Additional keyword arguments for future extensibility.
        Raises:
            ValidationException: The response format from the model does not match the output_model
        """
        pass

    def to_spec_dict(self) -> dict[str, Any]:
        """Serialize model to spec-compatible dictionary.

        This enables models to be serialized to JSON specifications
        for bidirectional conversion between Python and JSON.

        Returns:
            Dictionary containing model type, config, and other metadata

        Example:
            spec = model.to_spec_dict()
            # {
            #   "type": "OpenAIModel",
            #   "provider": "openai",
            #   "model_id": "gpt-4o-mini",
            #   "config": {...}
            # }
        """
        config = self.get_config()

        return {
            "type": self.__class__.__name__,
            "provider": self._get_provider_name(),
            "model_id": config.get("model_id") if isinstance(config, dict) else None,
            "config": config
        }

    @classmethod
    def from_spec_dict(cls: Type[ModelType], spec: dict[str, Any]) -> ModelType:
        """Deserialize model from spec dictionary.

        Note: This is a default implementation that should be overridden
        by subclasses for proper deserialization with specific parameters.

        Args:
            spec: Dictionary containing model configuration

        Returns:
            Model instance

        Raises:
            NotImplementedError: If subclass doesn't override this method

        Example:
            spec = {
                "type": "OpenAIModel",
                "model_id": "gpt-4o-mini",
                "config": {...}
            }
            model = OpenAIModel.from_spec_dict(spec)
        """
        raise NotImplementedError(
            f"{cls.__name__}.from_spec_dict() must be implemented by subclass. "
            f"Cannot deserialize model from spec without subclass-specific implementation."
        )
