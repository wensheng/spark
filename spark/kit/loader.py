"""
Spec → Runtime deserialization.

This module provides utilities to load GraphSpec instances back into
executable runtime graphs with all their configuration.

Phase 2 Enhancement: Full-fidelity bidirectional conversion.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from spark.nodes.spec import (
    GraphSpec,
    NodeSpec,
    EdgeSpec,
    ConditionSpec,
    ModelSpec,
    ToolDefinitionSpec,
    EnhancedAgentConfigSpec,
)
from spark.nodes.base import BaseNode, Edge, EdgeCondition
from spark.nodes.types import ExecutionContext
from spark.graphs.graph import Graph, SubgraphNode
from spark.graphs.checkpoint import GraphCheckpointConfig
from spark.graphs.state_backend import create_state_backend
from spark.utils.import_utils import import_from_ref, import_class_from_ref, ImportError as ImportResolutionError
from spark.tools.simulation.stubs import PlaceholderTool

logger = logging.getLogger(__name__)


class GenericNode(BaseNode):
    """Generic concrete node for deserialization of unknown node types."""

    def __init__(self, description: str | None = None):
        super().__init__()
        self.description = description

    async def process(self, context: ExecutionContext):
        """Simple pass-through process."""
        return context.inputs


class SpecLoaderError(Exception):
    """Base exception for spec loader errors."""
    pass


class SpecLoader:
    """Load runtime objects from specifications.

    Handles deserialization of GraphSpec back into executable runtime
    graphs, nodes, edges, and configurations.

    Example:
        loader = SpecLoader()
        spec = GraphSpec.model_validate_json(json_data)
        graph = loader.load_graph(spec)
        await graph.run(inputs={'query': 'test'})
    """

    def __init__(self, import_policy: str = 'safe', simulation_mode: bool = False):
        """Initialize the spec loader.

        Args:
            import_policy: Import safety policy ('safe' or 'allow_all')
                'safe' only allows imports from spark.* modules
                'allow_all' allows any module imports
            simulation_mode: When True, skip importing real tools and use placeholders.
        """
        self.import_policy = import_policy
        self.tool_cache: Dict[str, Any] = {}
        self.model_cache: Dict[str, Any] = {}
        self.node_cache: Dict[str, BaseNode] = {}
        self.simulation_mode = simulation_mode

    def load_model(self, model_spec: ModelSpec | str) -> Any:
        """Instantiate model from spec.

        Args:
            model_spec: ModelSpec instance or model ID string

        Returns:
            Model instance (OpenAIModel, BedrockModel, etc.)

        Raises:
            SpecLoaderError: If model cannot be loaded
        """
        try:
            from spark.models.openai import OpenAIModel
            from spark.models.bedrock import BedrockModel
            from spark.models.gemini import GeminiModel
            from spark.models.echo import EchoModel

            # Handle simple string model ID
            if isinstance(model_spec, str):
                # Check cache for string model IDs
                cache_key = f"openai:{model_spec}"
                if cache_key in self.model_cache:
                    return self.model_cache[cache_key]

                # Use OpenAI as default provider
                model = OpenAIModel(model_id=model_spec)
                self.model_cache[cache_key] = model
                return model

            # Check cache for ModelSpec
            cache_key = f"{model_spec.provider}:{model_spec.model_id}"
            if cache_key in self.model_cache:
                return self.model_cache[cache_key]

            # Create model based on provider
            provider_map = {
                'openai': OpenAIModel,
                'bedrock': BedrockModel,
                'gemini': GeminiModel,
                'echo': EchoModel,
            }

            model_class = provider_map.get(model_spec.provider)
            if not model_class:
                raise SpecLoaderError(f"Unknown model provider: {model_spec.provider}")

            # Instantiate model - handle EchoModel specially
            if model_spec.provider == 'echo':
                # EchoModel only accepts streaming parameter
                model = EchoModel(streaming=model_spec.streaming)
            else:
                model = model_class(
                    model_id=model_spec.model_id,
                    **model_spec.client_args
                )

            # Cache and return
            self.model_cache[cache_key] = model
            return model

        except Exception as e:
            raise SpecLoaderError(f"Failed to load model from spec: {e}") from e

    def load_tool(self, tool_source: str) -> Any:
        """Load tool function from source reference.

        Args:
            tool_source: Module:function reference (e.g., 'myapp.tools:search')

        Returns:
            Tool function or BaseTool instance

        Raises:
            SpecLoaderError: If tool cannot be loaded
        """
        try:
            # Check cache
            if tool_source in self.tool_cache:
                return self.tool_cache[tool_source]

            # Validate import based on policy
            if self.import_policy == 'safe':
                # Only allow spark.* imports for safety
                if not (tool_source.startswith('spark.') or tool_source.startswith('tools:')):
                    logger.warning(
                        f"Skipping tool import '{tool_source}' due to safe import policy. "
                        "Use import_policy='allow_all' to enable."
                    )
                    return None

            # Import the tool
            tool_obj = import_from_ref(tool_source)

            # Cache and return
            self.tool_cache[tool_source] = tool_obj
            return tool_obj

        except Exception as e:
            logger.warning(f"Failed to load tool from '{tool_source}': {e}")
            return None

    def load_node(self, node_spec: NodeSpec) -> BaseNode:
        """Construct node from spec.

        Args:
            node_spec: NodeSpec instance

        Returns:
            BaseNode instance

        Raises:
            SpecLoaderError: If node cannot be constructed
        """
        try:
            # Check cache
            if node_spec.id in self.node_cache:
                return self.node_cache[node_spec.id]

            node_type = node_spec.type
            config = node_spec.config or {}

            # Handle different node types
            if node_type == 'Agent':
                node = self._load_agent_node(node_spec, config)
            elif node_type == 'RpcNode':
                from spark.nodes.rpc import RpcNode
                node = RpcNode(
                    host=config.get('host', '0.0.0.0'),
                    port=config.get('port', 8000)
                )
            elif node_type == 'JoinNode':
                from spark.nodes.nodes import JoinNode
                node = JoinNode(
                    keys=config.get('keys', []),
                    mode=config.get('mode', 'all')
                )
            elif node_type == 'SubgraphNode':
                node = self._load_subgraph_node(node_spec, config)
            else:
                # Generic/unknown node types - use GenericNode
                node = GenericNode(description=node_spec.description)

            # Set node ID
            node.id = node_spec.id

            # Cache and return
            self.node_cache[node_spec.id] = node
            return node

        except Exception as e:
            raise SpecLoaderError(f"Failed to load node '{node_spec.id}': {e}") from e

    def _load_agent_node(self, node_spec: NodeSpec, config: Dict[str, Any]) -> BaseNode:
        """Load an Agent node with full configuration.

        Args:
            node_spec: NodeSpec for the agent
            config: Agent configuration dictionary

        Returns:
            Agent instance
        """
        from spark.agents.agent import Agent
        from spark.agents.config import AgentConfig
        from spark.agents.memory import MemoryConfig

        try:
            # Load model
            model_spec = config.get('model')
            if isinstance(model_spec, dict):
                model = self.load_model(ModelSpec(**model_spec))
            else:
                model = self.load_model(model_spec or 'gpt-4o-mini')

            # Load tools
            tools = []
            tool_specs = config.get('tools', [])
            for index, tool_spec in enumerate(tool_specs):
                if self.simulation_mode:
                    placeholder_name = tool_spec.get('name') or f"{node_spec.id}_tool_{index}"
                    tools.append(PlaceholderTool(placeholder_name))
                    continue
                tool_source = tool_spec.get('source')
                if tool_source:
                    tool = self.load_tool(tool_source)
                    if tool:
                        tools.append(tool)

            # Load memory config
            memory_config_dict = config.get('memory_config', {})
            memory_config = MemoryConfig(
                policy=memory_config_dict.get('policy', 'rolling_window'),
                window=memory_config_dict.get('window', 10),
                summary_max_chars=memory_config_dict.get('summary_max_chars', 1000)
            )

            # Load reasoning strategy
            reasoning_strategy = None
            strategy_spec = config.get('reasoning_strategy')
            if strategy_spec:
                strategy_type = strategy_spec.get('type')
                if strategy_type in ('noop', 'react', 'chain_of_thought'):
                    # Use string name - AgentConfig will resolve it
                    reasoning_strategy = strategy_type
                elif strategy_type == 'custom':
                    custom_class = strategy_spec.get('custom_class')
                    if custom_class:
                        try:
                            reasoning_strategy = import_from_ref(custom_class)
                        except Exception as e:
                            logger.warning(f"Could not load custom strategy '{custom_class}': {e}")

            # Create AgentConfig
            agent_config = AgentConfig(
                model=model,
                name=config.get('name'),
                description=config.get('description'),
                system_prompt=config.get('system_prompt'),
                prompt_template=config.get('prompt_template'),
                tools=tools,
                tool_choice=config.get('tool_choice', 'auto'),
                max_steps=config.get('max_steps', 100),
                parallel_tool_execution=config.get('parallel_tool_execution', False),
                output_mode=config.get('output_config', {}).get('mode', 'text'),
                memory_config=memory_config,
                reasoning_strategy=reasoning_strategy,
                preload_messages=config.get('preload_messages', [])
            )

            # Create Agent
            agent = Agent(config=agent_config)
            return agent

        except Exception as e:
            raise SpecLoaderError(f"Failed to load Agent node: {e}") from e

    def _load_subgraph_node(self, node_spec: NodeSpec, config: Dict[str, Any]) -> BaseNode:
        """Load a SubgraphNode from spec configuration."""
        try:
            graph_obj: Graph
            subgraph_spec = None
            if 'graph_spec' in config and config['graph_spec'] is not None:
                subgraph_spec = GraphSpec.model_validate(config['graph_spec'])
                sub_loader = SpecLoader(import_policy=self.import_policy)
                graph_obj = sub_loader.load_graph(subgraph_spec)
            elif config.get('graph_source'):
                graph_obj = self._load_graph_from_source(config['graph_source'])
            else:
                raise SpecLoaderError(
                    f"SubgraphNode '{node_spec.id}' requires either 'graph_spec' or 'graph_source'."
                )

            node = SubgraphNode(
                graph=graph_obj,
                input_mapping=config.get('input_mapping'),
                output_mapping=config.get('output_mapping'),
                share_state=config.get('share_state', True),
                share_event_bus=config.get('share_event_bus', False),
                graph_spec=subgraph_spec,
                graph_source=config.get('graph_source'),
            )
            return node
        except Exception as e:
            raise SpecLoaderError(f"Failed to load Subgraph node '{node_spec.id}': {e}") from e

    def load_edge_condition(self, condition_spec: Optional[ConditionSpec]) -> Optional[EdgeCondition]:
        """Load edge condition from spec.

        Args:
            condition_spec: ConditionSpec or None

        Returns:
            EdgeCondition instance or None
        """
        if condition_spec is None:
            return None

        try:
            if condition_spec.kind == 'expr':
                return EdgeCondition(expr=condition_spec.expr)
            elif condition_spec.kind == 'equals':
                return EdgeCondition(equals=condition_spec.equals)
            elif condition_spec.kind == 'always':
                return EdgeCondition(condition=lambda n: True)
            else:
                # lambda and python kinds not directly loadable
                logger.warning(f"Cannot load condition kind '{condition_spec.kind}' from spec")
                return None
        except Exception as e:
            logger.warning(f"Failed to load edge condition: {e}")
            return None

    def load_graph(self, graph_spec: GraphSpec) -> Graph:
        """Construct complete graph from spec.

        Args:
            graph_spec: GraphSpec instance

        Returns:
            Executable Graph instance

        Raises:
            SpecLoaderError: If graph cannot be constructed
        """
        try:
            # Clear caches for fresh load
            self.node_cache.clear()

            # Load all nodes
            nodes: Dict[str, BaseNode] = {}
            for node_spec in graph_spec.nodes:
                node = self.load_node(node_spec)
                nodes[node_spec.id] = node

            # Get start node
            if graph_spec.start not in nodes:
                raise SpecLoaderError(f"Start node '{graph_spec.start}' not found in graph")
            start_node = nodes[graph_spec.start]

            # Create edges
            edges: List[Edge] = []
            for edge_spec in graph_spec.edges:
                from_node = nodes.get(edge_spec.from_node)
                to_node = nodes.get(edge_spec.to_node)

                if not from_node or not to_node:
                    logger.warning(
                        f"Skipping edge '{edge_spec.id}': "
                        f"missing from_node or to_node"
                    )
                    continue

                # Load condition
                condition = None
                if edge_spec.condition:
                    if isinstance(edge_spec.condition, str):
                        # Simple expr string
                        condition = EdgeCondition(expr=edge_spec.condition)
                    else:
                        condition = self.load_edge_condition(edge_spec.condition)
                else:
                    condition = EdgeCondition()

                # Create edge
                edge = Edge(
                    from_node=from_node,
                    to_node=to_node,
                    condition=condition,
                    priority=edge_spec.priority,
                    description=edge_spec.description
                )
                if edge_spec.delay_seconds is not None:
                    edge.delay_seconds = edge_spec.delay_seconds
                if edge_spec.event_topic:
                    edge.event_topic = edge_spec.event_topic
                    if edge_spec.event_filter:
                        if isinstance(edge_spec.event_filter, str):
                            edge.event_filter = EdgeCondition(expr=edge_spec.event_filter)
                        else:
                            edge.event_filter = self.load_edge_condition(edge_spec.event_filter)
                edge.id = edge_spec.id
                edges.append(edge)

            initial_state: dict[str, Any] = {}
            state_backend_instance = None
            state_schema_model: type[BaseModel] | BaseModel | None = None
            checkpoint_config: GraphCheckpointConfig | None = None
            if graph_spec.graph_state:
                initial_state = dict(graph_spec.graph_state.initial_state or {})
                backend_spec = graph_spec.graph_state.backend
                if backend_spec:
                    state_backend_instance = create_state_backend(
                        backend_spec.name,
                        options=backend_spec.options,
                        serializer=backend_spec.serializer,
                    )
                schema_spec = graph_spec.graph_state.schema
                if schema_spec and schema_spec.module:
                    try:
                        schema_cls = import_class_from_ref(schema_spec.module)
                    except ImportResolutionError as exc:
                        raise SpecLoaderError(f"Failed to import mission state schema '{schema_spec.module}': {exc}") from exc
                    if not isinstance(schema_cls, type) or not issubclass(schema_cls, BaseModel):
                        raise SpecLoaderError(f"Schema reference '{schema_spec.module}' is not a Pydantic model.")
                    if schema_spec.name:
                        setattr(schema_cls, 'schema_name', schema_spec.name)
                    if schema_spec.version:
                        setattr(schema_cls, 'schema_version', schema_spec.version)
                    state_schema_model = schema_cls
                if graph_spec.graph_state.checkpointing:
                    checkpoint_config = GraphCheckpointConfig.from_dict(
                        graph_spec.graph_state.checkpointing.model_dump()
                    )

            # Create graph
            graph = Graph(
                *edges,
                start=start_node,
                initial_state=initial_state,
                state_backend=state_backend_instance,
                state_schema=state_schema_model,
                checkpoint_config=checkpoint_config,
            )
            graph.id = graph_spec.id
            if graph_spec.description:
                graph.description = graph_spec.description

            # Setup GraphState if specified
            if graph_spec.graph_state and graph_spec.graph_state.concurrent_mode:
                graph.state.enable_concurrent_mode()

            return graph

        except Exception as e:
            raise SpecLoaderError(f"Failed to load graph: {e}") from e

    def _load_graph_from_source(self, ref: str) -> Graph:
        """Load a Graph instance from a module reference."""
        try:
            graph_obj = import_from_ref(ref)
            if callable(graph_obj) and not isinstance(graph_obj, Graph):
                graph_obj = graph_obj()
            if not isinstance(graph_obj, Graph):
                raise SpecLoaderError(f"Reference '{ref}' did not return a Graph instance.")
            return graph_obj
        except SpecLoaderError:
            raise
        except Exception as e:
            raise SpecLoaderError(f"Failed to load graph from '{ref}': {e}") from e

    def validate_imports(self, spec: GraphSpec) -> List[str]:
        """Validate all module:attr references are loadable.

        Args:
            spec: GraphSpec to validate

        Returns:
            List of error messages (empty if all valid)
        """
        errors: List[str] = []

        # Check tools
        for tool_spec in spec.tools:
            result = self.load_tool(tool_spec.function)
            if result is None:
                errors.append(f"Tool '{tool_spec.name}' could not be loaded from '{tool_spec.function}'")

        # Check node configs
        for node_spec in spec.nodes:
            if node_spec.type == 'Agent' and node_spec.config:
                # Check agent tools
                tool_specs = node_spec.config.get('tools', [])
                for tool_cfg in tool_specs:
                    tool_source = tool_cfg.get('source')
                    if tool_source:
                        result = self.load_tool(tool_source)
                        if result is None:
                            errors.append(f"Agent '{node_spec.id}' tool '{tool_source}' could not be loaded")

        return errors
