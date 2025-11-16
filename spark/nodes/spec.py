"""
Specification models for Spark graphs, nodes, edges, and tools.

These Pydantic models mirror the JSON contracts described in spec/spark001.md
and are used for validation, (de)serialization, and code generation inputs.

This module provides full-fidelity specification models for:
- Agents with reasoning strategies, memory, tools, cost tracking
- Tools from @tool decorator system and tool depot
- Advanced node types (RpcNode, JoinNode, ParallelNode, etc.)
- Graph features (GraphState, GraphEventBus, Task, Budget)
- Enhanced edge conditions and routing
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


class ToolHandlerSpec(BaseModel):
    """Handler configuration describing how a tool is invoked."""

    model_config = ConfigDict(extra='ignore')

    type: Literal['http', 'grpc', 'function', 'mcp']
    endpoint: Optional[str] = None
    method: Optional[str] = None
    timeout: Optional[int] = None


class ToolSpec(BaseModel):
    """Metadata and schemas defining a tool in the spec."""

    model_config = ConfigDict(extra='ignore')

    id: str
    description: Optional[str] = None
    input_schema: Optional[dict[str, Any]] = None
    output_schema: Optional[dict[str, Any]] = None
    error_schemas: Optional[list[dict[str, Any]]] = None
    handler: Optional[ToolHandlerSpec] = None


# ============================================================================
# Agent Configuration Specifications
# ============================================================================


class ReasoningStrategySpec(BaseModel):
    """Specification for reasoning strategy.

    Reasoning strategies define how an agent thinks and plans its actions.
    Common strategies include ReAct (Reasoning + Acting), Chain of Thought,
    and custom strategies.

    Example:
        {
            "type": "react",
            "config": {"verbose": true}
        }

        {
            "type": "custom",
            "custom_class": "myapp.strategies:MyStrategy",
            "config": {"param": "value"}
        }
    """

    model_config = ConfigDict(extra='ignore')

    type: Literal['noop', 'react', 'chain_of_thought', 'plan_and_solve', 'custom']
    """Strategy type - 'noop' for simple agents, 'react' for ReAct pattern,
    'chain_of_thought' for CoT, 'plan_and_solve' for plan-aware strategies,
    'custom' for user-defined strategies"""

    config: Optional[dict[str, Any]] = None
    """Strategy-specific configuration parameters"""

    custom_class: Optional[str] = None
    """Module:class reference for custom strategy (e.g., 'myapp.strategies:MyStrategy')"""

    @model_validator(mode='after')
    def validate_custom_strategy(self) -> 'ReasoningStrategySpec':
        """Validate that custom_class is provided when type is 'custom'."""
        if self.type == 'custom' and not self.custom_class:
            raise ValueError(
                "custom_class is required when type='custom'. "
                "Provide a module:class reference like 'myapp.strategies:MyStrategy'"
            )
        return self


class MemoryConfigSpec(BaseModel):
    """Memory management configuration.

    Controls how conversation history is managed and retained.

    Example:
        {
            "policy": "rolling_window",
            "window": 10,
            "summary_max_chars": 1000
        }
    """

    model_config = ConfigDict(extra='ignore')

    policy: Literal['null', 'rolling_window', 'summarize', 'custom'] = 'rolling_window'
    """Memory retention policy:
    - null: No memory retention
    - rolling_window: Keep last N messages
    - summarize: Summarize old messages while keeping recent ones
    - custom: Custom policy via callable"""

    window: int = 10
    """Number of messages to retain in rolling window"""

    summary_max_chars: int = 1000
    """Maximum characters for summarized content (summarize policy)"""


class ToolConfigSpec(BaseModel):
    """Tool configuration within agent.

    Defines how a specific tool is configured for use by an agent.

    Example:
        {
            "name": "search_web",
            "source": "tools:search_web",
            "enabled": true,
            "config": {"max_results": 5}
        }
    """

    model_config = ConfigDict(extra='ignore')

    name: str
    """Tool identifier/name"""

    source: str
    """Tool source reference - module:function or tool_id"""

    enabled: bool = True
    """Whether tool is enabled for use"""

    config: Optional[dict[str, Any]] = None
    """Tool-specific configuration parameters"""


class StructuredOutputSpec(BaseModel):
    """Structured output configuration.

    Controls whether agent output is plain text or structured JSON
    with schema validation.

    Example:
        {
            "mode": "structured",
            "output_schema": {...},
            "schema_class": "myapp.models:ResponseModel"
        }
    """

    model_config = ConfigDict(extra='ignore')

    mode: Literal['text', 'json'] = 'text'
    """Output mode - 'text' for plain text, 'json' for structured JSON"""

    output_schema: Optional[dict[str, Any]] = None
    """Pydantic schema as JSON (for serialization)"""

    schema_class: Optional[str] = None
    """Module:class reference to Pydantic model (e.g., 'myapp.models:Response')"""


class CostTrackingSpec(BaseModel):
    """Cost tracking configuration.

    Enables monitoring of token usage and API costs.

    Example:
        {
            "enabled": true,
            "track_tokens": true,
            "track_cost": true,
            "cost_limits": {"max_cost": 1.0}
        }
    """

    model_config = ConfigDict(extra='ignore')

    enabled: bool = False
    """Whether cost tracking is enabled"""

    track_tokens: bool = True
    """Track token usage"""

    track_cost: bool = True
    """Track monetary cost"""

    cost_limits: Optional[dict[str, float]] = None
    """Cost limit constraints (e.g., max_cost, max_tokens)"""


class AgentHooksSpec(BaseModel):
    """Agent hook callbacks.

    Hooks are callbacks executed at specific points in agent execution
    for logging, monitoring, or customization.

    Example:
        {
            "before_llm_hooks": ["myapp.hooks:log_request"],
            "after_llm_hooks": ["myapp.hooks:log_response"],
            "on_error": ["myapp.hooks:handle_error"]
        }
    """

    model_config = ConfigDict(extra='ignore')

    before_llm_hooks: list[str] = Field(default_factory=list)
    """Hooks called before LLM invocation - module:function references"""

    after_llm_hooks: list[str] = Field(default_factory=list)
    """Hooks called after LLM response - module:function references"""

    on_tool_call: Optional[str] = None
    """Hook called when tool is invoked - module:function reference"""

    on_error: Optional[str] = None
    """Hook called on error - module:function reference"""


class EnhancedAgentConfigSpec(BaseModel):
    """Complete agent configuration specification.

    This captures all aspects of agent configuration including model,
    tools, memory, reasoning strategy, and hooks.

    Example:
        {
            "model": {"provider": "openai", "model_id": "gpt-4o"},
            "system_prompt": "You are a helpful assistant",
            "tools": [
                {"name": "search", "source": "tools:search_web"}
            ],
            "tool_choice": "auto",
            "max_steps": 5,
            "memory_config": {"policy": "rolling_window", "window": 10},
            "reasoning_strategy": {"type": "react"},
            "cost_tracking": {"enabled": true}
        }
    """

    model_config = ConfigDict(extra='ignore')

    model: Union[str, 'ModelSpec']
    """Model configuration - either model_id string or full ModelSpec"""

    name: Optional[str] = None
    """Agent name"""

    description: Optional[str] = None
    """Agent description"""

    system_prompt: Optional[str] = None
    """System prompt for agent behavior"""

    prompt_template: Optional[str] = None
    """Jinja2 template for user prompts"""

    tools: list[ToolConfigSpec] = Field(default_factory=list)
    """Tools available to agent"""

    tool_choice: Literal['auto', 'any', 'none'] | str = 'auto'
    """Tool selection strategy - auto, any, none, or specific tool name"""

    max_steps: int = 100
    """Maximum reasoning/tool execution steps"""

    parallel_tool_execution: bool = False
    """Enable parallel tool execution"""

    output_config: Optional[StructuredOutputSpec] = None
    """Structured output configuration"""

    memory_config: Optional[MemoryConfigSpec] = None
    """Memory management configuration"""

    reasoning_strategy: Optional[ReasoningStrategySpec] = None
    """Reasoning strategy configuration"""

    cost_tracking: Optional[CostTrackingSpec] = None
    """Cost tracking configuration"""

    hooks: Optional[AgentHooksSpec] = None
    """Agent hook callbacks"""

    preload_messages: list[dict[str, Any]] = Field(default_factory=list)
    """Initial conversation history"""

    @model_validator(mode='after')
    def validate_agent_config(self) -> 'EnhancedAgentConfigSpec':
        """Validate agent configuration for consistency."""
        # Validate tool_choice consistency
        if self.tool_choice in ('any', 'required'):
            if not self.tools:
                raise ValueError(
                    f"tool_choice='{self.tool_choice}' requires at least one tool to be configured. "
                    "Please add tools to the 'tools' list or change tool_choice."
                )

        # Validate output_config consistency
        if self.output_config and self.output_config.mode == 'json':
            if not self.output_config.output_schema and not self.output_config.schema_class:
                raise ValueError(
                    "output_config with mode='json' requires either 'output_schema' or 'schema_class'"
                )

        # Validate max_steps
        if self.max_steps < 0:
            raise ValueError(f"max_steps must be non-negative, got {self.max_steps}")

        # Validate memory_config
        if self.memory_config and self.memory_config.window <= 0:
            raise ValueError(
                f"memory_config.window must be positive, got {self.memory_config.window}"
            )

        return self


# ============================================================================
# Tool System Specifications
# ============================================================================


class ToolParameterSpec(BaseModel):
    """Tool parameter definition.

    Describes a single parameter for a tool, including its type,
    description, and whether it's required.

    Example:
        {
            "name": "query",
            "type": "str",
            "description": "Search query",
            "required": true,
            "default": null,
            "inject_context": false
        }
    """

    model_config = ConfigDict(extra='ignore')

    name: str
    """Parameter name"""

    type: str
    """Python type annotation as string (e.g., 'str', 'int', 'list[str]')"""

    description: Optional[str] = None
    """Parameter description"""

    required: bool = True
    """Whether parameter is required"""

    default: Optional[Any] = None
    """Default value if not required"""

    inject_context: bool = False
    """Whether ToolContext should be injected for this parameter"""


class ToolDefinitionSpec(BaseModel):
    """Complete tool definition from @tool decorator.

    Captures all metadata about a tool including its parameters,
    return type, and execution characteristics.

    Example:
        {
            "name": "search_web",
            "function": "tools:search_web",
            "description": "Search the web for information",
            "parameters": [
                {"name": "query", "type": "str", "required": true}
            ],
            "return_type": "str",
            "return_description": "Search results",
            "is_async": false,
            "category": "search"
        }
    """

    model_config = ConfigDict(extra='ignore')

    name: str
    """Tool name/identifier"""

    function: str
    """Module:function reference (e.g., 'myapp.tools:search_web')"""

    description: str
    """Tool description explaining what it does"""

    parameters: list[ToolParameterSpec] = Field(default_factory=list)
    """List of tool parameters"""

    return_type: Optional[str] = None
    """Return type annotation as string"""

    return_description: Optional[str] = None
    """Description of return value"""

    is_async: bool = False
    """Whether tool is async"""

    category: Optional[str] = None
    """Tool category (e.g., 'git', 'python', 'shell')"""


class ToolDepotSpec(BaseModel):
    """Collection of tools from depot.

    Represents a collection of related tools from a tool depot module.

    Example:
        {
            "depot_id": "git_tools",
            "tools": [...],
            "version": "1.0"
        }
    """

    model_config = ConfigDict(extra='ignore')

    depot_id: str
    """Depot identifier (e.g., 'git_tools', 'python_tools')"""

    tools: list[ToolDefinitionSpec] = Field(default_factory=list)
    """Tools in this depot"""

    version: str = '1.0'
    """Depot version"""


# ============================================================================
# Edge and Condition Specifications
# ============================================================================


class ConditionSpec(BaseModel):
    """Serializable description of an edge condition.

    - kind='expr': expression string evaluated at runtime (e.g., "$.inputs.action == 'search'")
    - kind='equals': direct equals routing (e.g., {'action': 'search'})
    - kind='lambda': lambda function preserved as source code
    - kind='always': condition that always evaluates to true
    - kind='python': non-serializable callable; captured best-effort representation

    Example:
        {"kind": "expr", "expr": "$.outputs.score > 0.7"}
        {"kind": "equals", "equals": {"action": "search"}}
        {"kind": "lambda", "lambda_source": "lambda n: n.outputs.get('ready')"}
        {"kind": "always"}
    """

    model_config = ConfigDict(extra='ignore')

    kind: Literal['expr', 'equals', 'lambda', 'always', 'python'] = 'expr'
    """Condition type"""

    expr: Optional[str] = None
    """Expression string for 'expr' kind"""

    equals: Optional[dict[str, Any]] = None
    """Equality dict for 'equals' kind"""

    lambda_source: Optional[str] = None
    """Source code for lambda functions"""

    python_repr: Optional[str] = None
    """String representation for 'python' kind (best-effort)"""

    description: Optional[str] = None
    """Optional description of what this condition checks"""


# ============================================================================
# Advanced Node Type Specifications
# ============================================================================


class BatchProcessingSpec(BaseModel):
    """Batch processing configuration.

    Configuration for nodes that process lists of items
    (ParallelNode, MultipleThreadNode, MultipleProcessNode).

    Example:
        {
            "mode": "parallel",
            "failure_strategy": "skip_failed",
            "max_workers": 4,
            "timeout_per_item": 30.0
        }
    """

    model_config = ConfigDict(extra='ignore')

    mode: Literal['parallel', 'thread', 'process']
    """Execution mode - parallel (async), thread (threading), or process (multiprocessing)"""

    failure_strategy: Literal['all_or_nothing', 'skip_failed', 'collect_errors'] = 'all_or_nothing'
    """How to handle item failures:
    - all_or_nothing: Fail entire batch if any item fails
    - skip_failed: Skip failed items and continue
    - collect_errors: Collect errors but continue processing"""

    max_workers: Optional[int] = None
    """Maximum number of concurrent workers (thread/process modes)"""

    timeout_per_item: Optional[float] = None
    """Timeout in seconds for processing each item"""


class JoinNodeSpec(BaseModel):
    """Join/barrier node configuration.

    Configuration for JoinNode which waits for multiple parent nodes
    before proceeding.

    Example:
        {
            "keys": ["branch1", "branch2"],
            "mode": "all",
            "timeout": 30.0,
            "reducer": "myapp.reducers:merge_results"
        }
    """

    model_config = ConfigDict(extra='ignore')

    keys: list[str]
    """Expected parent node IDs to wait for"""

    mode: Literal['all', 'any'] = 'all'
    """Wait mode - 'all' waits for all parents, 'any' releases on first"""

    timeout: Optional[float] = None
    """Timeout in seconds for waiting"""

    reducer: Optional[str] = None
    """Module:function reference for custom merge logic"""


class RpcNodeSpec(BaseModel):
    """RPC node configuration.

    Configuration for RpcNode which exposes graph functionality
    as a JSON-RPC 2.0 service.

    Example:
        {
            "host": "0.0.0.0",
            "port": 8000,
            "protocol": "http",
            "methods": ["rpc_process", "rpc_status"]
        }
    """

    model_config = ConfigDict(extra='ignore')

    host: str = '0.0.0.0'
    """Server host address"""

    port: int = 8000
    """Server port"""

    protocol: Literal['http', 'websocket'] = 'http'
    """RPC protocol"""

    methods: list[str] = Field(default_factory=list)
    """RPC method names (e.g., rpc_* methods)"""


class SubgraphNodeSpec(BaseModel):
    """Subgraph node configuration.

    Configuration for SubgraphNode which wraps another graph
    as a single node.

    Example:
        {
            "graph_source": "myapp.graphs:my_graph",
            "input_mapping": {"query": "user_query"},
            "output_mapping": {"result": "final_result"}
        }

        {
            "graph_spec": {...},  # Inline graph definition
            "input_mapping": {...},
            "output_mapping": {...}
        }
    """

    model_config = ConfigDict(extra='ignore')

    graph_source: Optional[str] = None
    """Module:attr reference to graph instance or factory"""

    graph_spec: Optional['GraphSpec'] = None
    """Inline graph definition (alternative to graph_source)"""

    input_mapping: Optional[dict[str, str]] = None
    """Map parent outputs to subgraph inputs"""

    output_mapping: Optional[dict[str, str]] = None
    """Map subgraph outputs to this node's outputs"""

    share_state: bool = True
    """Share parent GraphState with the subgraph."""

    share_event_bus: bool = False
    """Forward the parent's event bus into the subgraph."""

    @model_validator(mode='after')
    def validate_graph_source(self) -> 'SubgraphNodeSpec':
        """Validate that exactly one of graph_source or graph_spec is provided."""
        has_source = self.graph_source is not None
        has_spec = self.graph_spec is not None

        if not has_source and not has_spec:
            raise ValueError(
                "Either 'graph_source' or 'graph_spec' must be provided for SubgraphNode"
            )

        if has_source and has_spec:
            raise ValueError(
                "Only one of 'graph_source' or 'graph_spec' should be provided, not both"
            )

        return self


# ============================================================================
# Graph Feature Specifications
# ============================================================================


class ModelSpec(BaseModel):
    """Model configuration specification.

    Captures model provider and configuration for LLM models.

    Example:
        {
            "provider": "openai",
            "model_id": "gpt-4o",
            "client_args": {"api_key": "..."},
            "streaming": false,
            "cache_enabled": false
        }
    """

    model_config = ConfigDict(extra='ignore')

    provider: Literal['openai', 'bedrock', 'gemini', 'ollama', 'echo']
    """Model provider name"""

    model_id: str
    """Model identifier (e.g., 'gpt-4o', 'claude-sonnet-4')"""

    client_args: dict[str, Any] = Field(default_factory=dict)
    """Provider-specific client arguments"""

    streaming: bool = False
    """Enable streaming responses"""

    cache_enabled: bool = False
    """Enable response caching"""


class StateBackendConfigSpec(BaseModel):
    """Backend configuration for GraphState."""

    model_config = ConfigDict(extra='ignore')

    name: Literal['memory', 'sqlite', 'file', 'redis', 'postgres', 's3'] = 'memory'
    """Backend identifier."""

    options: dict[str, Any] = Field(default_factory=dict)
    """Backend-specific options (paths, DSNs, etc.)."""

    serializer: str = 'json'
    """Serializer identifier (json, pickle, or custom registry entry)."""

    encryption: Optional[str] = None
    """Optional encryption reference."""


class StateCheckpointSpec(BaseModel):
    """Auto-checkpoint configuration for graph state."""

    model_config = ConfigDict(extra='ignore')

    enabled: bool = False
    every_n_iterations: Optional[int] = None
    every_seconds: Optional[float] = None
    retain_last: int = 5
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionStateSchemaSpec(BaseModel):
    """Metadata describing the mission state schema."""

    model_config = ConfigDict(extra='ignore')

    name: str
    version: str = '1.0'
    module: Optional[str] = None
    json_schema: Optional[dict[str, Any]] = None


class GraphStateSpec(BaseModel):
    """Graph state configuration.

    Configuration for shared state across all nodes in a graph.

    Example:
        {
            "initial_state": {"counter": 0, "status": "ready"},
            "concurrent_mode": false,
            "persistence": "memory"
        }
    """

    model_config = ConfigDict(extra='ignore')

    initial_state: dict[str, Any] = Field(default_factory=dict)
    """Initial state values"""

    concurrent_mode: bool = False
    """Enable locking for concurrent access (LONG_RUNNING tasks)"""

    persistence: Optional[Literal['memory', 'disk']] = 'memory'
    """Deprecated persistence strategy (use backend)."""

    backend: Optional[StateBackendConfigSpec] = None
    """Detailed backend configuration."""

    checkpointing: Optional[StateCheckpointSpec] = None
    """Auto-checkpoint declarative settings."""

    schema: Optional[MissionStateSchemaSpec] = None
    """Schema metadata for mission state."""

    @model_validator(mode='after')
    def _ensure_backend(self) -> 'GraphStateSpec':
        """Populate backend from legacy persistence flag if not provided."""
        if self.backend is None:
            backend_name = 'sqlite' if self.persistence == 'disk' else 'memory'
            self.backend = StateBackendConfigSpec(name=backend_name)
        return self


class GraphEventBusSpec(BaseModel):
    """Event bus configuration.

    Configuration for publish/subscribe event system within graph.

    Example:
        {
            "enabled": true,
            "buffer_size": 100,
            "topics": ["sensor.*", "alerts"]
        }
    """

    model_config = ConfigDict(extra='ignore')

    enabled: bool = True
    """Whether event bus is enabled"""

    buffer_size: int = 100
    """Event buffer size"""

    topics: list[str] = Field(default_factory=list)
    """Pre-configured topics (supports wildcards)"""


class BudgetSpec(BaseModel):
    """Execution budget constraints.

    Defines resource limits for task execution.

    Example:
        {
            "max_seconds": 300.0,
            "max_tokens": 10000,
            "max_cost": 1.0
        }
    """

    model_config = ConfigDict(extra='ignore')

    max_seconds: Optional[float] = None
    """Maximum execution time in seconds (0 = unlimited)"""

    max_tokens: Optional[int] = None
    """Maximum token usage (0 = unlimited)"""

    max_cost: Optional[float] = None
    """Maximum cost in dollars (0 = unlimited)"""


class TaskSpec(BaseModel):
    """Task configuration.

    Defines the type and execution parameters for a graph task.

    Example:
        {
            "type": "one_off",
            "inputs": {"query": "What is AI?"},
            "budget": {"max_seconds": 60.0},
            "resume_from": null
        }
    """

    model_config = ConfigDict(extra='ignore')

    type: Literal['one_off', 'long_running', 'streaming', 'resumable'] = 'one_off'
    """Task type"""

    inputs: dict[str, Any] = Field(default_factory=dict)
    """Initial task inputs"""

    budget: Optional[BudgetSpec] = None
    """Resource budget constraints"""

    resume_from: Optional[str] = None
    """Checkpoint ID for resumable tasks"""


# ============================================================================
# Node and Edge Specifications
# ============================================================================


class NodeSpec(BaseModel):
    """Serialized node descriptor within a graph spec."""

    model_config = ConfigDict(extra='ignore')

    id: str
    type: str
    description: Optional[str] = None
    inputs: Optional[dict[str, str]] = None
    outputs: Optional[dict[str, str]] = None
    config: Optional[dict[str, Any]] = None


class EdgeSpec(BaseModel):
    """Serialized edge descriptor connecting two nodes in a graph spec.

    Edges define the flow of data between nodes. When a node has multiple
    outgoing edges, ALL edges are evaluated (not first-match-wins). This
    enables fan-out behavior where multiple successor nodes can be activated
    simultaneously.

    Priority controls the evaluation order (higher priority = evaluated first),
    but does not prevent other edges from firing if their conditions are true.

    Example:
        {
            "id": "e1",
            "from_node": "router",
            "to_node": "processor",
            "condition": {"kind": "expr", "expr": "$.outputs.score > 0.7"},
            "priority": 10,
            "description": "High quality route",
            "metadata": {"category": "quality_check"}
        }
    """

    model_config = ConfigDict(extra='ignore')

    id: str
    """Unique edge identifier"""

    from_node: str = Field(alias='from_id')
    """Source node ID"""

    to_node: str = Field(alias='to_id')
    """Target node ID"""

    condition: Optional[Union[str, ConditionSpec]] = None
    """Edge activation condition (None = always active)"""

    description: Optional[str] = None
    """Human-readable edge description"""

    priority: int = 0
    """Edge priority (higher = evaluated first)"""

    metadata: dict[str, Any] = Field(default_factory=dict)
    """Additional edge metadata"""

    # Documentation field for fan-out behavior
    fanout_behavior: Literal['evaluate_all', 'first_match'] = 'evaluate_all'
    """Fan-out behavior (Spark always uses 'evaluate_all')"""

    delay_seconds: float | None = None
    """Optional delay before forwarding payloads."""

    event_topic: Optional[str] = None
    """Event bus topic for event-driven edges."""

    event_filter: Optional[Union[str, ConditionSpec]] = None
    """Optional condition applied to event payloads."""

    @model_validator(mode='before')
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        """Accept both alias pairs (from_node/to_node) and (from_id/to_id) on input."""
        # Accept either from_node/to_node or from_id/to_id on input
        if isinstance(data, dict):
            if 'from_node' in data and 'from_id' not in data:
                data['from_id'] = data['from_node']
            if 'to_node' in data and 'to_id' not in data:
                data['to_id'] = data['to_node']
        return data

    def model_dump_standard(self) -> dict[str, Any]:
        """Dump using spec's from_node/to_node names."""
        payload = self.model_dump(by_alias=True)
        # Translate back to spec preferred names
        payload['from_node'] = payload.pop('from_id')
        payload['to_node'] = payload.pop('to_id')
        return payload


class SimulationToolOverrideSpec(BaseModel):
    """Configuration for a simulated tool override."""

    model_config = ConfigDict(extra='ignore')

    name: str
    """Tool identifier (matches agent tool name)."""

    description: str | None = None
    """Optional description for reporting."""

    static_response: Any | None = None
    """Inline response payload returned by the simulation."""

    handler: str | None = None
    """Optional callable reference (module:function) that generates responses."""

    parameters: dict[str, Any] = Field(
        default_factory=lambda: {'type': 'object', 'properties': {}, 'required': []},
        description="JSON schema describing expected arguments.",
    )

    response_schema: dict[str, Any] | None = None
    """Optional JSON schema describing simulation responses."""

    @model_validator(mode='after')
    def validate_source(self) -> 'SimulationToolOverrideSpec':
        if self.static_response is None and not self.handler:
            raise ValueError("Simulation tool override requires either 'static_response' or 'handler'.")
        return self


class MissionSimulationSpec(BaseModel):
    """Mission-level simulation configuration."""

    model_config = ConfigDict(extra='ignore')

    enabled: bool = False
    """Toggle simulation behavior."""

    latency_seconds: float = 0.0
    """Optional artificial latency applied to simulated tools."""

    tools: list[SimulationToolOverrideSpec] = Field(default_factory=list)
    """Tool overrides available during simulation runs."""


class GraphSpec(BaseModel):
    """Top-level graph specification including nodes, edges, and graph features.

    Complete specification for a Spark graph including all runtime features
    like shared state, event bus, task configuration, and tools.

    Example:
        {
            "spark_version": "2.0",
            "id": "com.example.my-graph",
            "description": "Example graph with all features",
            "start": "input_node",
            "nodes": [...],
            "edges": [...],
            "graph_state": {
                "initial_state": {"counter": 0},
                "concurrent_mode": false
            },
            "event_bus": {
                "enabled": true,
                "buffer_size": 100
            },
            "task": {
                "type": "one_off",
                "budget": {"max_seconds": 60.0}
            },
            "tools": [...]
        }
    """

    model_config = ConfigDict(extra='ignore')

    spark_version: str = '2.0'
    """Spark specification version"""

    id: str
    """Unique graph identifier"""

    description: Optional[str] = None
    """Human-readable graph description"""

    start: str
    """Starting node ID"""

    nodes: list[NodeSpec] = Field(default_factory=list)
    """Graph nodes"""

    edges: list[EdgeSpec] = Field(default_factory=list)
    """Graph edges"""

    graph_state: Optional[GraphStateSpec] = None
    """Shared state configuration"""

    event_bus: Optional[GraphEventBusSpec] = None
    """Event bus configuration"""

    task: Optional[TaskSpec] = None
    """Default task configuration"""

    tools: list[ToolDefinitionSpec] = Field(default_factory=list)
    """Graph-level tool definitions"""

    @field_validator('nodes')
    @classmethod
    def unique_node_ids(cls, nodes: list[NodeSpec]) -> list[NodeSpec]:
        """Validate that node identifiers are unique within the graph."""
        seen: set[str] = set()
        for n in nodes:
            if n.id in seen:
                raise ValueError(f'duplicate node id: {n.id}')
            seen.add(n.id)
        return nodes

    @model_validator(mode='after')
    def validate_graph(self) -> 'GraphSpec':
        """Validate edge references and start node presence."""
        node_ids = {n.id for n in self.nodes}
        if self.start not in node_ids:
            raise ValueError(f'start node {self.start!r} not found among nodes')
        for e in self.edges:
            if e.from_node not in node_ids:
                raise ValueError(f'edge {e.id} references missing from_node {e.from_node!r}')
            if e.to_node not in node_ids:
                raise ValueError(f'edge {e.id} references missing to_node {e.to_node!r}')
        return self

    def model_dump_standard(self) -> dict[str, Any]:
        """Dump graph using spec field names consistently."""
        payload = self.model_dump()
        payload['edges'] = [e.model_dump_standard() for e in self.edges]
        return payload


class MissionPlanStepSpec(BaseModel):
    """Declarative mission plan step."""

    model_config = ConfigDict(extra='ignore')

    id: str
    description: str
    depends_on: list[str] = Field(default_factory=list)


class MissionPlanSpec(BaseModel):
    """Mission-level plan definition rendered by strategies and templates."""

    model_config = ConfigDict(extra='ignore')

    name: str = 'mission_plan'
    description: Optional[str] = None
    steps: list[MissionPlanStepSpec] = Field(default_factory=list)
    auto_advance: bool = True
    telemetry_topic: Optional[str] = None

    @field_validator('steps')
    @classmethod
    def unique_step_ids(cls, steps: list[MissionPlanStepSpec]) -> list[MissionPlanStepSpec]:
        seen: set[str] = set()
        for step in steps:
            if step.id in seen:
                raise ValueError(f'duplicate plan step id: {step.id}')
            seen.add(step.id)
        return steps

    @model_validator(mode='after')
    def _validate_dependencies(self) -> 'MissionPlanSpec':
        step_ids = {step.id for step in self.steps}
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise ValueError(f'plan step {step.id!r} depends on unknown step {dep!r}')
        return self


class MissionStrategyBindingSpec(BaseModel):
    """Binding between a mission component (graph/agent/subgraph) and a strategy."""

    model_config = ConfigDict(extra='ignore')

    target: Literal['graph', 'agent', 'subgraph'] = 'graph'
    reference: str = 'graph'
    description: Optional[str] = None
    strategy: ReasoningStrategySpec
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionTelemetrySpec(BaseModel):
    """Mission-level telemetry/export configuration."""

    model_config = ConfigDict(extra='ignore')

    enabled: bool = True
    backend: Optional[str] = None
    topics: list[str] = Field(default_factory=list)
    sampling_rate: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionDeploymentSpec(BaseModel):
    """Deployment metadata for packaging/rollout."""

    model_config = ConfigDict(extra='ignore')

    environment: str = 'dev'
    runtime: Optional[str] = None
    entrypoint: Optional[str] = None
    health_check: Optional[str] = None
    scaling: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionSpec(BaseModel):
    """Full mission package describing graph, plan, strategies, and deployment metadata."""

    model_config = ConfigDict(extra='ignore')

    spark_version: str = '2.0'
    mission_id: str
    version: str = '1.0'
    description: Optional[str] = None
    graph: GraphSpec
    plan: Optional[MissionPlanSpec] = None
    strategies: list[MissionStrategyBindingSpec] = Field(default_factory=list)
    state_schema: Optional[MissionStateSchemaSpec] = None
    telemetry: Optional[MissionTelemetrySpec] = None
    deployment: Optional[MissionDeploymentSpec] = None
    simulation: Optional[MissionSimulationSpec] = None

    @field_validator('strategies')
    @classmethod
    def unique_strategy_bindings(cls, bindings: list[MissionStrategyBindingSpec]) -> list[MissionStrategyBindingSpec]:
        seen: set[tuple[str, str]] = set()
        for binding in bindings:
            key = (binding.target, binding.reference)
            if key in seen:
                raise ValueError(f'duplicate strategy binding for {binding.target}:{binding.reference}')
            seen.add(key)
        return bindings
