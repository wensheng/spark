"""Async execution utilities for ADK tools."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Optional, Tuple

from spark.tools.registry import ToolRegistry
from spark.tools.types import BaseTool, ToolResult, ToolUse
from spark.tools.tools import validate_tool_use

logger = logging.getLogger(__name__)


def _utc_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ToolExecutionConfig:
    """Runtime settings for tool execution."""

    default_timeout: Optional[float] = None
    max_concurrency: Optional[int] = 32
    capture_timestamps: bool = True


class ToolCallExecutor:
    """Dispatch and monitor tool executions for agent tool calls."""

    def __init__(
        self,
        registry: ToolRegistry,
        config: Optional[ToolExecutionConfig] = None,
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self._registry = registry
        self._config = config or ToolExecutionConfig()
        self._loop = loop
        self._semaphore = (
            asyncio.Semaphore(self._config.max_concurrency)
            if self._config.max_concurrency and self._config.max_concurrency > 0
            else None
        )

    async def execute_tool_use(
        self,
        tool_use: ToolUse,
        invocation_state: Optional[dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> ToolResult:
        """Execute a tool call request."""
        validate_tool_use(tool_use)
        invocation_state = invocation_state or {}
        tool_name = tool_use["name"]
        tool = self._registry.get_tool(tool_name)

        started_at = _utc_iso()
        started_monotonic = time.perf_counter()
        timeout_value = timeout if timeout is not None else self._config.default_timeout

        logger.info("tool_name=<%s> | starting execution", tool_name)

        try:
            run_coro = self._invoke_with_prepared_args(tool, tool_use, invocation_state)
            if self._semaphore:
                async with self._semaphore:
                    raw_result = await self._run_with_timeout(run_coro, timeout_value)
            else:
                raw_result = await self._run_with_timeout(run_coro, timeout_value)

            result = self._finalize_result(raw_result, tool_use, started_at, started_monotonic)
            logger.info(
                "tool_name=<%s>, status=<%s>, duration_ms=<%s> | execution finished",
                tool_name,
                result["status"],
                result.get("metadata", {}).get("duration_ms"),
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("tool_name=<%s>, timeout=<%s> | execution timed out", tool_name, timeout_value)
            return self._build_timeout_result(tool_use, started_at, started_monotonic, timeout_value)
        except Exception as exc:  # pragma: no cover - unexpected errors logged and normalized
            logger.exception("tool_name=<%s> | execution failed", tool_name)
            return self._build_error_result(tool_use, started_at, started_monotonic, exc)

    async def _run_with_timeout(self, coro: Awaitable[Any], timeout: Optional[float]) -> Any:
        if timeout is None:
            return await coro
        return await asyncio.wait_for(coro, timeout)

    async def _invoke_with_prepared_args(
        self,
        tool: BaseTool,
        tool_use: ToolUse,
        invocation_state: dict[str, Any],
    ) -> Any:
        args, kwargs = self._prepare_call_arguments(tool, tool_use, invocation_state)
        if tool.supports_async:
            return await tool.acall(*args, **kwargs)
        return await asyncio.to_thread(tool, *args, **kwargs)

    def _prepare_call_arguments(
        self,
        tool: BaseTool,
        tool_use: ToolUse,
        invocation_state: dict[str, Any],
    ) -> Tuple[Tuple[Any, ...], dict[str, Any]]:
        prepare_method = getattr(tool, "prepare_tool_kwargs", None)
        if callable(prepare_method):
            kwargs = prepare_method(tool_use, invocation_state)
            return (), kwargs

        payload = tool_use.get("input")

        if isinstance(payload, dict):
            return (), dict(payload)
        if payload is None:
            return (), {}
        if isinstance(payload, (list, tuple)):
            return tuple(payload), {}
        return (payload,), {}

    def _finalize_result(
        self,
        raw_result: Any,
        tool_use: ToolUse,
        started_at: str,
        started_monotonic: float,
    ) -> ToolResult:
        normalized = self._normalize_result(raw_result, tool_use["toolUseId"])

        if self._config.capture_timestamps:
            normalized.setdefault("started_at", started_at)
            normalized.setdefault("completed_at", _utc_iso())

        duration_ms = int((time.perf_counter() - started_monotonic) * 1000)
        metadata = normalized.setdefault("metadata", {})
        metadata.setdefault("duration_ms", duration_ms)
        metadata.setdefault("tool_name", tool_use["name"])

        return normalized

    def _build_timeout_result(
        self,
        tool_use: ToolUse,
        started_at: str,
        started_monotonic: float,
        timeout_value: Optional[float],
    ) -> ToolResult:
        return {
            "toolUseId": tool_use["toolUseId"],
            "status": "error",
            "content": [{
                "text": (
                    f"Tool '{tool_use['name']}' timed out" + (f" after {timeout_value:.2f}s" if timeout_value else "")
                ),
            }],
            "started_at": started_at,
            "completed_at": _utc_iso(),
            "metadata": {
                "reason": "timeout",
                "duration_ms": int((time.perf_counter() - started_monotonic) * 1000),
                "tool_name": tool_use["name"],
            },
        }

    def _build_error_result(
        self,
        tool_use: ToolUse,
        started_at: str,
        started_monotonic: float,
        exc: Exception,
    ) -> ToolResult:
        return {
            "toolUseId": tool_use["toolUseId"],
            "status": "error",
            "content": [{"text": f"Tool '{tool_use['name']}' failed: {exc}"}],
            "started_at": started_at,
            "completed_at": _utc_iso(),
            "metadata": {
                "reason": "exception",
                "duration_ms": int((time.perf_counter() - started_monotonic) * 1000),
                "tool_name": tool_use["name"],
            },
        }

    def _normalize_result(self, raw_result: Any, tool_use_id: str) -> ToolResult:
        if isinstance(raw_result, dict) and {"content", "status"}.issubset(raw_result.keys()):
            result = dict(raw_result)
            result.setdefault("toolUseId", tool_use_id)
            content = result.get("content")
            if not isinstance(content, list):
                result["content"] = [content]
            return result  # type: ignore[return-value]

        message = raw_result if isinstance(raw_result, str) else repr(raw_result)
        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": message}],
        }
