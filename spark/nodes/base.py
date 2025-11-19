"""
Base types for the Spark framework.
"""

import ast
import functools
import inspect
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional, Union
from uuid import UUID, uuid4

from spark.nodes.types import NodeMessage, ExecutionContext, NodeState, default_node_state
from spark.nodes.channels import BaseChannel, InMemoryChannel

try:  # Optional telemetry instrumentation
    from spark.telemetry.instrumentation import instrument_edge_transition
except ImportError:  # pragma: no cover - optional dependency
    instrument_edge_transition = None

if TYPE_CHECKING:
    from spark.graphs.event_bus import GraphEventBus


class SparkError(Exception):
    """General Spark Error"""


def wrap_sync_method(fn):
    """Wrap a sync method to an async method."""

    if inspect.iscoroutinefunction(fn):
        return fn

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


class BaseNode(ABC):
    """
    The base class for all nodes in the Spark framework.
    A node represents an actor in the Spark graph.
    It is a single unit of computation.
    """

    _process_no_arg: bool = False
    """indicate if the process method can be called without arguments"""

    _process_item_no_arg: bool = False
    """indicate if the process_item method can be called without arguments"""

    def __init_subclass__(cls, **kwargs):
        """
        if subclass process has not arg other than self, set self._process_no_arg = True
        Note to AI: you should always write a process method that takes a context argument.
        This is just for lazy human programmers.
        """
        super().__init_subclass__(**kwargs)
        process_impl = getattr(cls, 'process', None)
        is_abstract = getattr(process_impl, "__isabstractmethod__", False)
        if process_impl and not is_abstract:
            process_sig = inspect.signature(process_impl)
            if len(process_sig.parameters) < 2:
                setattr(cls, '_process_no_arg', True)

        process_item_impl = getattr(cls, 'process_item', None)
        is_abstract = getattr(process_item_impl, "__isabstractmethod__", False)
        if process_item_impl and not is_abstract:
            process_item_sig = inspect.signature(process_item_impl)
            if len(process_item_sig.parameters) < 2:
                setattr(cls, '_process_item_no_arg', True)

    def __init__(self, **kwargs) -> None:
        """Initialize the node with optional parameters."""
        self.id = kwargs.get('id', uuid4().hex)
        self.description = kwargs.get('description', '')

        # mailbox for receiving messages when running in live mode
        self.mailbox: BaseChannel = kwargs.get(
            'mailbox',
            InMemoryChannel(name=f'node:{self.__class__.__name__}:{self.id}'),
        )

        # outputs of the node, to be used by the next nodes
        self.outputs = NodeMessage(content=None)

        self._state: NodeState = default_node_state()
        self.pre_process_hooks: list[Callable[[ExecutionContext], None]] = []
        self.post_process_hooks: list[Callable[[ExecutionContext], None]] = []
        self.human_policy = None
        self.edges: list[Edge] = []
        self.event_bus: GraphEventBus | None = None
        self.policy_engine = kwargs.get('policy_engine')

    def __repr__(self):
        """Return a string representation of the node."""
        return f"Node(name={self.__class__.__name__}, outputs={self.outputs}, edges={self.edges})"

    @property
    def state(self) -> NodeState:
        """Return the current state of the node."""
        return self._state

    @abstractmethod
    async def process(self, context: ExecutionContext) -> Any:
        """
        Process the context and return the output.
        This method must be implemented by subclasses.
        """

    async def _process(self, context: ExecutionContext) -> Any:
        """Wrap the process method to an async method."""
        process_fn = wrap_sync_method(self.process)
        self._state['process_count'] += 1
        if self._process_no_arg:
            return await process_fn()  # type: ignore
        return await process_fn(context)

    def _prepare_context(self, inputs: NodeMessage) -> ExecutionContext:
        """Prepare the execution context from inputs."""
        if not isinstance(inputs, NodeMessage):
            raise TypeError("inputs must be a Message")
        context = ExecutionContext(inputs=inputs, state=self._state)

        # Attach graph state if available
        graph_state = getattr(self, '_graph_state', None)
        if graph_state is not None:
            context.graph_state = graph_state

        return context

    def get_next_nodes(self) -> list['BaseNode']:
        """Get the next nodes based on conditions and priorities."""
        return [edge.to_node for edge in self.iter_active_edges() if edge.to_node]

    def iter_active_edges(self, include_event_edges: bool = False) -> list['Edge']:
        """Iterate edges that should fire based on their conditions."""
        sorted_edges = sorted(self.edges, key=lambda edge: -edge.priority)
        active_edges: list['Edge'] = []
        for edge in sorted_edges:
            if not edge.to_node:
                continue
            if edge.is_event_driven and not include_event_edges:
                continue
            if edge.condition.check(self):
                active_edges.append(edge)
        return active_edges

    def pop_ready_input(self) -> Any | None:
        """Return the next pre-staged input payload, if any.

        Graph schedulers call this before `run()` to allow nodes with custom
        buffering (e.g., join/barrier nodes) to supply the merged input that
        should be fed into their lifecycle. Base nodes return ``None`` to signal
        that schedulers should fall back to their default behaviour.
        """
        if self._state['pending_inputs']:
            return self._state['pending_inputs'].popleft()
        return None

    async def receive_from_parent(self, parent: 'BaseNode') -> bool:
        """Receive input from parent node."""
        payload = parent.outputs
        self.enqueue_input(payload)
        return True

    def enqueue_input(self, payload: NodeMessage | dict[str, Any] | list[dict[str, Any]] | None) -> None:
        """Append a payload to this node's pending input queue."""
        if payload is None:
            message = NodeMessage(content='', metadata={})
        elif isinstance(payload, NodeMessage):
            message = payload
        else:
            message = NodeMessage(content=payload, metadata={})
        self._state['pending_inputs'].append(message)

    def _record_snapshot(self, context: ExecutionContext) -> None:
        """Record a snapshot of the context."""
        self._state['context_snapshot'] = context.snapshot()

    def _pre_process(self, context: ExecutionContext) -> None:
        """Pre-process the context.
        This method is called before the process method.
        """
        for hook in self.pre_process_hooks:
            hook(context)

    def _post_process(self, context: ExecutionContext) -> NodeMessage:
        """Post-process the result.
        This method is called after the process method.
        """
        for hook in self.post_process_hooks:
            hook(context)
        if isinstance(context.outputs, NodeMessage):
            return context.outputs
        return NodeMessage(content=context.outputs)

    async def do(self, inputs: NodeMessage | dict[str, Any] | list[dict[str, Any]] | None = None) -> NodeMessage:
        """Run the node's processing logic.

        The default implementation simply calls the _process method, which is a wrapper of the process method.
        Nodes that require more complex setup or teardown can override this method.
        """
        if inputs is None:
            inputs = NodeMessage(content='', metadata={})
        elif not isinstance(inputs, NodeMessage):
            inputs = NodeMessage(content=inputs, metadata={})
        context = self._prepare_context(inputs)
        self._pre_process(context)

        # do everything here
        result = await self._process(context)
        result = await self._maybe_collect_human_input(context, result)

        context.outputs = result
        self.outputs = self._post_process(context)
        self._record_snapshot(context)
        return self.outputs

    async def go(self) -> Any:
        """Start running the node continuously."""
        raise NotImplementedError("go method is not implemented for this node.")

    async def _maybe_collect_human_input(self, context: ExecutionContext, result: Any) -> Any:
        """Hook for subclasses to collect human input after processing."""
        return result

    def attach_event_bus(self, event_bus: 'GraphEventBus') -> None:
        """Attach a graph-level event bus for pub/sub communication."""
        self.event_bus = event_bus

    async def publish_event(self, topic: str, payload: Any, *, metadata: Optional[dict[str, Any]] = None) -> None:
        """Publish an event if an event bus is configured."""
        if self.event_bus is None:
            return
        await self.event_bus.publish(
            topic,
            payload,
            metadata=metadata
            or {
                'node_id': self.id,
                'node_name': getattr(self, 'name', None),
            },
        )

    async def subscribe_event(self, topic: str):
        """Subscribe to a topic on the attached event bus."""
        if self.event_bus is None:
            raise RuntimeError('Event bus is not attached to this node')
        return await self.event_bus.subscribe(topic)

    def _normalize_edge_condition(
        self,
        *,
        condition: Optional[Union[str, 'EdgeCondition']] = None,
        expr: Optional[str] = None,
        equals: Optional[dict[str, Any]] = None,
        allow_empty: bool = False,
    ) -> Optional['EdgeCondition']:
        """Normalize heterogeneous inputs into an `EdgeCondition`."""

        if equals:
            return EdgeCondition(equals=dict(equals))
        if expr:
            return EdgeCondition(expr=expr)
        if condition is None:
            return None if allow_empty else EdgeCondition()
        if isinstance(condition, str):
            return EdgeCondition(expr=condition)
        if isinstance(condition, EdgeCondition):
            return condition
        if callable(condition):
            raise TypeError(
                "Lambda/callable conditions are not supported for spec compatibility. "
                "Use expr='...' or equals={...} instead.\n"
                "Example: node.on(expr='$.outputs.score > 0.5') >> next_node"
            )
        raise TypeError(f"Invalid condition type: {type(condition)}")

    def on(self, condition: Optional[Union[str, 'EdgeCondition']] = None, expr: Optional[str] = None, priority: int = 0, **equals: Any) -> 'Edge':
        """Create a conditional edge without specifying the target node yet."""

        normalized = self._normalize_edge_condition(
            condition=condition,
            expr=expr,
            equals=equals if equals else None,
        )
        return Edge(from_node=self, condition=normalized or EdgeCondition(), priority=priority)

    def on_timer(
        self,
        seconds: float,
        *,
        condition: Optional[Union[str, 'EdgeCondition']] = None,
        expr: Optional[str] = None,
        priority: int = 0,
        **equals: Any,
    ) -> 'Edge':
        """Create an edge that fires after the given delay."""

        if seconds < 0:
            raise ValueError("Timer delay must be non-negative")
        normalized = self._normalize_edge_condition(
            condition=condition,
            expr=expr,
            equals=equals if equals else None,
        )
        edge = Edge(from_node=self, condition=normalized or EdgeCondition(), priority=priority)
        edge.delay_seconds = seconds
        return edge

    def on_event(
        self,
        topic: str,
        *,
        event_filter: Optional[Union[str, 'EdgeCondition']] = None,
        expr: Optional[str] = None,
        priority: int = 0,
        **equals: Any,
    ) -> 'Edge':
        """Create an edge that activates when an event is published."""

        edge = Edge(from_node=self, condition=EdgeCondition(), priority=priority)
        edge.event_topic = topic
        normalized = self._normalize_edge_condition(
            condition=event_filter,
            expr=expr,
            equals=equals if equals else None,
            allow_empty=True,
        )
        edge.event_filter = normalized
        return edge

    def __rshift__(self, right: Union['BaseNode', 'Chain']) -> 'Chain':
        """Overload >> operator to add a next node / edge / chain."""
        if isinstance(right, Chain):
            edge = Edge(from_node=self, to_node=right.nodes[0], condition=EdgeCondition(None))
            right.nodes.insert(0, self)
            return right
        # right is a node
        edge = Edge(from_node=self, to_node=right, condition=EdgeCondition(None))
        return Chain([self, right])

    def goto(
        self, next_node: 'BaseNode', condition: Optional[Union['EdgeCondition', str]] = None
    ) -> 'Edge':
        """Create an edge to the next node with an optional condition.

        Args:
            next_node: The target node
            condition: EdgeCondition or expression string (no callables)

        Returns:
            Edge connecting this node to next_node

        Examples:
            node.goto(next_node)  # Unconditional
            node.goto(next_node, EdgeCondition(expr="$.outputs.score > 0.5"))
            node.goto(next_node, condition="$.outputs.score > 0.5")  # Shorthand

        Note:
            Lambda/callable conditions are NOT supported for spec compatibility.
            Use EdgeCondition or expr string instead.

        Raises:
            TypeError: If a callable is provided
        """
        if condition is None:
            edge = Edge(from_node=self, condition=EdgeCondition(), to_node=next_node)
        elif isinstance(condition, EdgeCondition):
            edge = Edge(from_node=self, condition=condition, to_node=next_node)
        elif isinstance(condition, str):
            edge = Edge(from_node=self, condition=EdgeCondition(expr=condition), to_node=next_node)
        elif callable(condition):
            raise TypeError(
                "Lambda/callable conditions are not supported for spec compatibility. "
                "Use EdgeCondition or expr string instead.\n"
                "Example: node.goto(next_node, EdgeCondition(expr='$.outputs.score > 0.5'))"
            )
        else:
            raise TypeError(f"Invalid condition type: {type(condition)}")

        return edge


class Chain:
    """A Chain is a sequence of nodes for human programmers."""

    def __init__(self, nodes: list[BaseNode]) -> None:
        """Initialize the Chain with a list of nodes."""
        if not nodes or not all(isinstance(n, BaseNode) for n in nodes):
            raise SparkError("Chain must be initialized with a non-empty list of Node instances.")
        if len(nodes) < 2:
            raise SparkError("Chain must be initialized with at least 2 nodes.")
        self.nodes = nodes

    def __rshift__(self, right: Union[BaseNode, 'Chain']) -> 'Chain':
        """Use >> operator to connect to next node."""
        if isinstance(right, Chain):
            edge = Edge(from_node=self.nodes[-1], to_node=right.nodes[0])
            self.nodes.extend(right.nodes)
        else:
            edge = Edge(from_node=self.nodes[-1], to_node=right)
            self.nodes.append(right)
        return self


@dataclass
class EdgeCondition:
    """A condition that determines the next node to run.

    EdgeCondition supports two types of conditions for spec-compatible routing:
    - expr: Expression string (e.g., "$.outputs.score > 0.5")
    - equals: Dictionary for exact matching (e.g., {'action': 'search'})

    Note: Lambda/callable conditions are NOT supported for spec compatibility.
    Use expr or equals instead.

    Examples:
        # Expression-based
        EdgeCondition(expr="$.outputs.score > 0.5")
        EdgeCondition(expr="$.outputs.status == 'ready' and $.outputs.count >= 10")

        # Equality-based
        EdgeCondition(equals={'action': 'search'})
        EdgeCondition(equals={'status': 'ready', 'count': 10})
    """

    expr: str | None = None
    equals: dict[str, Any] | None = None

    def __post_init__(self):
        """Validate that at least one condition type is provided."""
        if self.expr is None and self.equals is None:
            # Allow no condition (always True)
            pass

    def check(self, node: BaseNode) -> bool:
        """Execute the condition check.

        Returns:
            True if condition passes, False otherwise
        """
        # equals shortcut on node.outputs
        # All key/value pairs must match (AND logic, not OR)
        if self.equals:
            if node.outputs and node.outputs.content:
                data = node.outputs.content
            else:
                data = {}
            try:
                if not isinstance(data, dict):
                    return False
                # Check that ALL key/value pairs match
                for k, v in self.equals.items():
                    if data.get(k) != v:
                        return False
                return True
            except Exception:
                return False

        # Expression evaluator
        if self.expr:
            try:
                return self._eval_expr(node, self.expr)
            except Exception:
                return False

        # No condition means always True
        return True

    def _eval_expr(self, node: BaseNode, expr: str) -> bool:
        """Evaluate expression-based routing conditions.

        Supports:
        - Comparison: ==, !=, >, <, >=, <=
        - Logical: and, or, not
        - Membership: in
        - Nested paths: $.outputs.nested.key
        - Examples:
          - $.outputs.score > 0.5
          - $.outputs.status == 'ready' and $.outputs.count >= 10
          - $.outputs.category in ['A', 'B', 'C']
          - not $.outputs.failed
        """
        # Handle logical operators (and, or) by splitting and recursing
        if ' and ' in expr:
            parts = expr.split(' and ', 1)
            return self._eval_expr(node, parts[0].strip()) and self._eval_expr(node, parts[1].strip())

        if ' or ' in expr:
            parts = expr.split(' or ', 1)
            return self._eval_expr(node, parts[0].strip()) or self._eval_expr(node, parts[1].strip())

        # Handle not operator
        if expr.strip().startswith('not '):
            inner = expr.strip()[4:].strip()
            # Check if inner is a boolean field access (no comparison)
            bool_field_match = re.match(r"^\s*\$\.(inputs|outputs)\.(?P<path>[a-zA-Z_][\w\.-]*)\s*$", inner)
            if bool_field_match:
                container = bool_field_match.group(1)
                path = bool_field_match.group('path')
                source = self._get_source(node, container)
                if source is None:
                    return False
                value = self._get_nested(source, path)
                # Truthiness check
                return not bool(value)
            return not self._eval_expr(node, inner)

        # Handle membership operator (in)
        # Pattern: $.outputs.key in [value1, value2, ...]
        in_match = re.match(r"^\s*\$\.(inputs|outputs)\.(?P<path>[a-zA-Z_][\w\.-]*)\s+in\s+(?P<rhs>.+?)\s*$", expr)
        if in_match:
            container = in_match.group(1)
            path = in_match.group('path')
            rhs_raw = in_match.group('rhs')
            rhs = self._parse_literal(rhs_raw)
            source = self._get_source(node, container)
            if source is None:
                return False
            value = self._get_nested(source, path)
            if not isinstance(rhs, (list, tuple, set)):
                return False
            return value in rhs

        # Handle comparison operators
        # Pattern: $.outputs.key <op> value
        comparison_pattern = (
            r"^\s*\$\.(inputs|outputs)\.(?P<path>[a-zA-Z_][\w\.-]*)\s*(?P<op>==|!=|>=|<=|>|<)\s*(?P<rhs>.+?)\s*$"
        )
        comp_match = re.match(comparison_pattern, expr)
        if comp_match:
            container = comp_match.group(1)
            path = comp_match.group('path')
            op = comp_match.group('op')
            rhs_raw = comp_match.group('rhs')
            rhs = self._parse_literal(rhs_raw)

            source = self._get_source(node, container)
            if source is None:
                return False

            value = self._get_nested(source, path)

            # Perform comparison
            try:
                if op == '==':
                    return value == rhs
                elif op == '!=':
                    return value != rhs
                elif op == '>':
                    return value > rhs
                elif op == '<':
                    return value < rhs
                elif op == '>=':
                    return value >= rhs
                elif op == '<=':
                    return value <= rhs
                else:
                    return False
            except (TypeError, AttributeError):
                # Comparison failed (e.g., comparing incompatible types)
                return False

        # Handle direct boolean field access (no comparison operator)
        # Pattern: $.outputs.key (for truthiness check)
        bool_field_match = re.match(r"^\s*\$\.(inputs|outputs)\.(?P<path>[a-zA-Z_][\w\.-]*)\s*$", expr)
        if bool_field_match:
            container = bool_field_match.group(1)
            path = bool_field_match.group('path')
            source = self._get_source(node, container)
            if source is None:
                return False
            value = self._get_nested(source, path)
            return bool(value)

        # If no pattern matched, return False
        return False

    def _get_source(self, node: BaseNode, container: str) -> dict | None:
        """Get the source container (inputs or outputs) from the node."""
        if container == "outputs":
            source = node.outputs
            if hasattr(source, 'content'):
                return source.content if isinstance(source.content, dict) else None
            return source if isinstance(source, dict) else None
        # Note: inputs not currently accessible from node, only outputs
        return None

    @staticmethod
    def _parse_literal(s: str) -> Any:
        s = s.strip()
        lowered = s.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if lowered in {"null", "none"}:
            return None
        try:
            return ast.literal_eval(s)
        except Exception:
            if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
                return s[1:-1]
            return s

    @staticmethod
    def _get_nested(d: Mapping[str, Any] | Any, path: str) -> Any:
        """Get nested value from dictionary using dot-separated path.

        Examples:
        - path='key' -> d['key']
        - path='nested.key' -> d['nested']['key']
        - path='deep.nested.key' -> d['deep']['nested']['key']
        """
        if d is None:
            return None

        # Handle NodeMessage wrapper
        if hasattr(d, 'content') and isinstance(d.content, dict):
            d = d.content

        if not isinstance(d, Mapping):
            return None

        cur: Any = d
        for part in path.split('.'):
            if cur is None:
                return None
            if not isinstance(cur, Mapping):
                return None
            cur = cur.get(part)
        return cur


@dataclass
class Edge:
    """Represents a child node connection with edge conditions and priority."""

    from_node: BaseNode
    to_node: BaseNode | None = None
    id: UUID = field(default_factory=uuid4)
    description: str = field(default='')
    condition: EdgeCondition = field(default_factory=EdgeCondition)
    priority: int = 0
    channel: BaseChannel | None = None
    channel_config: dict[str, Any] = field(default_factory=dict)
    delay_seconds: float | None = None
    event_topic: str | None = None
    event_filter: EdgeCondition | None = None

    def __post_init__(self):
        """Add this edge to the from_node's edges list."""
        self.from_node.edges.append(self)

    def __rshift__(self, right: Union['Edge', 'BaseNode', 'Chain']) -> 'Chain':
        """Overload >> operator to add a next node / edge / chain."""
        if self.to_node is not None:
            raise SparkError("Edge already has a to_node")
        if isinstance(right, Chain):
            # Connect to the first node of the chain
            first = right.nodes[0]
            self.to_node = first
            # If the chain already starts with from_node, no need to insert
            if right.nodes[0] is not self.from_node:
                right.nodes.insert(0, self.from_node)
            return right
        if isinstance(right, BaseNode):
            self.to_node = right
            return Chain([self.from_node, right])
        # right is an edge
        self.to_node = right.from_node
        chain = Chain([self.from_node, right.from_node])
        if right.to_node:
            chain.nodes.append(right.to_node)
        return chain

    def configure_channel(self, **config: Any) -> 'Edge':
        """Attach configuration hints used when building per-edge channels."""
        self.channel_config.update(config)
        return self

    @property
    def is_event_driven(self) -> bool:
        return self.event_topic is not None
