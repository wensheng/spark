"""Tool-related type definitions for the ADK.

ToolSpec definition follows OpenAI and Gemini to use 'name', 'description', 'parameters'.
Spark adds 'output_schema' to support output validation.
"""

from abc import ABC, abstractmethod
from typing import Any, Literal, Union, cast
from pydantic import BaseModel, ConfigDict


from typing_extensions import NotRequired, TypedDict


class ToolArgsConfig(BaseModel):
    """Config to host free key-value pairs for the args in ToolConfig."""

    model_config = ConfigDict(extra="allow")


class ParametersSpec(TypedDict, extra_items=Any):
    """Schema for tool parameters."""

    type: Literal["object"]
    properties: dict[str, ToolArgsConfig]
    required: list[str]


class ToolRuntimeMetadata(TypedDict, total=False):
    """Spark-specific runtime hints for a tool."""

    supports_async: bool
    long_running: bool


class ToolSpec(TypedDict):
    """Specification for a tool that can be used by an agent.

    Attributes:
        name: The unique name of the tool.
        description: A human-readable description of what the tool does.
        parameters: JSON Schema defining the expected input parameters.
        output_schema: Optional JSON Schema defining the expected output format. Only used by Bedrock
    """

    name: str
    description: str
    parameters: dict[str, Any]
    response_schema: NotRequired[dict]
    x_spark: NotRequired[ToolRuntimeMetadata]


class Tool(TypedDict):
    """A tool that can be provided to a model.

    This type wraps a tool specification for inclusion in a model request.

    Attributes:
        toolSpec: The specification of the tool.
    """

    toolSpec: ToolSpec


class ToolUse(TypedDict):
    """A request from the model to use a specific tool with the provided input.

    Attributes:
        input: The input parameters for the tool.
            Can be any JSON-serializable type.
        name: The name of the tool to invoke.
        toolUseId: A unique identifier for this specific tool use request.
    """

    input: Any
    name: NotRequired[str]
    toolUseId: str


class ToolChoiceAuto(TypedDict):
    """Configuration for automatic tool selection.

    This represents the configuration for automatic tool selection, where the model decides whether and which tool to
    use based on the context.
    """

    pass


class ToolChoiceAny(TypedDict):
    """Configuration indicating that the model must request at least one tool."""

    pass


class ToolChoiceTool(TypedDict):
    """Configuration for forcing the use of a specific tool.

    Attributes:
        name: The name of the tool that the model must use.
    """

    name: str


# Individual ToolChoice type aliases
ToolChoiceAutoDict = dict[Literal["auto"], ToolChoiceAuto]
ToolChoiceAnyDict = dict[Literal["any"], ToolChoiceAny]
ToolChoiceToolDict = dict[Literal["tool"], ToolChoiceTool]

ToolChoice = Union[
    ToolChoiceAutoDict,
    ToolChoiceAnyDict,
    ToolChoiceToolDict,
]
"""
Configuration for how the model should choose tools.

- "auto": The model decides whether to use tools based on the context
- "any": The model must use at least one tool (any tool)
- "tool": The model must use the specified tool
"""


"""Status of a tool execution result."""


class ToolResult(TypedDict):
    """Result of a tool execution.

    Attributes:
        content: List of result content returned by the tool.
        status: The status of the tool execution ("success", "error", or "in_progress").
        toolUseId: The unique identifier of the tool use request that produced this result.
        metadata: Optional implementation-specific metadata (latency, identifiers, etc.).
        started_at: Optional ISO timestamp indicating when execution started.
        completed_at: Optional ISO timestamp indicating when execution completed.
        progress: Optional progress indicator between 0 and 1 for long-running tools.
    """

    content: list
    status: Literal["success", "error", "in_progress"]
    toolUseId: str
    metadata: NotRequired[dict[str, Any]]
    started_at: NotRequired[str]
    completed_at: NotRequired[str]
    progress: NotRequired[float]


class BaseTool(ABC):
    """Abstract base class for all ADK tools.

    This class defines the interface that all tool implementations must follow. Each tool must provide its name,
    specification, and implement a stream method that executes the tool's functionality.
    """

    _is_dynamic: bool
    _supports_async: bool
    _is_long_running: bool

    def __init__(self) -> None:
        """Initialize the base agent tool with default dynamic state."""
        self._is_dynamic = False
        self._supports_async = False
        self._is_long_running = False

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """The unique name of the tool used for identification and invocation."""
        pass

    @property
    @abstractmethod
    def tool_spec(self) -> ToolSpec:
        """Tool specification that describes its functionality and parameters."""
        pass

    @property
    @abstractmethod
    def tool_type(self) -> str:
        """The type of the tool implementation (e.g., 'python', 'javascript', 'lambda').

        Used for categorization and appropriate handling.
        """
        pass

    @property
    def supports_hot_reload(self) -> bool:
        """Whether the tool supports automatic reloading when modified.

        Returns:
            False by default.
        """
        return False

    @property
    def is_dynamic(self) -> bool:
        """Whether the tool was dynamically loaded during runtime.

        Dynamic tools may have different lifecycle management.

        Returns:
            True if loaded dynamically, False otherwise.
        """
        return self._is_dynamic

    def mark_dynamic(self) -> None:
        """Mark this tool as dynamically loaded."""
        self._is_dynamic = True

    @property
    def supports_async(self) -> bool:
        """Whether the tool provides an async execution path."""
        return self._supports_async

    def mark_supports_async(self) -> None:
        """Mark this tool as supporting async execution."""
        self._supports_async = True

    @property
    def is_long_running(self) -> bool:
        """Whether the tool is expected to run for an extended period."""
        return self._is_long_running

    def mark_long_running(self) -> None:
        """Mark this tool as potentially long running."""
        self._is_long_running = True

    def get_display_properties(self) -> dict[str, str]:
        """Get properties to display in UI representations of this tool.

        Subclasses can extend this to include additional properties.

        Returns:
            Dictionary of property names and their string values.
        """
        properties = {
            "Name": self.tool_name,
            "Type": self.tool_type,
        }
        properties["Async"] = "yes" if self.supports_async else "no"
        properties["Long Running"] = "yes" if self.is_long_running else "no"
        return properties

    @abstractmethod
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the tool with the given arguments."""
        pass

    async def acall(self, *args: Any, **kwargs: Any) -> Any:
        """Async entry point for tools; defaults to the synchronous implementation."""
        return self.__call__(*args, **kwargs)


def update_tool_runtime_metadata(
    tool_spec: ToolSpec, *, supports_async: bool | None = None, long_running: bool | None = None
) -> None:
    """Attach Spark runtime metadata flags to a tool specification."""
    if supports_async is None and long_running is None:
        return

    metadata = cast(ToolRuntimeMetadata, tool_spec.setdefault("x_spark", {}))

    if supports_async is not None:
        metadata["supports_async"] = supports_async

    if long_running is not None:
        metadata["long_running"] = long_running
