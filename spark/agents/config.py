"""Agent Config"""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Literal, Optional, Any, TypeVar
import logging

from pydantic import BaseModel, ConfigDict, Field, model_validator

from spark.nodes.config import NodeConfig
from spark.models.base import Model
from spark.models.types import Messages
from spark.agents.memory import MemoryConfig

if TYPE_CHECKING:
    from spark.agents.strategies import ReasoningStrategy

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
HookFn = Callable[..., Optional[Awaitable[None]]]


class DefaultOutputSchema(BaseModel):
    """Default output schema for agent responses that allow any fields."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)

    role: str
    content: list[str] = Field(default_factory=list)


class AgentConfig(NodeConfig):
    """Agent Config"""

    model: Model
    name: Optional[str] = None
    description: Optional[str] = None

    system_prompt: str | None = None
    """
    system_prompt: System prompt to guide model behavior.
    If None, the model will behave according to its default settings.
    """

    prompt_template: str | None = None
    """jinja2 format string template for the prompt to use for the agent."""

    preload_messages: Messages = Field(default_factory=list)
    """List of initial messages to pre-load into the conversation.  Defaults to an empty list if Nones"""

    memory_config: MemoryConfig = Field(default_factory=MemoryConfig)
    """Memory config for the agent."""

    output_mode: Literal['json', 'text'] = 'text'
    """Output mode for the agent."""

    output_schema: type[BaseModel] = DefaultOutputSchema
    """
    A pydantic model class (not an instance) that defines the expected structure
    of the agent's output. Defaults to the permissive DefaultOutputSchema.
    Ignored if output_mode is 'text'.
    """

    record_direct_tool_call: bool = True

    hooks: Optional[list[Any]] = None
    """hooks: hooks to be added to the agent hook registry (list of HookProvider instances)"""

    before_llm_hooks: list[HookFn] = Field(default_factory=list)
    """
    before_llm_hooks: hooks to be added before calling the LLM.
    while pre_process_hooks are executed before the process method.
    """

    after_llm_hooks: list[HookFn] = Field(default_factory=list)
    """after_llm_hooks: hooks to be added to the agent after calling the model"""

    tools: list[Any] = Field(default_factory=list)
    """tools: List of tools to make available to the agent.
    - tool names (e.g., "retrieve")
    - File paths (e.g., "/path/to/tool.py")
    - Imported Python modules (e.g., from spark.tools import bash_tool)
    - Functions wrapped with the @spark.tool decorator or spark.Tool class.
    """

    tool_choice: Literal['auto', 'any', 'none'] | str = 'auto'
    """Tool choice strategy for tool selection.

    Options:
    - 'auto' (default): LLM decides whether and which tool to use based on context
    - 'any': LLM must use at least one tool (any available tool)
    - 'none': Disable all tools for this call
    - '<tool_name>': Force the LLM to use a specific tool by name
    - None: Same as 'auto' when tools are available, no tools otherwise

    Example:
        # Let the LLM decide
        tool_choice='auto'

        # Force tool usage
        tool_choice='any'

        # Force specific tool
        tool_choice='search_web'

        # Disable tools
        tool_choice='none'
    """

    max_steps: int = 100
    """Maximum tool-execution steps per call. 0 means unlimited."""

    parallel_tool_execution: bool = False
    """Enable parallel tool execution when multiple tools are called.

    When True, tools are executed concurrently using asyncio.gather().
    When False (default), tools are executed sequentially.

    Note: Only enable if your tools are independent and thread-safe.
    Parallel execution can improve performance but may cause issues
    if tools have dependencies or side effects.

    Example:
        config = AgentConfig(
            model=model,
            tools=[search, calculate],
            parallel_tool_execution=True  # Execute tools concurrently
        )
    """

    reasoning_strategy: Optional[Any] = None
    """Reasoning strategy for structured thinking patterns.

    Options:
    - None (default): Uses NoOpStrategy for simple agents
    - ReActStrategy(): ReAct (Reasoning + Acting) pattern
    - ChainOfThoughtStrategy(): Chain-of-Thought reasoning
    - Custom ReasoningStrategy subclass

    Example:
        from spark.agents.strategies import ReActStrategy

        config = AgentConfig(
            model=model,
            reasoning_strategy=ReActStrategy(verbose=True)
        )
    """

    @model_validator(mode='after')
    def validate_config(self) -> 'AgentConfig':
        """Validate agent configuration for consistency.

        Raises:
            ValueError: If configuration is invalid
        """
        # Validate tool_choice consistency
        if self.tool_choice in ('any', 'required'):
            if not self.tools:
                raise ValueError(
                    f"tool_choice='{self.tool_choice}' requires at least one tool to be configured. "
                    "Please add tools to the 'tools' list or change tool_choice to 'auto' or 'none'."
                )

        # Validate specific tool name exists (can only validate at runtime when tools are registered)
        if (
            self.tool_choice
            and self.tool_choice not in ('auto', 'any', 'none', 'required', None)
            and not self.tools
        ):
            logger.warning(
                "tool_choice='%s' specifies a specific tool, but no tools are configured. "
                "Tool choice will fall back to 'auto' at runtime.",
                self.tool_choice
            )

        # Validate output_schema is only meaningful with JSON mode
        if self.output_schema != DefaultOutputSchema and self.output_mode != 'json':
            logger.warning(
                "output_schema is set but output_mode is '%s'. "
                "output_schema is only used when output_mode='json'. "
                "Consider changing output_mode to 'json' or removing output_schema.",
                self.output_mode
            )

        # Validate max_steps
        if self.max_steps < 0:
            raise ValueError(
                f"max_steps must be non-negative, got {self.max_steps}. "
                "Use 0 for unlimited steps or a positive integer for a limit."
            )

        # Validate memory_config is consistent
        if self.memory_config.policy.value not in ('null', 'rolling_window', 'summarize', 'custom'):
            raise ValueError(
                f"Invalid memory policy: {self.memory_config.policy}. "
                "Must be one of: null, rolling_window, summarize, custom"
            )

        if self.memory_config.window <= 0:
            raise ValueError(
                f"memory_config.window must be positive, got {self.memory_config.window}"
            )

        return self
