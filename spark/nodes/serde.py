"""
Serialization helpers between runtime Graph/Node/Edge and spec models.

This module provides full-fidelity export of in-memory graphs to GraphSpec.
It supports:
- Complete agent configuration (tools, memory, reasoning strategy, hooks)
- All node types (Agent, RpcNode, JoinNode, batch processing nodes, etc.)
- Graph features (GraphState, GraphEventBus, Task, Budget)
- Tool introspection and serialization
- Enhanced edge conditions (expr, equals, lambda, always)

Phase 2 Enhancement: Full-fidelity bidirectional conversion.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Dict, List, Optional

from spark.nodes.base import BaseNode, Edge
from spark.graphs.base import BaseGraph
from spark.nodes.config import NodeConfig
from spark.nodes.spec import (
    ConditionSpec,
    EdgeSpec,
    GraphSpec,
    NodeSpec,
    # Agent Config Specs
    EnhancedAgentConfigSpec,
    ReasoningStrategySpec,
    MemoryConfigSpec,
    ToolConfigSpec,
    StructuredOutputSpec,
    CostTrackingSpec,
    AgentHooksSpec,
    # Tool Specs
    ToolDefinitionSpec,
    ToolParameterSpec,
    # Node Type Specs
    BatchProcessingSpec,
    JoinNodeSpec,
    RpcNodeSpec,
    SubgraphNodeSpec,
    # Graph Feature Specs
    ModelSpec,
    GraphStateSpec,
    GraphEventBusSpec,
    StateBackendConfigSpec,
    StateCheckpointSpec,
    MissionStateSchemaSpec,
    TaskSpec,
    BudgetSpec,
    MissionSpec,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# Helper Functions for Type Inference
# ==============================================================================


def _infer_node_type(node: BaseNode) -> str:
    """Infer node type from runtime instance.

    Returns specific types like 'Agent', 'RpcNode', 'JoinNode', etc.
    Falls back to class name or 'Node' for generic nodes.
    """
    cls_name = node.__class__.__name__
    mod_name = getattr(node.__class__, '__module__', '')

    # Check for specific node types
    if cls_name.endswith('Agent') or '.agents.' in mod_name:
        return 'Agent'
    if cls_name == 'RpcNode' or 'rpc' in cls_name.lower():
        return 'RpcNode'
    if cls_name == 'JoinNode':
        return 'JoinNode'
    if cls_name == 'SubgraphNode':
        return 'SubgraphNode'
    if cls_name in ('ParallelNode', 'MultipleThreadNode', 'MultipleProcessNode', 'SequentialNode'):
        return cls_name

    # Return class name as type for custom nodes
    return cls_name if cls_name != 'Node' else 'Basic'


def _get_module_ref(obj: Any) -> Optional[str]:
    """Get module:name reference for an object.

    Returns a string like 'myapp.module:ClassName' or 'myapp.module:function_name'.
    Returns None if unable to determine reference.
    """
    if obj is None:
        return None

    try:
        module = inspect.getmodule(obj)
        if module is None:
            return None

        module_name = module.__name__

        # Handle classes
        if inspect.isclass(obj):
            return f"{module_name}:{obj.__name__}"

        # Handle functions
        if inspect.isfunction(obj) or inspect.ismethod(obj):
            return f"{module_name}:{obj.__name__}"

        # Handle instances - get class reference
        if hasattr(obj, '__class__'):
            cls = obj.__class__
            return f"{cls.__module__}:{cls.__name__}"

        return None
    except Exception as e:
        logger.debug(f"Could not get module reference for {obj}: {e}")
        return None


# ==============================================================================
# Tool Serialization
# ==============================================================================


def tool_to_spec(tool: Any) -> Optional[ToolDefinitionSpec]:
    """Serialize a tool to ToolDefinitionSpec.

    Extracts metadata from @tool decorated functions or BaseTool instances.

    Args:
        tool: Tool function or BaseTool instance

    Returns:
        ToolDefinitionSpec or None if tool cannot be serialized
    """
    try:
        from spark.tools.decorator import DecoratedFunctionTool
        from spark.tools.types import BaseTool

        # Get tool name
        name = getattr(tool, 'name', None) or getattr(tool, '__name__', 'unknown')

        # Get function reference
        if isinstance(tool, DecoratedFunctionTool):
            func = tool.func
            func_ref = _get_module_ref(func) or f"unknown:{name}"
        elif isinstance(tool, BaseTool):
            func_ref = _get_module_ref(tool) or f"unknown:{name}"
        elif callable(tool):
            func_ref = _get_module_ref(tool) or f"unknown:{name}"
            func = tool
        else:
            return None

        # Get description
        description = getattr(tool, 'description', None)
        if not description and hasattr(tool, 'func'):
            func_to_check = getattr(tool, 'func')
            description = inspect.getdoc(func_to_check) or ""
        if not description:
            description = inspect.getdoc(tool) or ""

        # Get parameters
        parameters = []
        if hasattr(tool, 'func'):
            func_to_inspect = getattr(tool, 'func')
        else:
            func_to_inspect = tool if callable(tool) else None

        if func_to_inspect:
            sig = inspect.signature(func_to_inspect)
            for param_name, param in sig.parameters.items():
                # Skip self, cls, and common injected parameters
                if param_name in ('self', 'cls', 'ctx', 'context'):
                    continue

                param_type = 'Any'
                if param.annotation != inspect.Parameter.empty:
                    param_type = str(param.annotation)

                required = param.default == inspect.Parameter.empty
                default_val = None if required else param.default

                param_spec = ToolParameterSpec(
                    name=param_name,
                    type=param_type,
                    required=required,
                    default=default_val,
                    inject_context=(param_name in ('ctx', 'context'))
                )
                parameters.append(param_spec)

        # Get return type
        return_type = None
        if func_to_inspect:
            sig = inspect.signature(func_to_inspect)
            if sig.return_annotation != inspect.Signature.empty:
                return_type = str(sig.return_annotation)

        # Check if async
        is_async = inspect.iscoroutinefunction(func_to_inspect) if func_to_inspect else False

        return ToolDefinitionSpec(
            name=name,
            function=func_ref,
            description=description,
            parameters=parameters,
            return_type=return_type,
            is_async=is_async
        )
    except Exception as e:
        logger.debug(f"Could not serialize tool {tool}: {e}")
        return None


# ==============================================================================
# Model Serialization
# ==============================================================================


def model_to_spec(model: Any) -> Optional[ModelSpec]:
    """Serialize a Model instance to ModelSpec.

    Args:
        model: Model instance (OpenAIModel, BedrockModel, etc.)

    Returns:
        ModelSpec or None if model cannot be serialized
    """
    try:
        from spark.models.base import Model

        if not isinstance(model, Model):
            # Try to handle model ID strings
            if isinstance(model, str):
                # Simple model ID string - infer provider
                if 'gpt' in model.lower():
                    provider = 'openai'
                elif 'claude' in model.lower():
                    provider = 'bedrock'
                elif 'gemini' in model.lower():
                    provider = 'gemini'
                else:
                    provider = 'openai'  # Default

                return ModelSpec(
                    provider=provider,  # type: ignore
                    model_id=model,
                    streaming=False,
                    cache_enabled=False
                )
            return None

        # Get provider from class name
        class_name = model.__class__.__name__
        provider_map = {
            'OpenAIModel': 'openai',
            'BedrockModel': 'bedrock',
            'GeminiModel': 'gemini',
            'OllamaModel': 'ollama',
            'EchoModel': 'echo'
        }
        provider = provider_map.get(class_name, 'openai')

        # Get model ID - try get_config() first, then attribute
        model_id = 'unknown'
        try:
            config = model.get_config()
            model_id = config.get('model_id', 'unknown')
        except Exception:
            model_id = getattr(model, 'model_id', 'unknown')

        # Get streaming setting
        streaming = getattr(model, 'streaming', False)

        # Get cache settings
        cache_enabled = getattr(model, '_cache_enabled', False)

        return ModelSpec(
            provider=provider,  # type: ignore
            model_id=model_id,
            streaming=streaming,
            cache_enabled=cache_enabled
        )
    except Exception as e:
        logger.debug(f"Could not serialize model {model}: {e}")
        return None


# ==============================================================================
# Agent Configuration Serialization
# ==============================================================================


def agent_config_to_spec(agent: Any) -> Optional[EnhancedAgentConfigSpec]:
    """Serialize an Agent's configuration to EnhancedAgentConfigSpec.

    Extracts complete agent configuration including tools, memory,
    reasoning strategy, cost tracking, and hooks.

    Args:
        agent: Agent instance

    Returns:
        EnhancedAgentConfigSpec or None if agent cannot be serialized
    """
    try:
        config = getattr(agent, 'config', None)
        if not config:
            return None

        # Serialize model
        model = getattr(config, 'model', None)
        model_spec = model_to_spec(model)
        if not model_spec:
            # Fallback to simple model ID
            model_spec = str(model) if model else 'gpt-4o-mini'

        # Get basic agent info
        name = getattr(config, 'name', None)
        description = getattr(config, 'description', None)
        system_prompt = getattr(config, 'system_prompt', None)
        prompt_template = getattr(config, 'prompt_template', None)

        # Serialize tools
        tool_specs: List[ToolConfigSpec] = []
        tools = getattr(config, 'tools', [])
        tool_registry = getattr(agent, 'tool_registry', None)
        if tool_registry:
            # ToolRegistry has a 'registry' attribute
            all_tools = getattr(tool_registry, 'registry', {})
            for tool_name, tool_obj in all_tools.items():
                func_ref = _get_module_ref(tool_obj) or f"tools:{tool_name}"
                tool_specs.append(ToolConfigSpec(
                    name=tool_name,
                    source=func_ref,
                    enabled=True
                ))

        # Get tool choice
        tool_choice = getattr(config, 'tool_choice', 'auto')

        # Get max steps
        max_steps = getattr(config, 'max_steps', 100)

        # Get parallel tool execution
        parallel_tool_execution = getattr(config, 'parallel_tool_execution', False)

        # Serialize output config
        output_config = None
        output_mode = getattr(config, 'output_mode', 'text')
        if output_mode == 'json':
            output_schema_cls = getattr(config, 'output_schema', None)
            schema_ref = _get_module_ref(output_schema_cls) if output_schema_cls else None
            output_config = StructuredOutputSpec(
                mode='json',
                schema_class=schema_ref
            )

        # Serialize memory config
        memory_config_obj = getattr(config, 'memory_config', None)
        memory_config = None
        if memory_config_obj:
            policy = str(getattr(memory_config_obj, 'policy', 'rolling_window'))
            window = getattr(memory_config_obj, 'window', 10)
            summary_max_chars = getattr(memory_config_obj, 'summary_max_chars', 1000)
            memory_config = MemoryConfigSpec(
                policy=policy,  # type: ignore
                window=window,
                summary_max_chars=summary_max_chars
            )

        # Serialize reasoning strategy
        reasoning_strategy = None
        strategy_obj = getattr(config, 'reasoning_strategy', None)
        if strategy_obj:
            if isinstance(strategy_obj, str):
                # Strategy name
                reasoning_strategy = ReasoningStrategySpec(
                    type=strategy_obj,  # type: ignore
                    config=None
                )
            elif strategy_obj is not None:
                # Strategy instance
                strategy_name = strategy_obj.__class__.__name__.replace('Strategy', '').lower()
                if strategy_name in ('noop', 'react', 'chain_of_thought', 'plan_and_solve'):
                    reasoning_strategy = ReasoningStrategySpec(
                        type=strategy_name,  # type: ignore
                        config=None
                    )
                else:
                    custom_class = _get_module_ref(strategy_obj)
                    reasoning_strategy = ReasoningStrategySpec(
                        type='custom',
                        custom_class=custom_class
                    )

        # Serialize cost tracking
        cost_tracking = None
        cost_tracker = getattr(agent, 'cost_tracker', None)
        if cost_tracker:
            cost_tracking = CostTrackingSpec(
                enabled=True,
                track_tokens=True,
                track_cost=True
            )

        # Serialize hooks
        hooks = None
        before_hooks = getattr(config, 'before_llm_hooks', [])
        after_hooks = getattr(config, 'after_llm_hooks', [])
        if before_hooks or after_hooks:
            before_refs = []
            for hook in before_hooks:
                if isinstance(hook, str):
                    before_refs.append(hook)
                else:
                    ref = _get_module_ref(hook)
                    if ref:
                        before_refs.append(ref)

            after_refs = []
            for hook in after_hooks:
                if isinstance(hook, str):
                    after_refs.append(hook)
                else:
                    ref = _get_module_ref(hook)
                    if ref:
                        after_refs.append(ref)

            hooks = AgentHooksSpec(
                before_llm_hooks=before_refs,
                after_llm_hooks=after_refs
            )

        # Get preload messages
        preload_messages = list(getattr(config, 'preload_messages', []))

        return EnhancedAgentConfigSpec(
            model=model_spec,  # type: ignore
            name=name,
            description=description,
            system_prompt=system_prompt,
            prompt_template=prompt_template,
            tools=tool_specs,
            tool_choice=tool_choice,  # type: ignore
            max_steps=max_steps,
            parallel_tool_execution=parallel_tool_execution,
            output_config=output_config,
            memory_config=memory_config,
            reasoning_strategy=reasoning_strategy,
            cost_tracking=cost_tracking,
            hooks=hooks,
            preload_messages=preload_messages
        )
    except Exception as e:
        logger.warning(f"Could not fully serialize agent config: {e}")
        return None


def _safe_config_from_node(node: BaseNode) -> Dict[str, Any]:
    """Extract a JSON-friendly subset of node configuration/state."""
    cfg: Dict[str, Any] = {}
    # Base fields
    if getattr(node, 'description', None):
        cfg['description'] = node.description
    # NodeConfig subset
    nc = getattr(node, 'config', None)
    if isinstance(nc, NodeConfig):
        if nc.id:
            cfg['id'] = nc.id
        if nc.initial_state:
            try:
                cfg['initial_state'] = dict(nc.initial_state)
            except Exception:
                pass
        if nc.timeout is not None:
            cfg['timeout'] = nc.timeout
    # Agent extras
    if _infer_node_type(node) == 'Agent':
        try:
            # Avoid non-serializable callables
            cfg['model'] = getattr(node, 'model', None)
            cfg['prompt'] = getattr(node, 'prompt', None)
            cfg['max_steps'] = getattr(node, 'max_steps', None)
            cfg['memory_policy'] = getattr(node, '_memory_policy', None)
            cfg['memory_window'] = getattr(node, '_memory_window', None)
        except Exception:
            pass
    # Filter Nones
    return {k: v for k, v in cfg.items() if v is not None}


def _serialize_subgraph_node(node: BaseNode) -> Dict[str, Any]:
    """Serialize SubgraphNode runtime configuration into spec-friendly data."""
    config: Dict[str, Any] = {}
    graph_source = getattr(node, 'graph_source', None)
    if graph_source:
        config['graph_source'] = graph_source

    graph_spec_payload = getattr(node, 'graph_spec_payload', None)
    if graph_spec_payload:
        config['graph_spec'] = graph_spec_payload
    elif not graph_source:
        template = getattr(node, '_graph_template', None)
        if template is None:
            raise ValueError("SubgraphNode requires a graph_spec or graph_source for serialization.")
        config['graph_spec'] = graph_to_spec(template).model_dump()

    input_mapping = getattr(node, 'input_mapping', None)
    if input_mapping:
        config['input_mapping'] = dict(input_mapping)
    output_mapping = getattr(node, 'output_mapping', None)
    if output_mapping:
        config['output_mapping'] = dict(output_mapping)

    config['share_state'] = getattr(node, 'share_state', True)
    config['share_event_bus'] = getattr(node, 'share_event_bus', False)
    return config


def _collect_nodes_from_edges(edges: List[Edge]) -> List[BaseNode]:
    nodes: Dict[str, BaseNode] = {}
    for e in edges:
        nodes.setdefault(e.from_node.id, e.from_node)
        if e.to_node is not None:
            nodes.setdefault(e.to_node.id, e.to_node)
    # Stable order by id for deterministic output
    return [nodes[k] for k in sorted(nodes.keys())]


def _condition_to_spec(condition: Optional[Any]) -> Optional[ConditionSpec]:
    cond = condition
    if cond is None:
        return None
    # Prefer equals/expr if set
    equals = getattr(cond, 'equals', None)
    if equals:
        try:
            return ConditionSpec(kind='equals', equals=dict(equals))
        except Exception:
            pass
    expr = getattr(cond, 'expr', None)
    if expr:
        return ConditionSpec(kind='expr', expr=str(expr))
    # Fallback to python callable repr
    fn = getattr(cond, 'condition', None)
    if fn is None:
        return None
    try:
        rep = repr(fn)
    except Exception:
        rep = '<callable>'
    return ConditionSpec(kind='python', python_repr=rep)


def _edge_condition_to_spec(edge: Edge) -> Optional[ConditionSpec]:
    return _condition_to_spec(getattr(edge, 'condition', None))


def node_to_spec(node: BaseNode) -> NodeSpec:
    """Convert a runtime `BaseNode` instance to a `NodeSpec`.

    Performs type-specific serialization for Agents, RpcNodes, JoinNodes, etc.
    Falls back to basic serialization for unknown node types.
    """
    node_type = _infer_node_type(node)
    node_id = str(node.id)
    description = getattr(node, 'description', None) or None

    # Type-specific serialization
    if node_type == 'SubgraphNode':
        config_dict = _serialize_subgraph_node(node)
    elif node_type == 'Agent':
        # Use comprehensive agent serialization
        agent_config = agent_config_to_spec(node)
        if agent_config:
            config_dict = agent_config.model_dump(exclude_none=True)
        else:
            config_dict = _safe_config_from_node(node)
    else:
        # Use basic config extraction for other node types
        config_dict = _safe_config_from_node(node)

    return NodeSpec(
        id=node_id,
        type=node_type,
        description=description,
        inputs=None,
        outputs=None,
        config=config_dict or None,
    )


def edge_to_spec(edge: Edge) -> Optional[EdgeSpec]:
    """Convert a runtime `Edge` instance to an `EdgeSpec`, skipping dangling edges."""
    if edge.to_node is None:
        # Skip dangling edges in export
        return None
    cond = _edge_condition_to_spec(edge)
    return EdgeSpec(
        id=str(edge.id),
        from_id=edge.from_node.id,
        to_id=edge.to_node.id,
        description=edge.description or None,
        priority=getattr(edge, 'priority', 0) or 0,
        condition=cond,
        delay_seconds=getattr(edge, 'delay_seconds', None),
        event_topic=getattr(edge, 'event_topic', None),
        event_filter=_condition_to_spec(getattr(edge, 'event_filter', None)),
    )


def graph_to_spec(graph: BaseGraph, *, spark_version: str = '2.0') -> GraphSpec:
    """Create a `GraphSpec` from an in-memory `BaseGraph`.

    Enhanced in Phase 2 to include:
    - GraphState configuration
    - GraphEventBus configuration
    - Graph-level tool definitions
    - Complete node serialization with type-specific handling
    """
    # Prefer graph.edges as source of truth
    edges: List[Edge] = list(getattr(graph, 'edges', []) or [])
    # Nodes present in edges; if empty, attempt to use graph.nodes
    if edges:
        nodes = _collect_nodes_from_edges(edges)
    else:
        node_set = list(getattr(graph, 'nodes', []) or [])
        # Filter to BaseNode instances, stable order by id
        nodes = sorted([n for n in node_set if isinstance(n, BaseNode)], key=lambda n: str(n.id))

    node_specs = [node_to_spec(n) for n in nodes]
    edge_specs = [es for e in edges if (es := edge_to_spec(e)) is not None]

    start = getattr(graph, 'start', None)
    start_id = start.id if isinstance(start, BaseNode) else (nodes[0].id if nodes else '')

    # Serialize GraphState if present
    graph_state_spec = None
    graph_state = getattr(graph, 'state', None)
    if graph_state:
        try:
            initial_state = graph_state.get_snapshot()
            backend = getattr(graph_state, '_backend', None)
            concurrent_mode = bool(getattr(backend, '_concurrent_mode', False))
            backend_info = graph_state.describe_backend()
            backend_spec = StateBackendConfigSpec(
                name=backend_info.get('name', 'memory'),
                options=backend_info.get('config', {}),
                serializer=backend_info.get('serializer', 'json'),
            )
            schema_info = graph_state.describe_schema()
            schema_spec = MissionStateSchemaSpec(**schema_info) if schema_info else None
            checkpoint_cfg = getattr(graph, 'get_checkpoint_config', None)
            checkpoint_spec = None
            if callable(checkpoint_cfg):
                cfg = checkpoint_cfg()
                if cfg:
                    checkpoint_spec = StateCheckpointSpec(**cfg.to_serializable())
            graph_state_spec = GraphStateSpec(
                initial_state=initial_state,
                concurrent_mode=concurrent_mode,
                backend=backend_spec,
                schema=schema_spec,
                checkpointing=checkpoint_spec,
                persistence='disk' if backend_spec.name in ('sqlite', 'file') else 'memory',
            )
        except Exception as e:
            logger.debug(f"Could not serialize GraphState: %s", e)

    # Serialize GraphEventBus if present
    event_bus_spec = None
    event_bus = getattr(graph, 'event_bus', None)
    if event_bus:
        try:
            enabled = True  # If it exists, it's enabled
            buffer_size = getattr(event_bus, 'buffer_size', 100)
            event_bus_spec = GraphEventBusSpec(
                enabled=enabled,
                buffer_size=buffer_size
            )
        except Exception as e:
            logger.debug(f"Could not serialize GraphEventBus: {e}")

    # Collect graph-level tools (from all agents)
    tool_specs: List[ToolDefinitionSpec] = []
    for node in nodes:
        if _infer_node_type(node) == 'Agent':
            tool_registry = getattr(node, 'tool_registry', None)
            if tool_registry:
                all_tools = getattr(tool_registry, 'registry', {})
                for tool_name, tool_obj in all_tools.items():
                    tool_spec = tool_to_spec(tool_obj)
                    if tool_spec and tool_spec not in tool_specs:
                        tool_specs.append(tool_spec)

    return GraphSpec(
        spark_version=spark_version,
        id=str(getattr(graph, 'id', 'graph')),
        description=getattr(graph, 'description', None) or None,
        start=str(start_id),
        nodes=node_specs,
        edges=edge_specs,
        graph_state=graph_state_spec,
        event_bus=event_bus_spec,
        tools=tool_specs,
    )


def graph_to_json(graph: BaseGraph, *, spark_version: str = '2.0', indent: int = 2) -> str:
    """Serialize a graph to a JSON string using spec field names."""
    spec = graph_to_spec(graph, spark_version=spark_version)
    payload = spec.model_dump_standard()
    # Late import to avoid hard dependency for consumers who use Python APIs only
    import json as _json

    return _json.dumps(payload, ensure_ascii=False, indent=indent)


def save_graph_json(path: str, graph: BaseGraph, *, spark_version: str = '2.0', indent: int = 2) -> None:
    """Write the JSON representation of a graph to the given file path."""
    content = graph_to_json(graph, spark_version=spark_version, indent=indent)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def load_graph_spec(path: str) -> GraphSpec:
    """Load and validate a `GraphSpec` from a JSON file path."""
    import json as _json

    with open(path, 'r', encoding='utf-8') as f:
        data = _json.load(f)
    return GraphSpec.model_validate(data)


def mission_spec_to_json(mission: MissionSpec, *, indent: int = 2) -> str:
    """Serialize a MissionSpec to JSON string."""
    import json as _json

    return _json.dumps(mission.model_dump(), ensure_ascii=False, indent=indent)


def save_mission_spec(path: str, mission: MissionSpec, *, indent: int = 2) -> None:
    """Write MissionSpec JSON payload to disk."""
    content = mission_spec_to_json(mission, indent=indent)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def load_mission_spec(path: str) -> MissionSpec:
    """Load MissionSpec JSON from disk and validate."""
    import json as _json

    with open(path, 'r', encoding='utf-8') as f:
        data = _json.load(f)
    return MissionSpec.model_validate(data)
