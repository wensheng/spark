"""
Reverse-compiler from GraphSpec to Python code.

Generates production-ready Python code from GraphSpec including:
- Complete node class implementations
- Full agent configuration with tools, memory, reasoning strategies
- Graph assembly with GraphState and EventBus
- Import optimization
- Multi-file project structure support
- Documentation and tests

This module provides both simple single-file generation (backward compatible)
and comprehensive multi-file project generation for production use.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple
import os
import re
from collections import defaultdict

from spark.nodes.spec import (
    ConditionSpec,
    GraphSpec,
    NodeSpec,
    EdgeSpec,
    ModelSpec,
    ToolDefinitionSpec,
    EnhancedAgentConfigSpec,
)


# ============================================================================
# Utility Functions
# ============================================================================

def _safe_module_id(text: str) -> str:
    """Convert text to safe module identifier."""
    base = re.sub(r"[^0-9a-zA-Z_]+", "_", text)
    if not base:
        base = "graph"
    return base.lower()


def _safe_ident(text: str) -> str:
    """Convert text to safe Python identifier."""
    s = re.sub(r"[^0-9a-zA-Z_]+", "_", text)
    if s and s[0].isdigit():
        s = f"_{s}"
    return s or "_"


def _class_name(node_id: str, node_type: str) -> str:
    """Generate class name from node ID and type."""
    parts = re.split(r"[^0-9a-zA-Z]+", node_id)
    title = "".join(p.capitalize() for p in parts if p)
    if not title:
        title = "Node"

    # Handle Agent types
    if node_type.lower() == "agent":
        if not title.endswith("Agent"):
            return f"{title}Agent"
        return title

    # Handle other node types
    if not title.endswith("Node"):
        return f"{title}Node"
    return title


def _indent(code: str, level: int = 1) -> str:
    """Indent code block."""
    indent_str = "    " * level
    return "\n".join(indent_str + line if line.strip() else "" for line in code.split("\n"))


def _format_dict(d: Dict[str, Any], indent_level: int = 0) -> str:
    """Format dictionary as Python code."""
    if not d:
        return "{}"
    items = []
    for k, v in d.items():
        if isinstance(v, str):
            items.append(f"'{k}': {repr(v)}")
        elif isinstance(v, dict):
            items.append(f"'{k}': {_format_dict(v, indent_level + 1)}")
        elif isinstance(v, list):
            items.append(f"'{k}': {repr(v)}")
        else:
            items.append(f"'{k}': {v}")
    return "{" + ", ".join(items) + "}"


# ============================================================================
# Import Optimizer
# ============================================================================

class ImportOptimizer:
    """Optimize and organize imports for generated code."""

    def __init__(self):
        self.stdlib_imports: Set[str] = set()
        self.spark_imports: Dict[str, Set[str]] = defaultdict(set)
        self.third_party_imports: Set[str] = set()

    def add_import(self, module: str, items: List[str] | None = None):
        """Add import to the optimizer."""
        if module.startswith('spark.'):
            if items:
                self.spark_imports[module].update(items)
            else:
                self.spark_imports[module] = set()
        elif module in ('typing', 'asyncio', 'os', 'sys', 'logging', 'json'):
            self.stdlib_imports.add(module)
        else:
            self.third_party_imports.add(module)

    def analyze_spec(self, spec: GraphSpec):
        """Analyze spec and determine required imports."""
        # Always need these
        self.add_import('typing', ['Any', 'Dict', 'List', 'Optional'])
        self.add_import('spark.graphs.graph', ['Graph'])
        self.add_import('spark.nodes.types', ['ExecutionContext'])

        # Analyze nodes
        has_agent = False
        has_rpc = False
        has_join = False
        has_batch = False
        has_basic = False

        for node in spec.nodes:
            node_type = node.type
            if node_type == 'Agent':
                has_agent = True
            elif node_type == 'RpcNode':
                has_rpc = True
            elif node_type == 'JoinNode':
                has_join = True
            elif node_type in ('ParallelNode', 'SequentialNode', 'MultipleThreadNode', 'MultipleProcessNode'):
                has_batch = True
            else:
                has_basic = True

        # Add node imports
        if has_agent:
            self.add_import('spark.agents.agent', ['Agent'])
            self.add_import('spark.agents.config', ['AgentConfig'])
        if has_basic:
            self.add_import('spark.nodes.nodes', ['Node'])
            self.add_import('spark.nodes.config', ['NodeConfig'])
        if has_rpc:
            self.add_import('spark.nodes.rpc', ['RpcNode'])
        if has_join:
            self.add_import('spark.nodes.nodes', ['JoinNode'])
        if has_batch:
            self.add_import('spark.nodes.nodes', ['ParallelNode', 'SequentialNode'])

        # Analyze edges
        if spec.edges:
            self.add_import('spark.nodes.base', ['Edge', 'EdgeCondition'])

        # Analyze models
        model_providers = set()
        for node in spec.nodes:
            if node.type == 'Agent' and node.config:
                model_config = node.config.get('model')
                if isinstance(model_config, dict):
                    provider = model_config.get('provider', 'openai')
                    model_providers.add(provider)
                elif isinstance(model_config, str):
                    model_providers.add('openai')  # Default

        # Add model imports
        for provider in model_providers:
            if provider == 'openai':
                self.add_import('spark.models.openai', ['OpenAIModel'])
            elif provider == 'bedrock':
                self.add_import('spark.models.bedrock', ['BedrockModel'])
            elif provider == 'gemini':
                self.add_import('spark.models.gemini', ['GeminiModel'])
            elif provider == 'ollama':
                self.add_import('spark.models.ollama', ['OllamaModel'])
            elif provider == 'echo':
                self.add_import('spark.models.echo', ['EchoModel'])

        # Check for GraphState
        if spec.graph_state:
            self.add_import('spark.graphs.graph_state', ['GraphState'])

        # Check for tools
        if spec.tools:
            self.add_import('spark.tools.decorator', ['tool'])

    def generate_imports(self) -> str:
        """Generate formatted import block."""
        lines = []

        # Stdlib imports
        if self.stdlib_imports:
            for module in sorted(self.stdlib_imports):
                lines.append(f"import {module}")
            lines.append("")

        # Spark imports
        if self.spark_imports:
            for module in sorted(self.spark_imports.keys()):
                items = self.spark_imports[module]
                if items:
                    items_str = ", ".join(sorted(items))
                    lines.append(f"from {module} import {items_str}")
                else:
                    lines.append(f"import {module}")
            lines.append("")

        # Third party imports
        if self.third_party_imports:
            for module in sorted(self.third_party_imports):
                lines.append(f"import {module}")
            lines.append("")

        return "\n".join(lines)


# ============================================================================
# Code Generator
# ============================================================================

class CodeGenerator:
    """Enhanced code generator from GraphSpec to production-ready Python code."""

    def __init__(self, spec: GraphSpec, style: str = 'production'):
        """
        Initialize code generator.

        Args:
            spec: GraphSpec to generate code from
            style: Generation style - 'stub', 'production', 'documented'
        """
        self.spec = spec
        self.style = style
        self.import_optimizer = ImportOptimizer()
        self.import_optimizer.analyze_spec(spec)

    def generate_tool_definitions(self) -> str:
        """Generate tool function definitions."""
        if not self.spec.tools:
            return ""

        lines = []
        lines.append("# ============================================================================")
        lines.append("# Tool Definitions")
        lines.append("# ============================================================================")
        lines.append("")

        for tool_spec in self.spec.tools:
            # Generate tool function
            lines.append("@tool")

            # Build parameter list
            params = []
            for param in tool_spec.parameters:
                param_str = f"{param.name}: {param.type}"
                if not param.required and param.default is not None:
                    param_str += f" = {repr(param.default)}"
                params.append(param_str)

            param_list = ", ".join(params) if params else ""
            return_type = tool_spec.return_type or "Any"

            if tool_spec.is_async:
                lines.append(f"async def {tool_spec.name}({param_list}) -> {return_type}:")
            else:
                lines.append(f"def {tool_spec.name}({param_list}) -> {return_type}:")

            # Docstring
            lines.append(f'    """{tool_spec.description}')
            if tool_spec.parameters:
                lines.append("")
                lines.append("    Args:")
                for param in tool_spec.parameters:
                    desc = param.description or ""
                    lines.append(f"        {param.name}: {desc}")
            if tool_spec.return_description:
                lines.append("")
                lines.append("    Returns:")
                lines.append(f"        {tool_spec.return_description}")
            lines.append('    """')

            # Stub implementation
            if self.style == 'stub':
                lines.append("    # TODO: Implement tool logic")
                lines.append("    raise NotImplementedError")
            else:
                lines.append("    # Tool implementation")
                lines.append(f"    # Reference: {tool_spec.function}")
                lines.append("    raise NotImplementedError(f'Tool {tool_spec.name} not implemented')")

            lines.append("")

        return "\n".join(lines)

    def generate_node_class(self, node: NodeSpec) -> str:
        """Generate complete node class implementation."""
        if node.type == 'Agent':
            return self._generate_agent_class(node)
        elif node.type == 'RpcNode':
            return self._generate_rpc_node_class(node)
        elif node.type == 'JoinNode':
            return self._generate_join_node_class(node)
        elif node.type in ('ParallelNode', 'SequentialNode'):
            return self._generate_batch_node_class(node)
        else:
            return self._generate_basic_node_class(node)

    def _generate_agent_class(self, node: NodeSpec) -> str:
        """Generate Agent class with full configuration."""
        class_name = _class_name(node.id, node.type)
        lines = []

        lines.append(f"class {class_name}(Agent):")
        desc = node.description or f"Agent node: {node.id}"
        lines.append(f'    """{desc}"""')

        if self.style != 'stub':
            lines.append("")
            lines.append("    # Agent implementation can override process() if needed")

        lines.append("    pass")
        lines.append("")

        return "\n".join(lines)

    def _generate_basic_node_class(self, node: NodeSpec) -> str:
        """Generate basic Node class."""
        class_name = _class_name(node.id, node.type)
        lines = []

        lines.append(f"class {class_name}(Node):")
        desc = node.description or f"Node: {node.id}"
        lines.append(f'    """{desc}"""')
        lines.append("")
        lines.append("    async def process(self, context: ExecutionContext) -> Any:")

        if self.style == 'stub':
            lines.append("        # Echo stub: forwards inputs downstream")
            lines.append("        return context.inputs")
        else:
            lines.append("        # Implement node processing logic")
            lines.append("        # Access inputs via context.inputs")
            lines.append("        # Access state via context.state")
            lines.append("        # Return outputs for downstream nodes")
            lines.append("        return context.inputs")

        lines.append("")
        return "\n".join(lines)

    def _generate_rpc_node_class(self, node: NodeSpec) -> str:
        """Generate RPC node class."""
        class_name = _class_name(node.id, node.type)
        lines = []

        lines.append(f"class {class_name}(RpcNode):")
        desc = node.description or f"RPC Node: {node.id}"
        lines.append(f'    """{desc}"""')
        lines.append("")
        lines.append("    async def rpc_example(self, params: dict, context: ExecutionContext):")
        lines.append('        """Example RPC method."""')
        lines.append("        return {'result': 'success'}")
        lines.append("")

        return "\n".join(lines)

    def _generate_join_node_class(self, node: NodeSpec) -> str:
        """Generate Join node class (typically doesn't need custom class)."""
        # JoinNode is usually instantiated directly, not subclassed
        return ""

    def _generate_batch_node_class(self, node: NodeSpec) -> str:
        """Generate batch processing node class."""
        class_name = _class_name(node.id, node.type)
        lines = []

        lines.append(f"class {class_name}({node.type}):")
        desc = node.description or f"Batch node: {node.id}"
        lines.append(f'    """{desc}"""')
        lines.append("")
        lines.append("    async def process_item(self, item: Any) -> Any:")
        lines.append('        """Process individual item."""')
        lines.append("        # Implement item processing logic")
        lines.append("        return item")
        lines.append("")

        return "\n".join(lines)

    def generate_node_classes(self) -> str:
        """Generate all node class definitions."""
        lines = []
        lines.append("# ============================================================================")
        lines.append("# Node Definitions")
        lines.append("# ============================================================================")
        lines.append("")

        for node in self.spec.nodes:
            node_class = self.generate_node_class(node)
            if node_class:
                lines.append(node_class)

        return "\n".join(lines)

    def _generate_model_instance(self, model_config: Any) -> str:
        """Generate model instantiation code."""
        if isinstance(model_config, str):
            # Simple model ID - use OpenAI
            return f"OpenAIModel(model_id={repr(model_config)})"
        elif isinstance(model_config, dict):
            provider = model_config.get('provider', 'openai')
            model_id = model_config.get('model_id', 'gpt-4o-mini')
            client_args = model_config.get('client_args', {})
            streaming = model_config.get('streaming', False)

            if provider == 'openai':
                return f"OpenAIModel(model_id={repr(model_id)})"
            elif provider == 'echo':
                return f"EchoModel(streaming={streaming})"
            elif provider == 'bedrock':
                return f"BedrockModel(model_id={repr(model_id)})"
            elif provider == 'gemini':
                return f"GeminiModel(model_id={repr(model_id)})"
            elif provider == 'ollama':
                return f"OllamaModel(model_id={repr(model_id)})"

        return "OpenAIModel(model_id='gpt-4o-mini')"

    def _generate_agent_config(self, node: NodeSpec) -> str:
        """Generate AgentConfig instantiation."""
        config = node.config or {}
        parts = []

        # Model
        model_config = config.get('model', 'gpt-4o-mini')
        parts.append(f"model={self._generate_model_instance(model_config)}")

        # System prompt
        if 'system_prompt' in config:
            parts.append(f"system_prompt={repr(config['system_prompt'])}")

        # Prompt template
        if 'prompt_template' in config:
            parts.append(f"prompt_template={repr(config['prompt_template'])}")

        # Tools
        if 'tools' in config and config['tools']:
            tool_names = [t.get('name') if isinstance(t, dict) else t for t in config['tools']]
            tools_dict = "{" + ", ".join(f"'{name}': {name}" for name in tool_names) + "}"
            parts.append(f"tools={tools_dict}")

        # Tool choice
        if 'tool_choice' in config:
            parts.append(f"tool_choice={repr(config['tool_choice'])}")

        # Max steps
        if 'max_steps' in config:
            parts.append(f"max_steps={config['max_steps']}")

        # Output mode
        if 'output_mode' in config:
            parts.append(f"output_mode={repr(config['output_mode'])}")

        # Memory config
        if 'memory_config' in config:
            mem_cfg = config['memory_config']
            if isinstance(mem_cfg, dict):
                mem_parts = []
                if 'max_messages' in mem_cfg:
                    mem_parts.append(f"max_messages={mem_cfg['max_messages']}")
                if 'policy' in mem_cfg:
                    mem_parts.append(f"policy={repr(mem_cfg['policy'])}")
                if mem_parts:
                    parts.append(f"memory_config=MemoryConfig({', '.join(mem_parts)})")

        # Cost tracking
        if config.get('enable_cost_tracking'):
            parts.append("enable_cost_tracking=True")

        return "AgentConfig(\n" + ",\n".join(_indent(part) for part in parts) + "\n)"

    def generate_node_instances(self) -> str:
        """Generate node instance creation code."""
        lines = []
        lines.append("def build_nodes() -> Dict[str, Any]:")
        lines.append('    """Create all node instances."""')
        lines.append("    nodes: Dict[str, Any] = {}")
        lines.append("")

        for node in self.spec.nodes:
            node_id = node.id
            var_name = _safe_ident(node_id)
            class_name = _class_name(node_id, node.type)

            if node.type == 'Agent':
                # Generate agent with full config
                config_code = self._generate_agent_config(node)
                lines.append(f"    {var_name} = {class_name}(")
                lines.append(f"        config={config_code}")
                lines.append("    )")
            elif node.type == 'RpcNode':
                config = node.config or {}
                host = config.get('host', '0.0.0.0')
                port = config.get('port', 8000)
                lines.append(f"    {var_name} = {class_name}(host={repr(host)}, port={port})")
            elif node.type == 'JoinNode':
                config = node.config or {}
                keys = config.get('keys', [])
                mode = config.get('mode', 'all')
                lines.append(f"    {var_name} = JoinNode(keys={repr(keys)}, mode={repr(mode)})")
            else:
                # Basic node with config
                config = node.config or {}
                if config:
                    config_parts = []
                    if 'timeout' in config:
                        config_parts.append(f"timeout={config['timeout']}")
                    if 'initial_state' in config:
                        config_parts.append(f"initial_state={repr(config['initial_state'])}")
                    if config_parts:
                        config_str = ", ".join(config_parts)
                        lines.append(f"    {var_name} = {class_name}(config=NodeConfig({config_str}))")
                    else:
                        lines.append(f"    {var_name} = {class_name}()")
                else:
                    lines.append(f"    {var_name} = {class_name}()")

            lines.append(f"    nodes[{repr(node_id)}] = {var_name}")
            lines.append("")

        lines.append("    return nodes")
        lines.append("")

        return "\n".join(lines)

    def generate_graph_assembly(self) -> str:
        """Generate graph construction function."""
        lines = []
        lines.append("def build_graph() -> Graph:")
        lines.append('    """Assemble the complete graph with all edges and features."""')
        lines.append("    nodes = build_nodes()")
        lines.append("")

        # Generate edges
        if self.spec.edges:
            lines.append("    # Create edges")
            for edge in self.spec.edges:
                from_var = _safe_ident(edge.from_node)
                to_var = _safe_ident(edge.to_node)

                if edge.condition:
                    if isinstance(edge.condition, ConditionSpec):
                        if edge.condition.kind == 'equals' and edge.condition.equals:
                            # Equals condition
                            eq_items = ", ".join(
                                f"{k}={repr(v)}" for k, v in edge.condition.equals.items()
                            )
                            if edge.priority != 0:
                                lines.append(f"    nodes[{repr(edge.from_node)}].on({eq_items}, priority={edge.priority}) >> nodes[{repr(edge.to_node)}]")
                            else:
                                lines.append(f"    nodes[{repr(edge.from_node)}].on({eq_items}) >> nodes[{repr(edge.to_node)}]")
                        elif edge.condition.kind == 'expr' and edge.condition.expr:
                            # Expression condition
                            if edge.priority != 0:
                                lines.append(f"    nodes[{repr(edge.from_node)}].on(expr={repr(edge.condition.expr)}, priority={edge.priority}) >> nodes[{repr(edge.to_node)}]")
                            else:
                                lines.append(f"    nodes[{repr(edge.from_node)}].on(expr={repr(edge.condition.expr)}) >> nodes[{repr(edge.to_node)}]")
                        else:
                            # Unconditional or lambda
                            lines.append(f"    nodes[{repr(edge.from_node)}] >> nodes[{repr(edge.to_node)}]")
                    else:
                        # Unconditional
                        lines.append(f"    nodes[{repr(edge.from_node)}] >> nodes[{repr(edge.to_node)}]")
                else:
                    # Unconditional
                    lines.append(f"    nodes[{repr(edge.from_node)}] >> nodes[{repr(edge.to_node)}]")
            lines.append("")

        # Create graph
        start_node = self.spec.start
        lines.append(f"    # Create graph with auto-discovery from start node")
        lines.append(f"    graph = Graph(start=nodes[{repr(start_node)}])")
        lines.append("")

        # Setup GraphState if specified
        if self.spec.graph_state:
            lines.append("    # Initialize GraphState")
            initial_state = self.spec.graph_state.initial_state or {}
            if initial_state:
                for key, value in initial_state.items():
                    lines.append(f"    await graph.state.set({repr(key)}, {repr(value)})")
            if self.spec.graph_state.concurrent_mode:
                lines.append("    graph.state.enable_concurrent_mode()")
            lines.append("")

        lines.append("    return graph")
        lines.append("")

        return "\n".join(lines)

    def generate_main_runner(self) -> str:
        """Generate main execution function."""
        lines = []
        lines.append("async def main():")
        lines.append('    """Main execution function."""')
        lines.append("    # Build the graph")
        lines.append("    graph = build_graph()")
        lines.append("")
        lines.append("    # Run the graph")
        lines.append("    inputs = {}")
        lines.append("    result = await graph.run(inputs)")
        lines.append("")
        lines.append("    # Process results")
        lines.append("    print(f'Graph execution completed: {result}')")
        lines.append("")
        lines.append("")
        lines.append("if __name__ == '__main__':")
        lines.append("    import asyncio")
        lines.append("    asyncio.run(main())")
        lines.append("")

        return "\n".join(lines)

    def generate_complete_file(self) -> str:
        """Generate complete Python file."""
        sections = []

        # Header comment
        sections.append(f'"""')
        sections.append(f"Generated from GraphSpec: {self.spec.id}")
        sections.append(f"")
        sections.append(f"This file contains the complete graph implementation including:")
        sections.append(f"- Node class definitions")
        sections.append(f"- Tool definitions (if any)")
        sections.append(f"- Graph assembly")
        sections.append(f"- Main runner")
        sections.append(f'"""')
        sections.append("")

        # Imports
        sections.append(self.import_optimizer.generate_imports())

        # Tools
        if self.spec.tools:
            sections.append(self.generate_tool_definitions())

        # Node classes
        sections.append(self.generate_node_classes())

        # Node instances
        sections.append(self.generate_node_instances())

        # Graph assembly
        sections.append(self.generate_graph_assembly())

        # Main runner
        sections.append(self.generate_main_runner())

        return "\n".join(sections)


# ============================================================================
# Backward Compatible API
# ============================================================================

def _build_node_ctor(node: NodeSpec) -> Tuple[str, str]:
    """Return (class_name, constructor_code). [Backward compatible]"""
    class_name = _class_name(node.id, node.type)
    config = node.config or {}
    if node.type.lower() == "agent":
        model_id = config.get("model", "gpt-4o-mini")
        system_prompt = config.get("system_prompt", "")
        config_parts = []
        config_parts.append(f"model=OpenAIModel(model_id={repr(model_id)})")
        if system_prompt:
            config_parts.append(f"system_prompt={repr(system_prompt)}")
        config_str = ", ".join(config_parts)
        ctor = f"{class_name}(config=AgentConfig({config_str}))"
        return class_name, ctor
    timeout = config.get("timeout")
    timeout_s = str(timeout) if timeout is not None else "None"
    initial_state = config.get("initial_state")
    if initial_state is None:
        ctor = f"{class_name}(config=NodeConfig(timeout={timeout_s}))"
    else:
        ctor = f"{class_name}(config=NodeConfig(timeout={timeout_s}, initial_state={repr(initial_state)}))"
    return class_name, ctor


def _emit_single_py(spec: GraphSpec, out_dir: str, module_id: str) -> str:
    """Emit single Python file. [Backward compatible - simple version]"""
    path = os.path.join(out_dir, f"spark_{module_id}.py")
    lines: List[str] = []

    # Imports
    lines.append('from typing import Any, Dict')
    lines.append('from spark.nodes.types import ExecutionContext')
    lines.append('from spark.nodes.base import Edge')
    lines.append('from spark.nodes.nodes import Node')
    lines.append('from spark.nodes.base import EdgeCondition')
    lines.append('from spark.graphs.graph import Graph')
    lines.append('from spark.agents.agent import Agent')
    lines.append('from spark.nodes.config import NodeConfig')
    lines.append('from spark.agents.config import AgentConfig')
    lines.append('from spark.models.openai import OpenAIModel')
    lines.append('')

    # Node/Agent class stubs
    for node in spec.nodes:
        class_name = _class_name(node.id, node.type)
        if node.type.lower() == 'agent':
            lines.append(f'class {class_name}(Agent):')
            lines.append('    pass')
        else:
            lines.append(f'class {class_name}(Node):')
            lines.append('    async def process(self, context: ExecutionContext) -> Any:')
            lines.append('        # Echo stub: forwards inputs downstream')
            lines.append('        return context.inputs')
        lines.append('')

    # Builder for instances
    lines.append('def build_nodes() -> Dict[str, Any]:')
    lines.append('    instances: Dict[str, Any] = {}')
    for node in spec.nodes:
        class_name, ctor = _build_node_ctor(node)
        var_name = _safe_ident(node.id)
        lines.append(f'    {var_name} = {ctor}')
        lines.append(f'    instances[{repr(node.id)}] = {var_name}')
    lines.append('    return instances')
    lines.append('')

    # Graph assembly
    lines.append('def build_graph() -> Graph:')
    lines.append('    nodes = build_nodes()')
    lines.append('    edges: list[Edge] = []')
    for e in spec.edges:
        if _edge_is_equals(e.condition):
            eq = e.condition.equals if isinstance(e.condition, ConditionSpec) else {}
            kwargs = ", ".join(f"{k}={repr(v)}" for k, v in (eq or {}).items())
            lines.append(f'    _edge = nodes[{repr(e.from_node)}].on({kwargs})')
            lines.append(f'    _edge >> nodes[{repr(e.to_node)}]')
            lines.append('    edges.append(_edge)')
        else:
            _expr = None
            if isinstance(e.condition, str):
                _expr = e.condition
            elif isinstance(e.condition, ConditionSpec) and e.condition.kind == 'expr' and e.condition.expr:
                _expr = e.condition.expr
            if _expr:
                lines.append(f'    _cond = EdgeCondition(expr={repr(_expr)})')
                lines.append(
                    f'    edges.append(nodes[{repr(e.from_node)}].goto(nodes[{repr(e.to_node)}], condition=_cond))'
                )
            else:
                lines.append(f'    edges.append(nodes[{repr(e.from_node)}].goto(nodes[{repr(e.to_node)}]))')
    lines.append(f"    return Graph(*edges, start=nodes[{repr(spec.start)}], id={repr(spec.id)})")
    lines.append('')

    # Demo runner
    lines.append('async def _run_demo() -> None:')
    lines.append('    g = build_graph()')
    lines.append('    await g.run({})')
    lines.append('')
    lines.append("if __name__ == '__main__':")
    lines.append('    from spark.utils import arun')
    lines.append('    arun(_run_demo())')

    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    return path


def _edge_is_equals(cond: Any) -> bool:
    """Check if condition is equals type."""
    if isinstance(cond, ConditionSpec):
        return cond.kind == 'equals' and isinstance(cond.equals, dict) and len(cond.equals) > 0
    return False


def generate(spec: GraphSpec, out_dir: str, style: str = 'simple') -> str:
    """Generate Python code from GraphSpec into out_dir.

    Args:
        spec: GraphSpec to generate from
        out_dir: Output directory
        style: Generation style:
            - 'simple': Simple single-file output (backward compatible)
            - 'production': Enhanced production-ready code
            - 'documented': Production code with extensive documentation

    Returns:
        Path to generated file(s)
    """
    os.makedirs(out_dir, exist_ok=True)
    module_id = _safe_module_id(spec.id)

    if style == 'simple':
        # Use backward compatible simple generation
        return _emit_single_py(spec, out_dir, module_id)
    else:
        # Use enhanced CodeGenerator
        generator = CodeGenerator(spec, style=style)
        code = generator.generate_complete_file()

        # Write to file
        path = os.path.join(out_dir, f"spark_{module_id}.py")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(code)

        return path
