"""Core tool implementations.

This module provides the base classes for all tool implementations in the SDK, including function-based tools and
Python module-based tools, as well as utilities for validating tool uses and normalizing tool schemas.
"""

import asyncio
import inspect
import logging
import re
from typing import Any, Awaitable, Protocol, Union

from spark.tools.types import BaseTool, ToolResult, ToolSpec, ToolUse, update_tool_runtime_metadata

logger = logging.getLogger(__name__)


class InvalidToolUseNameException(Exception):
    """Exception raised when a tool use has an invalid name."""

    pass


def validate_tool_use(tool: ToolUse) -> None:
    """Validate a tool use request.

    Args:
        tool: The tool use to validate.
    """
    validate_tool_use_name(tool)


def validate_tool_use_name(tool: ToolUse) -> None:
    """Validate the name of a tool use.

    Args:
        tool: The tool use to validate.

    Raises:
        InvalidToolUseNameException: If the tool name is invalid.
    """
    # We need to fix some typing here, because we don't actually expect a ToolUse, but dict[str, Any]
    if "name" not in tool:
        message = "tool name missing"  # type: ignore[unreachable]
        logger.warning(message)
        raise InvalidToolUseNameException(message)

    tool_name = tool["name"]
    tool_name_pattern = r"^[a-zA-Z0-9_\-]{1,}$"
    tool_name_max_length = 64
    valid_name_pattern = bool(re.match(tool_name_pattern, tool_name))
    tool_name_len = len(tool_name)

    if not valid_name_pattern:
        message = f"tool_name=<{tool_name}> | invalid tool name pattern"
        logger.warning(message)
        raise InvalidToolUseNameException(message)

    if tool_name_len > tool_name_max_length:
        message = f"tool_name=<{tool_name}>, tool_name_max_length=<{tool_name_max_length}> | invalid tool name length"
        logger.warning(message)
        raise InvalidToolUseNameException(message)


def _normalize_property(prop_name: str, prop_def: Any) -> dict[str, Any]:
    """Normalize a single property definition.

    Args:
        prop_name: The name of the property.
        prop_def: The property definition to normalize.

    Returns:
        The normalized property definition.
    """
    if not isinstance(prop_def, dict):
        return {"type": "string", "description": f"Property {prop_name}"}

    if prop_def.get("type") == "object" and "properties" in prop_def:
        return normalize_schema(prop_def)  # Recursive call

    # Copy existing property, ensuring defaults
    normalized_prop = prop_def.copy()

    # It is expected that type and description are already included in referenced $def.
    if "$ref" in normalized_prop:
        return normalized_prop

    normalized_prop.setdefault("type", "string")
    normalized_prop.setdefault("description", f"Property {prop_name}")
    return normalized_prop


def normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize a JSON schema to match expectations.

    This function recursively processes nested objects to preserve the complete schema structure.
    Uses a copy-then-normalize approach to preserve all original schema properties.

    Args:
        schema: The schema to normalize.

    Returns:
        The normalized schema.
    """
    # Start with a complete copy to preserve all existing properties
    normalized = schema.copy()

    # Ensure essential structure exists
    normalized.setdefault("type", "object")
    normalized.setdefault("properties", {})
    normalized.setdefault("required", [])

    # Process properties recursively
    if "properties" in normalized:
        properties = normalized["properties"]
        for prop_name, prop_def in properties.items():
            normalized["properties"][prop_name] = _normalize_property(prop_name, prop_def)

    return normalized


def normalize_tool_spec(tool_spec: ToolSpec) -> ToolSpec:
    """Normalize a complete tool specification by transforming its parameters.

    Args:
        tool_spec: The tool specification to normalize.

    Returns:
        The normalized tool specification.
    """
    normalized = tool_spec.copy()

    if "parameters" in normalized:
        if isinstance(normalized["parameters"], dict):
            if "json" in normalized["parameters"]:
                # Schema is already in correct format, just normalize inner schema
                normalized["parameters"]["json"] = normalize_schema(normalized["parameters"]["json"])
            else:
                # Convert direct schema to proper format
                normalized["parameters"] = {"json": normalize_schema(normalized["parameters"])}

    return normalized


class ToolFunc(Protocol):
    """Function signature for Python decorated and module based tools."""

    __name__: str

    def __call__(self, *args: Any, **kwargs: Any) -> Union[ToolResult, Awaitable[ToolResult]]:
        """Function signature for Python decorated and module based tools.

        Returns:
            Tool result or awaitable tool result.
        """
        ...


class PythonAgentTool(BaseTool):
    """Tool implementation for Python-based tools.

    This class handles tools implemented as Python functions, providing a simple interface for executing Python code
    as SDK tools.
    """

    _tool_name: str
    _tool_spec: ToolSpec
    _tool_func: ToolFunc

    def __init__(
        self,
        tool_name: str,
        tool_spec: ToolSpec,
        tool_func: ToolFunc,
        *,
        long_running: bool = False,
        supports_async: bool | None = None,
    ) -> None:
        """Initialize a Python-based tool.

        Args:
            tool_name: Unique identifier for the tool.
            tool_spec: Tool specification defining parameters and behavior.
            tool_func: Python function to execute when the tool is invoked.
        """
        super().__init__()

        self._tool_name = tool_name
        self._tool_spec = tool_spec
        self._tool_func = tool_func
        self._is_async_func = self._detect_async_callable(tool_func)
        self._supports_async_flag = supports_async if supports_async is not None else self._is_async_func

        if self._supports_async_flag:
            self.mark_supports_async()
        if long_running:
            self.mark_long_running()

        update_tool_runtime_metadata(
            self._tool_spec,
            supports_async=self.supports_async if self.supports_async else None,
            long_running=self.is_long_running if self.is_long_running else None,
        )

    @property
    def tool_name(self) -> str:
        """Get the name of the tool.

        Returns:
            The name of the tool.
        """
        return self._tool_name

    @property
    def tool_spec(self) -> ToolSpec:
        """Get the tool specification for this Python-based tool.

        Returns:
            The tool specification.
        """
        return self._tool_spec

    @property
    def supports_hot_reload(self) -> bool:
        """Check if this tool supports automatic reloading when modified.

        Returns:
            Always true for function-based tools.
        """
        return True

    @property
    def tool_type(self) -> str:
        """Identifies this as a Python-based tool implementation.

        Returns:
            "python".
        """
        return "python"

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the underlying tool function with the provided arguments.

        Args:
            *args: Positional arguments to pass to the tool function.
            **kwargs: Keyword arguments to pass to the tool function.

        Returns:
            The result of calling the underlying tool function.
        """
        result = self._tool_func(*args, **kwargs)
        if inspect.isawaitable(result):
            return self._await_result_sync(result)
        return result

    async def acall(self, *args: Any, **kwargs: Any) -> Any:
        """Async entry point that supports both sync and async tool functions."""
        if self._is_async_func:
            result = self._tool_func(*args, **kwargs)
            return await self._ensure_awaitable(result)
        return await asyncio.to_thread(self._tool_func, *args, **kwargs)

    @staticmethod
    def _detect_async_callable(func: ToolFunc) -> bool:
        """Determine whether the provided callable is coroutine-based."""
        if inspect.iscoroutinefunction(func):
            return True
        if hasattr(func, "__call__"):
            return inspect.iscoroutinefunction(func.__call__)
        return False

    @staticmethod
    async def _ensure_awaitable(result: Any) -> Any:
        """Await result if needed (handles coroutine / awaitable)."""
        if inspect.isawaitable(result):
            return await result
        return result

    @staticmethod
    def _await_result_sync(result: Awaitable[Any]) -> Any:
        """Resolve an awaitable from a synchronous context when possible."""

        async def _runner() -> Any:
            return await result

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_runner())
        PythonAgentTool._cleanup_awaitable(result)
        raise RuntimeError(
            "Attempted to invoke async tool synchronously while an event loop is running. "
            "Use 'await tool.acall(...)' instead."
        )

    @staticmethod
    def _cleanup_awaitable(result: Awaitable[Any]) -> None:
        """Best-effort cleanup for awaitables we choose not to await."""
        if asyncio.isfuture(result):
            result.cancel()
            return
        if inspect.iscoroutine(result):
            result.close()
