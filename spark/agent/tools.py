"""Provider-neutral LLM tool contracts."""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from ..core.identity import FrozenHeaders

ToolHandler = Callable[[Mapping[str, Any]], Any | Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A model request to execute one local tool."""

    call_id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=FrozenHeaders)
    raw_arguments: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", FrozenHeaders(self.arguments))


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Result of executing one tool call."""

    call_id: str
    name: str
    output: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class Tool:
    """A local tool the model may request."""

    name: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=lambda: FrozenHeaders({"type": "object"}))
    handler: ToolHandler | None = None
    strict: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", FrozenHeaders(self.parameters))
        normalized_name = self.name.strip()
        if not normalized_name:
            raise ValueError("tool name must not be empty")
        object.__setattr__(self, "name", normalized_name)


@dataclass(frozen=True, slots=True)
class ToolTrace:
    """One model-requested tool call and its execution result, if any."""

    request_id: str
    round_index: int
    call_index: int
    call: ToolCall
    result: ToolResult | None = None


def tool(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    parameters: Mapping[str, Any] | None = None,
    strict: bool = True,
) -> Tool | Callable[[Callable[..., Any]], Tool]:
    """Decorate a regular function into a provider-neutral Tool."""

    def decorate(target: Callable[..., Any]) -> Tool:
        return Tool(
            name=name or target.__name__,
            description=description or inspect.getdoc(target) or target.__name__,
            parameters=parameters or _parameters_from_signature(target),
            handler=_handler_from_function(target),
            strict=strict,
        )

    if func is None:
        return decorate
    return decorate(func)


def _handler_from_function(func: Callable[..., Any]) -> ToolHandler:
    signature = inspect.signature(func)
    for parameter in signature.parameters.values():
        if parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            raise ValueError(f"tool function {func.__name__!r} cannot use variadic parameters")

    def handler(arguments: Mapping[str, Any]) -> Any | Awaitable[Any]:
        return func(**dict(arguments))

    return handler


def _parameters_from_signature(func: Callable[..., Any]) -> dict[str, Any]:
    signature = inspect.signature(func)
    try:
        type_hints = get_type_hints(func)
    except (NameError, TypeError):
        type_hints = {}
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in signature.parameters.values():
        if parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            raise ValueError(f"tool function {func.__name__!r} cannot use variadic parameters")
        properties[parameter.name] = _schema_from_annotation(type_hints.get(parameter.name, parameter.annotation))
        if parameter.default is inspect.Parameter.empty:
            required.append(parameter.name)
        else:
            try:
                json.dumps(parameter.default)
            except TypeError:
                pass
            else:
                properties[parameter.name]["default"] = parameter.default

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _schema_from_annotation(annotation: Any) -> dict[str, Any]:
    if annotation is inspect.Signature.empty or annotation is Any:
        return {}
    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is None or annotation is type(None):
        return {"type": "null"}

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Literal:
        return {"enum": list(args)}
    if origin in {list, tuple, set, frozenset, Sequence}:
        schema: dict[str, Any] = {"type": "array"}
        if args:
            schema["items"] = _schema_from_annotation(args[0])
        return schema
    if origin in {dict, Mapping}:
        return {"type": "object"}
    if origin in {UnionType, Union}:
        variants = [_schema_from_annotation(arg) for arg in args]
        return {"anyOf": variants}
    return {}


class ToolRegistry:
    """Registry and executor for local tools."""

    def __init__(self, tools: Mapping[str, Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = dict(tools or {})

    def register(self, tool: Tool) -> None:
        """Register or replace a local tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Return a tool by name."""
        return self._tools.get(name)

    def list(self) -> tuple[Tool, ...]:
        """Return registered tools."""
        return tuple(self._tools.values())

    async def execute(self, call: ToolCall) -> ToolResult:
        """Execute a tool call and capture errors as ToolResult values."""
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(call_id=call.call_id, name=call.name, output="", error="tool not found")
        if tool.handler is None:
            return ToolResult(call_id=call.call_id, name=call.name, output="", error="tool has no handler")
        try:
            output = tool.handler(call.arguments)
            if inspect.isawaitable(output):
                output = await output
        except Exception as exc:
            return ToolResult(call_id=call.call_id, name=call.name, output="", error=str(exc))
        return ToolResult(call_id=call.call_id, name=call.name, output=self._stringify(output))

    def _stringify(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, sort_keys=True)
        except TypeError:
            return str(value)
