"""
Base types for the Spark Node.
"""

from __future__ import annotations

import ast
import copy
import inspect
import re
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import MISSING, dataclass, field, fields, replace
from typing import (
    Any,
    ClassVar,
    TypeVar,
    cast,
)
from uuid import UUID, uuid4

from typing_extensions import TypedDict  # PEP 728, available > 4.10.0, available in Python 3.15

from spark.actor import Actor, ActorAddress
from spark.core.exceptions import ActorNotStartedError, SparkException
from spark.core.message import Message

_FORWARD_REPLY_TO_METADATA_KEY = "__spark_node_forward_reply_to__"
_FORWARDED_METADATA_KEY = "__spark_node_forwarded__"
_FANOUT_GROUP_METADATA_KEY = "__spark_node_fanout_group__"
_FANOUT_BRANCH_METADATA_KEY = "__spark_node_fanout_branch__"
_FANOUT_EXPECTED_METADATA_KEY = "__spark_node_fanout_expected__"


class NodeState(TypedDict, extra_items=Any):  # type: ignore[call-arg]
    """State of the node."""

    context_snapshot: dict[str, Any] | None
    processing: bool
    pending_inputs: deque[Message]
    process_count: int


# TypeVar for NodeState and its subclasses
TNodeState = TypeVar("TNodeState", bound=NodeState)
NodeHook = Callable[[Any, Any], Any | Awaitable[Any]]


def default_node_state(**kwargs) -> NodeState:
    """Create a default node state."""
    state: NodeState = {
        "context_snapshot": None,
        "processing": False,
        "pending_inputs": deque(),
        "process_count": 0,
    }
    state.update(kwargs)  # type: ignore
    return state


def _safe_copy(value: Any) -> Any:
    """Best-effort deep copy used when snapshotting context for errors."""
    try:
        return copy.deepcopy(value)
    except Exception:
        try:
            return copy.copy(value)
        except Exception:
            return value


@dataclass(slots=True)
class ExecutionMetadata:
    """Timing and attempt metadata captured for each run."""

    attempt: int = 1
    started_at: float | None = None
    finished_at: float | None = None

    def mark_started(self, attempt: int) -> None:
        """Mark the execution as started."""
        self.attempt = attempt
        self.started_at = time.perf_counter()
        self.finished_at = None

    def mark_finished(self) -> None:
        """Mark the execution as finished."""
        self.finished_at = time.perf_counter()

    @property
    def duration(self) -> float | None:
        """Get the duration of the execution."""
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at

    def as_dict(self) -> dict[str, Any]:
        """Convert the execution metadata to a dictionary."""
        return {
            "attempt": self.attempt,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration": self.duration,
        }


@dataclass(slots=True)
class NodeContext[TNodeState: NodeState]:
    """
    Per-invocation context for a node run.

    Framework internals pass this object through hooks, policies, validation, and
    post-processing. User node implementations access the active context through
    `self.context`.
    """

    inputs: Message = field(default_factory=Message)
    state: TNodeState = field(default_factory=default_node_state)  # type: ignore[assignment]
    metadata: ExecutionMetadata = field(default_factory=ExecutionMetadata)
    outputs: Any = None
    run_id: str | None = None

    def snapshot(self) -> dict[str, Any]:
        """Return a deep copy of the current state for diagnostics."""

        return _safe_copy(self.state)

    def fork(self) -> NodeContext[TNodeState]:
        """Produce a copy suitable for branch execution."""

        return NodeContext(
            inputs=_safe_copy(self.inputs),
            state=_safe_copy(self.state),
            metadata=replace(self.metadata),
            outputs=_safe_copy(self.outputs),
            run_id=self.run_id,
        )


@dataclass(slots=True)
class RouteContext:
    """Small routing surface used by edge conditions."""

    inputs: Any = None
    outputs: Any = None


def _is_node_instance(value: Any) -> bool:
    """Return True for runtime BaseNode instances without importing BaseNode at module load time."""

    base_node_type = globals().get("BaseNode")
    return isinstance(base_node_type, type) and isinstance(value, base_node_type)


class Chain:
    """A Chain is a sequence of nodes for human programmers."""

    def __init__(self, nodes: list[BaseNode]) -> None:
        """Initialize the Chain with a list of nodes."""
        if not nodes or not all(_is_node_instance(n) for n in nodes):
            raise SparkException("Chain must be initialized with a non-empty list of Node instances.")
        if len(nodes) < 2:
            raise SparkException("Chain must be initialized with at least 2 nodes.")
        self.nodes = nodes

    def __rshift__(self, right: BaseNode | Chain) -> Chain:
        """Use >> operator to connect to next node."""
        if isinstance(right, Chain):
            Edge(from_node=self.nodes[-1], to_node=right.nodes[0])
            self.nodes.extend(right.nodes)
        elif _is_node_instance(right):
            Edge(from_node=self.nodes[-1], to_node=right)
            self.nodes.append(right)
        else:
            raise SparkException("Chain can only be connected to a Node or Chain.")
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

    def check(self, node: Any) -> bool:
        """Execute the condition check.

        Returns:
            True if condition passes, False otherwise
        """
        # equals shortcut on node.outputs
        # All key/value pairs must match (AND logic, not OR)
        if self.equals:
            data = node.outputs or {}
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

    def _eval_expr(self, node: Any, expr: str) -> bool:
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
        if " and " in expr:
            parts = expr.split(" and ", 1)
            return self._eval_expr(node, parts[0].strip()) and self._eval_expr(node, parts[1].strip())

        if " or " in expr:
            parts = expr.split(" or ", 1)
            return self._eval_expr(node, parts[0].strip()) or self._eval_expr(node, parts[1].strip())

        # Handle not operator
        if expr.strip().startswith("not "):
            inner = expr.strip()[4:].strip()
            # Check if inner is a boolean field access (no comparison)
            bool_field_match = re.match(r"^\s*\$\.(?P<path>[a-zA-Z_][\w\.-]*)\s*$", inner)
            if bool_field_match:
                path = bool_field_match.group("path")
                value = self._resolve_path(node, path)
                # Truthiness check
                return not bool(value)
            return not self._eval_expr(node, inner)

        # Handle membership operator (in)
        # Pattern: $.outputs.key in [value1, value2, ...]
        in_match = re.match(r"^\s*\$(?:\.(?P<path>[a-zA-Z_][\w\.-]*))?\s+in\s+(?P<rhs>.+?)\s*$", expr)
        if in_match:
            path = in_match.group("path")
            rhs_raw = in_match.group("rhs")
            rhs = self._parse_literal(rhs_raw)
            value = self._resolve_path(node, path)
            if not isinstance(rhs, (list, tuple, set)):
                return False
            return value in rhs

        # Handle comparison operators
        # Pattern: $.outputs.key <op> value
        comparison_pattern = r"^\s*\$(?:\.(?P<path>[a-zA-Z_][\w\.-]*))?\s*(?P<op>==|!=|>=|<=|>|<)\s*(?P<rhs>.+?)\s*$"
        comp_match = re.match(comparison_pattern, expr)
        if comp_match:
            path = comp_match.group("path")
            op = comp_match.group("op")
            rhs_raw = comp_match.group("rhs")
            rhs = self._parse_literal(rhs_raw)

            value = self._resolve_path(node, path)

            # Perform comparison
            try:
                if op == "==":
                    return value == rhs
                if op == "!=":
                    return value != rhs
                if op == ">":
                    return value > rhs
                if op == "<":
                    return value < rhs
                if op == ">=":
                    return value >= rhs
                if op == "<=":
                    return value <= rhs
                return False
            except (TypeError, AttributeError):
                # Comparison failed (e.g., comparing incompatible types)
                return False

        # Handle direct boolean field access (no comparison operator)
        # Pattern: $.outputs.key (for truthiness check)
        bool_field_match = re.match(r"^\s*\$\.(?P<path>[a-zA-Z_][\w\.-]*)\s*$", expr)
        if bool_field_match:
            path = bool_field_match.group("path")
            value = self._resolve_path(node, path)
            return bool(value)

        # If no pattern matched, return False
        return False

    @staticmethod
    def _resolve_path(node: Any, path: str | None) -> Any:
        if path is None:
            return getattr(node, "outputs", node)

        root, separator, remainder = path.partition(".")
        if root in {"outputs", "output"} and hasattr(node, "outputs"):
            source = node.outputs
            return source if not separator else EdgeCondition._get_nested(source, remainder)
        if root in {"inputs", "input"} and hasattr(node, "inputs"):
            source = node.inputs
            return source if not separator else EdgeCondition._get_nested(source, remainder)

        source = getattr(node, "outputs", node)
        return EdgeCondition._get_nested(source, path)

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

        if not isinstance(d, Mapping) and hasattr(d, "content") and isinstance(d.content, dict):
            d = d.content

        if not isinstance(d, Mapping):
            return None

        cur: Any = d
        for part in path.split("."):
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
    description: str = field(default="")
    condition: EdgeCondition = field(default_factory=EdgeCondition)
    priority: int = 0
    delay_seconds: float | None = None
    event_filter: EdgeCondition | None = None

    def __post_init__(self):
        """Add this edge to the from_node's edges list."""
        self.from_node.edges.append(self)
        if self.to_node is not None:
            self.to_node._incoming_edges.append(self)

    def __rshift__(self, right: Edge | BaseNode | Chain) -> Chain:
        """Overload >> operator to add a next node / edge / chain."""
        if self.to_node is not None:
            raise SparkException("Edge already has a to_node")
        if isinstance(right, Chain):
            # Connect to the first node of the chain
            first = right.nodes[0]
            self.to_node = first
            first._incoming_edges.append(self)
            # If the chain already starts with from_node, no need to insert
            if right.nodes[0] is not self.from_node:
                right.nodes.insert(0, self.from_node)
            return right
        if _is_node_instance(right):
            node = cast("Node", right)
            self.to_node = node
            node._incoming_edges.append(self)
            return Chain([self.from_node, node])
        # right is an edge
        edge = cast("Edge", right)
        self.to_node = edge.from_node
        edge.from_node._incoming_edges.append(self)
        chain = Chain([self.from_node, edge.from_node])
        if edge.to_node:
            chain.nodes.append(edge.to_node)
        return chain


class NodeTimeoutError(SparkException):
    """Raised when a node stage exceeds its configured timeout."""

    def __init__(self, node: Any, stage: str, timeout: float | None) -> None:
        """Initialize the NodeTimeoutError."""
        self.node = node
        self.stage = stage
        self.timeout = timeout
        timeout_msg = f" after {timeout} seconds" if timeout is not None else ""
        super().__init__(f"Node {node.__class__.__name__} {stage} stage timed out{timeout_msg}.")


@dataclass
class NodeConfig:
    id: str = field(default_factory=lambda: uuid4().hex)
    type: str | None = None
    description: str | None = None

    state: NodeState = field(default_factory=default_node_state)

    # Policies for resilience and control
    # retry: RetryPolicy | None = None  # Keep as is
    # timeout: TimeoutPolicy | None = None  # Changed from float to TimeoutPolicy
    # rate_limiter: RateLimiterPolicy | None = None  # New field, replaces rate_limit, resource_key, registry
    # circuit_breaker: CircuitBreakerPolicy | None = None  # New field, replaces breaker_key, circuit_breaker, registry
    # idempotency: IdempotencyPolicy | None = None  # Changed from IdempotencyConfig to IdempotencyPolicy

    redact_keys: set[str] | None = None
    # event_sink: EventSink | None = None

    validators: tuple[Callable[[Mapping[str, Any]], None | str], ...] = ()

    pre_process_hooks: list[NodeHook] = field(default_factory=list)
    """Pre-process hook to be called before the process method."""

    post_process_hooks: list[NodeHook] = field(default_factory=list)
    """Post-process hook to be called after the process method."""

    keep_in_state: list[str] = field(default_factory=list)
    """List of input keys to keep in the state."""


def resolve_config_kwargs(inst: Node, config: NodeConfig | None, kwargs: dict[str, Any]) -> None:
    """Helper function to resolve configuration values from NodeConfig and kwargs."""
    if config is not None and not isinstance(config, NodeConfig):
        raise SparkException("Node config must be an instance of NodeConfig")

    def resolve_config_value(field_name: str, default: Any) -> Any:
        if field_name in kwargs:
            return kwargs[field_name]
        if config is not None:
            return getattr(config, field_name)
        return default

    for config_field in fields(NodeConfig):
        if config_field.default_factory is not MISSING:
            default = config_field.default_factory()
        elif config_field.default is not MISSING:
            default = config_field.default
        else:
            default = None
        value = resolve_config_value(config_field.name, default)
        setattr(inst, config_field.name, value)


class BaseNode(Actor):
    id: str
    type: str | None
    description: str | None
    state: NodeState
    redact_keys: set[str] | None
    validators: tuple[Callable[[Mapping[str, Any]], None | str], ...]
    pre_process_hooks: list[NodeHook]
    post_process_hooks: list[NodeHook]
    keep_in_state: list[str]

    def __init__(self) -> None:
        super().__init__()
        self.edges: list[Edge] = []
        self._incoming_edges: list[Edge] = []
        self._fanin_buffers: dict[str, dict[str, Message]] = {}
        self._last_inputs: Message | None = None
        self._outputs: Any = None

    def __rshift__(self, right: BaseNode | Edge | Chain) -> Chain:
        """Use ``node >> next_node`` syntax to connect graph nodes."""
        if isinstance(right, Chain):
            if right.nodes[0] is not self:
                Edge(from_node=self, to_node=right.nodes[0])
                right.nodes.insert(0, self)
            return right
        if isinstance(right, Edge):
            Edge(from_node=self, to_node=right.from_node)
            chain = Chain([self, right.from_node])
            if right.to_node is not None:
                chain.nodes.append(right.to_node)
            return chain
        if isinstance(right, BaseNode):
            Edge(from_node=self, to_node=right)
            return Chain([self, right])
        raise SparkException("Node can only be connected to a Node, Edge, or Chain.")

    @property
    def actor_context(self):
        """Return the actor runtime context, if this node is bound to an actor."""
        return self._require_context()

    @property
    def outputs(self) -> Any:
        """Return the outputs from the last process run."""
        return self._outputs

    def iter_active_edges(self) -> list[Edge]:
        """Iterate edges that should fire based on their conditions."""
        sorted_edges = sorted(self.edges, key=lambda edge: -edge.priority)
        route_context = RouteContext(inputs=self._last_inputs, outputs=self._outputs)
        active_edges: list[Edge] = []
        for edge in sorted_edges:
            if not edge.to_node:
                continue
            if edge.condition.check(route_context):
                active_edges.append(edge)
        return active_edges

    def get_next_nodes(self) -> list[BaseNode]:
        """Get the next nodes based on conditions and priorities."""
        return [edge.to_node for edge in self.iter_active_edges() if edge.to_node]

    def _normalize_edge_condition(
        self,
        *,
        condition: str | EdgeCondition | None = None,
        expr: str | None = None,
        equals: dict[str, Any] | None = None,
        allow_empty: bool = False,
    ) -> EdgeCondition | None:
        """Normalize heterogeneous inputs into an `EdgeCondition`."""

        styles = [
            condition is not None,
            expr is not None,
            bool(equals),
        ]
        if sum(styles) > 1:
            raise TypeError("Only one edge condition style may be provided: condition, expr, or equals kwargs.")

        if equals:
            return EdgeCondition(equals=dict(equals))
        if expr is not None:
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

    def on(
        self,
        condition: str | EdgeCondition | None = None,
        expr: str | None = None,
        priority: int = 0,
        **equals: Any,
    ) -> Edge:
        """Create a conditional edge without specifying the target node yet."""

        normalized = self._normalize_edge_condition(
            condition=condition,
            expr=expr,
            equals=equals if equals else None,
        )
        return Edge(from_node=self, condition=normalized or EdgeCondition(), priority=priority)

    def goto(
        self,
        next_node: BaseNode,
        condition: EdgeCondition | str | None = None,
        expr: str | None = None,
        priority: int = 0,
        **equals: Any,
    ) -> Edge:
        """Create an edge to the next node with an optional condition.

        Args:
            next_node: The target node
            condition: EdgeCondition or expression string (no callables)
            expr: Expression string condition
            priority: Higher-priority edges are evaluated and forwarded first
            **equals: Equality match condition on output fields

        Returns:
            Edge connecting this node to next_node

        Examples:
            node.goto(next_node)  # Unconditional
            node.goto(next_node, EdgeCondition(expr="$.outputs.score > 0.5"))
            node.goto(next_node, condition="$.outputs.score > 0.5")  # Shorthand
            node.goto(next_node, expr="$.outputs.score > 0.5", priority=10)
            node.goto(next_node, action="search")

        Note:
            Lambda/callable conditions are NOT supported for spec compatibility.
            Use EdgeCondition or expr string instead.

        Raises:
            TypeError: If a callable is provided
        """
        if not isinstance(next_node, BaseNode):
            raise TypeError("next_node must be a BaseNode.")

        normalized = self._normalize_edge_condition(
            condition=condition,
            expr=expr,
            equals=equals if equals else None,
        )
        return Edge(from_node=self, condition=normalized or EdgeCondition(), to_node=next_node, priority=priority)


class Node(BaseNode):
    """
    Node is still abstract, it does not implement the process method.
    It provides a more convenient interface for user implementations,
    while BaseNode focuses on the core execution logic and actor integration.
    """

    _process_no_arg: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs):
        """
        if subclass process has not arg other than self, set self._process_no_arg = True
        Note to AI: you should always write a process method that takes a Message argument.
        This is just for lazy human programmers.
        """
        super().__init_subclass__(**kwargs)
        process_impl = getattr(cls, "process", None)
        is_abstract = getattr(process_impl, "__isabstractmethod__", False)
        if process_impl and not is_abstract:
            process_sig = inspect.signature(process_impl)
            if len(process_sig.parameters) < 2:
                cls._process_no_arg = True

    def __init__(self, config: NodeConfig | None = None, **kwargs: Any) -> None:
        super().__init__()
        resolve_config_kwargs(self, config, kwargs)

    def __repr__(self):
        """Return a string representation of the node."""
        return f"Node(name={self.__class__.__name__}, edges={self.edges})"

    def forward_to(self, next_node: BaseNode) -> Node:
        """Forward process results to ``next_node`` instead of returning them."""

        self.goto(next_node)
        return self

    def _forward_target_addresses(self, edges: list[Edge]) -> list[ActorAddress]:
        """Resolve forwarding edge targets to actor addresses before sending."""

        addresses: list[ActorAddress] = []
        for edge in edges:
            next_node = edge.to_node
            if next_node is None:
                continue
            if next_node.address is None:
                raise ActorNotStartedError(next_node.__class__.__name__)
            addresses.append(next_node.address)
        return addresses

    def _forward_message(self, result: Any, message: Message) -> Message:
        """Build the message sent to a downstream forwarding target."""

        metadata = dict(message.metadata)
        if message.sender is not None:
            metadata.setdefault(_FORWARD_REPLY_TO_METADATA_KEY, message.sender)
        metadata[_FORWARDED_METADATA_KEY] = True
        correlation_id = message.correlation_id or message.id
        return Message(content=result, metadata=metadata, correlation_id=correlation_id, state=message.state)

    def _mark_fanout_message(
        self,
        forward_message: Message,
        edge: Edge,
        fanout_count: int,
        fanout_group: str | None,
    ) -> Message:
        """Mark a forwarded message as one branch of a fan-out."""

        if fanout_count > 1:
            forward_message.metadata[_FANOUT_GROUP_METADATA_KEY] = fanout_group or uuid4().hex
            forward_message.metadata[_FANOUT_BRANCH_METADATA_KEY] = edge.id.hex
            forward_message.metadata[_FANOUT_EXPECTED_METADATA_KEY] = fanout_count
        return forward_message

    def _fanin_message(self, message: Message) -> Message | None:
        """Collect fan-out branches when they converge at a multi-input node."""

        if len(self._incoming_edges) < 2:
            return message

        metadata = message.metadata
        group_id = metadata.get(_FANOUT_GROUP_METADATA_KEY)
        branch_id = metadata.get(_FANOUT_BRANCH_METADATA_KEY)
        expected = metadata.get(_FANOUT_EXPECTED_METADATA_KEY)
        if not isinstance(group_id, str) or not isinstance(branch_id, str) or not isinstance(expected, int):
            return message

        buffer = self._fanin_buffers.setdefault(group_id, {})
        buffer[branch_id] = message
        if len(buffer) < expected:
            return None

        messages = list(buffer.values())
        del self._fanin_buffers[group_id]
        joined_metadata = dict(messages[-1].metadata)
        joined_metadata.pop(_FANOUT_GROUP_METADATA_KEY, None)
        joined_metadata.pop(_FANOUT_BRANCH_METADATA_KEY, None)
        joined_metadata.pop(_FANOUT_EXPECTED_METADATA_KEY, None)
        return Message(
            content=[item.content for item in messages],
            metadata=joined_metadata,
            correlation_id=message.correlation_id,
            state=message.state,
        )

    async def _apply_hooks(self, value: Any, hooks: list[NodeHook]) -> Any:
        """Apply value-transforming hooks in order."""

        for hook in hooks:
            value = hook(self, value)
            if inspect.isawaitable(value):
                value = await value
        return value

    async def _process(self, message: Message) -> Any | Awaitable[Any]:
        """Wrap the process method to an async method."""

        fanin_message = self._fanin_message(message)
        if fanin_message is None:
            return None
        message = fanin_message

        message.content = await self._apply_hooks(message.content, self.pre_process_hooks)
        if self._process_no_arg:
            result = self.process()  # type: ignore[call-arg]
        else:
            result = self.process(message)
        if inspect.isawaitable(result):
            result = await result
        result = await self._apply_hooks(result, self.post_process_hooks)

        self._last_inputs = message
        self._outputs = result
        active_edges = self.iter_active_edges()
        forward_targets = self._forward_target_addresses(active_edges)
        if forward_targets:
            fanout_count = len(forward_targets)
            fanout_group = uuid4().hex if fanout_count > 1 else None
            for edge, forward_target in zip(active_edges, forward_targets, strict=True):
                forward_message = self._forward_message(result, message)
                forward_message = self._mark_fanout_message(forward_message, edge, fanout_count, fanout_group)
                await self.tell(forward_message, forward_target)
            return None

        reply_to = message.metadata.get(_FORWARD_REPLY_TO_METADATA_KEY)
        if isinstance(reply_to, ActorAddress):
            await self.tell(result, reply_to)
            return None
        if message.metadata.get(_FORWARDED_METADATA_KEY):
            return None
        return result
