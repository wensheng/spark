"""Agent Config"""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Literal, Optional, Any, TypeVar, Union
import logging

from pydantic import BaseModel, ConfigDict, Field, model_validator

from spark.nodes.config import NodeConfig
from spark.models.base import Model
from spark.models.types import Messages
from spark.agents.memory import MemoryConfig
from spark.agents.policies import AgentBudgetConfig, HumanInteractionPolicy
from spark.governance.policy import PolicySet
from spark.utils.import_utils import import_from_ref, get_ref_for_callable, safe_import_from_ref

if TYPE_CHECKING:
    from spark.agents.strategies import ReasoningStrategy
    from spark.agents.strategy_registry import StrategyRegistry

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
HookFn = Callable[..., Optional[Awaitable[None]]]
HookRef = Union[HookFn, str]  # Hook can be callable or module:function string


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

    before_llm_hooks: list[HookRef] = Field(default_factory=list)
    """
    before_llm_hooks: hooks to be added before calling the LLM.
    Can be callables or module:function string references.
    while pre_process_hooks are executed before the process method.

    Example:
        # Using callable
        before_llm_hooks=[my_hook_function]

        # Using string reference (spec-compatible)
        before_llm_hooks=["myapp.hooks:before_llm"]
    """

    after_llm_hooks: list[HookRef] = Field(default_factory=list)
    """
    after_llm_hooks: hooks to be added to the agent after calling the model.
    Can be callables or module:function string references.

    Example:
        # Using callable
        after_llm_hooks=[my_hook_function]

        # Using string reference (spec-compatible)
        after_llm_hooks=["myapp.hooks:after_llm"]
    """

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

    Can be:
    - None (default): Uses NoOpStrategy for simple agents
    - Strategy instance: ReActStrategy(), ChainOfThoughtStrategy(), etc.
    - Strategy name (string): "react", "chain_of_thought", "noop"
    - Custom ReasoningStrategy subclass

    Example:
        from spark.agents.strategies import ReActStrategy

        # Using instance (existing pattern)
        config = AgentConfig(
            model=model,
            reasoning_strategy=ReActStrategy(verbose=True)
        )

        # Using name (spec-compatible)
        config = AgentConfig(
            model=model,
            reasoning_strategy="react"
        )
    """

    budget: AgentBudgetConfig | None = None
    """Optional runtime budget enforcement."""

    human_policy: HumanInteractionPolicy | None = None
    """Optional human interaction policy (approvals, stop tokens)."""

    policy_set: PolicySet | None = None
    """Optional governance policies enforced before tool execution."""

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

    def resolve_hook(self, hook: HookRef) -> HookFn:
        """Resolve a hook reference to a callable.

        Args:
            hook: Either a callable or module:function string reference

        Returns:
            The resolved callable hook function

        Raises:
            ValueError: If string reference cannot be imported

        Example:
            # Resolve string reference
            hook_fn = config.resolve_hook("myapp.hooks:my_hook")

            # Pass through callable
            hook_fn = config.resolve_hook(my_hook_function)
        """
        if isinstance(hook, str):
            try:
                return import_from_ref(hook)
            except Exception as e:
                raise ValueError(f"Failed to import hook from '{hook}': {e}") from e
        return hook

    def resolve_hooks(self, hooks: list[HookRef]) -> list[HookFn]:
        """Resolve a list of hook references to callables.

        Args:
            hooks: List of callables or module:function string references

        Returns:
            List of resolved callable hook functions

        Example:
            hooks = config.resolve_hooks(config.before_llm_hooks)
        """
        return [self.resolve_hook(hook) for hook in hooks]

    def resolve_strategy(self, strategy: Optional[Any] = None) -> Optional['ReasoningStrategy']:
        """Resolve a strategy reference to an instance.

        Args:
            strategy: Strategy name (string), instance, or None. If None, uses self.reasoning_strategy

        Returns:
            Strategy instance, or None if no strategy

        Raises:
            ValueError: If strategy name not found in registry

        Example:
            # Resolve string name
            strategy = config.resolve_strategy("react")

            # Pass through instance
            strategy = config.resolve_strategy(ReActStrategy())

            # Use config's strategy
            strategy = config.resolve_strategy()
        """
        if strategy is None:
            strategy = self.reasoning_strategy

        if strategy is None:
            return None

        # If already an instance, return it
        from spark.agents.strategies import ReasoningStrategy
        if isinstance(strategy, ReasoningStrategy):
            return strategy

        # If it's a string, look it up in the registry
        if isinstance(strategy, str):
            from spark.agents.strategy_registry import get_global_registry
            registry = get_global_registry()
            try:
                return registry.create_strategy(strategy)
            except Exception as e:
                raise ValueError(f"Failed to resolve strategy '{strategy}': {e}") from e

        # If it's a class, instantiate it
        if isinstance(strategy, type) and issubclass(strategy, ReasoningStrategy):
            return strategy()

        raise ValueError(f"Invalid strategy type: {type(strategy)}")

    def get_strategy_spec(self, strategy: Optional[Any] = None) -> Optional[dict[str, Any]]:
        """Get strategy specification for serialization.

        Args:
            strategy: Strategy instance, name, or None. If None, uses self.reasoning_strategy

        Returns:
            Dictionary with strategy spec (name or ref), or None if no strategy

        Example:
            spec = config.get_strategy_spec()
            # {"name": "react"} or {"ref": "myapp.strategies:CustomStrategy"}
        """
        if strategy is None:
            strategy = self.reasoning_strategy

        if strategy is None:
            return None

        # If it's a string name, just return it
        if isinstance(strategy, str):
            return {"name": strategy}

        # If it's an instance, try to get its name or reference from registry
        from spark.agents.strategies import ReasoningStrategy
        if isinstance(strategy, ReasoningStrategy):
            from spark.agents.strategy_registry import get_global_registry
            registry = get_global_registry()

            # Check if it's a registered strategy
            strategy_class = strategy.__class__
            for name, registered_class in registry.registry.items():
                if registered_class == strategy_class:
                    # Found in registry - use name
                    return {"name": name}

            # Not in registry - try to get class reference
            try:
                ref = get_ref_for_class(strategy_class)
                return {"ref": ref}
            except Exception:
                logger.warning(
                    "Could not serialize strategy %s to spec",
                    strategy_class.__name__
                )
                return None

        return None

    def get_hook_ref(self, hook: HookFn) -> Optional[str]:
        """Get the module:function reference for a hook callable.

        Args:
            hook: A callable hook function

        Returns:
            Module:function reference string, or None if not available

        Example:
            ref = config.get_hook_ref(my_hook_function)
            # Returns: "myapp.hooks:my_hook_function"
        """
        try:
            return get_ref_for_callable(hook)
        except Exception:
            return None

    def to_spec_dict(self) -> dict[str, Any]:
        """Serialize config to spec-compatible dictionary.

        This enables AgentConfig to be serialized to JSON specifications
        for bidirectional conversion between Python and JSON.

        Returns:
            Dictionary containing config data with string references

        Example:
            spec = config.to_spec_dict()
            # Can be serialized to JSON
            import json
            json.dumps(spec)
        """
        spec: dict[str, Any] = {
            "model": {
                "type": self.model.__class__.__name__,
                "model_id": getattr(self.model, "model_id", None)
            },
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "prompt_template": self.prompt_template,
            "preload_messages": self.preload_messages,
            "memory_config": {
                "policy": self.memory_config.policy.value,
                "window": self.memory_config.window,
                "summary_max_chars": self.memory_config.summary_max_chars
            },
            "output_mode": self.output_mode,
            "tool_choice": self.tool_choice,
            "max_steps": self.max_steps,
            "parallel_tool_execution": self.parallel_tool_execution
        }

        # Serialize hooks - convert callables to string references
        before_hooks_refs = []
        for hook in self.before_llm_hooks:
            if isinstance(hook, str):
                before_hooks_refs.append(hook)
            else:
                ref = self.get_hook_ref(hook)
                if ref:
                    before_hooks_refs.append(ref)
                else:
                    logger.warning("Could not serialize hook to reference: %s", hook)

        after_hooks_refs = []
        for hook in self.after_llm_hooks:
            if isinstance(hook, str):
                after_hooks_refs.append(hook)
            else:
                ref = self.get_hook_ref(hook)
                if ref:
                    after_hooks_refs.append(ref)
                else:
                    logger.warning("Could not serialize hook to reference: %s", hook)

        if before_hooks_refs:
            spec["before_llm_hooks"] = before_hooks_refs
        if after_hooks_refs:
            spec["after_llm_hooks"] = after_hooks_refs

        # Serialize reasoning strategy
        strategy_spec = self.get_strategy_spec()
        if strategy_spec:
            spec["reasoning_strategy"] = strategy_spec

        # Note: tools and output_schema require separate handling
        # as they have their own registries/serialization mechanisms

        return spec

    @classmethod
    def from_spec_dict(cls, spec: dict[str, Any], model: Model) -> "AgentConfig":
        """Deserialize config from spec dictionary.

        Args:
            spec: Dictionary containing config data
            model: Model instance to use (must be provided separately)

        Returns:
            New AgentConfig instance

        Example:
            spec = config.to_spec_dict()
            new_config = AgentConfig.from_spec_dict(spec, model)
        """
        # Extract hooks as string references
        before_hooks = spec.get("before_llm_hooks", [])
        after_hooks = spec.get("after_llm_hooks", [])

        # Create memory config
        memory_spec = spec.get("memory_config", {})
        memory_config = MemoryConfig(
            policy=memory_spec.get("policy", "null"),
            window=memory_spec.get("window", 10),
            summary_max_chars=memory_spec.get("summary_max_chars", 1000)
        )

        # Load reasoning strategy
        strategy = None
        strategy_spec = spec.get("reasoning_strategy")
        if strategy_spec:
            if "name" in strategy_spec:
                # Strategy by name
                strategy = strategy_spec["name"]
            elif "ref" in strategy_spec:
                # Strategy by reference - store as string, will be resolved when needed
                strategy = strategy_spec["ref"]

        return cls(
            model=model,
            name=spec.get("name"),
            description=spec.get("description"),
            system_prompt=spec.get("system_prompt"),
            prompt_template=spec.get("prompt_template"),
            preload_messages=spec.get("preload_messages", []),
            memory_config=memory_config,
            output_mode=spec.get("output_mode", "text"),
            before_llm_hooks=before_hooks,
            after_llm_hooks=after_hooks,
            reasoning_strategy=strategy,
            tool_choice=spec.get("tool_choice", "auto"),
            max_steps=spec.get("max_steps", 100),
            parallel_tool_execution=spec.get("parallel_tool_execution", False)
        )
