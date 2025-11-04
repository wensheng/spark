"""
Serialization helpers between runtime Graph/Node/Edge and spec models.

This module provides best-effort export of in-memory graphs to GraphSpec.
It focuses on structure fidelity (nodes, edges, priorities, descriptions).
Conditions implemented as Python callables are recorded as non-executable
descriptions (ConditionSpec(kind='python')).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from spark.nodes.base import BaseNode, Edge
from spark.graphs.base import BaseGraph
from spark.nodes.config import NodeConfig
from spark.nodes.spec import ConditionSpec, EdgeSpec, GraphSpec, NodeSpec


def _infer_node_type(node: BaseNode) -> str:
    # Avoid importing Agent at module import time to reduce heavy deps
    cls_name = node.__class__.__name__
    mod_name = getattr(node.__class__, '__module__', '')
    if cls_name.endswith('Agent') or '.agents.' in mod_name:
        return 'Agent'
    # Future: Router, SubGraph, HumanInLoop, Tool could be derived by class type
    return 'Basic'


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


def _collect_nodes_from_edges(edges: List[Edge]) -> List[BaseNode]:
    nodes: Dict[str, BaseNode] = {}
    for e in edges:
        nodes.setdefault(e.from_node.id, e.from_node)
        if e.to_node is not None:
            nodes.setdefault(e.to_node.id, e.to_node)
    # Stable order by id for deterministic output
    return [nodes[k] for k in sorted(nodes.keys())]


def _edge_condition_to_spec(edge: Edge) -> Optional[ConditionSpec]:
    cond = edge.condition
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


def node_to_spec(node: BaseNode) -> NodeSpec:
    """Convert a runtime `BaseNode` instance to a `NodeSpec`."""
    return NodeSpec(
        id=str(node.id),
        type=_infer_node_type(node),
        description=getattr(node, 'description', None) or None,
        inputs=None,
        outputs=None,
        config=_safe_config_from_node(node) or None,
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
    )


def graph_to_spec(graph: BaseGraph, *, spark_version: str = '1.0') -> GraphSpec:
    """Create a `GraphSpec` from an in-memory `BaseGraph`."""
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

    return GraphSpec(
        spark_version=spark_version,
        id=str(getattr(graph, 'id', 'graph')),
        description=getattr(graph, 'description', None) or None,
        start=str(start_id),
        nodes=node_specs,
        edges=edge_specs,
    )


def graph_to_json(graph: BaseGraph, *, spark_version: str = '1.0', indent: int = 2) -> str:
    """Serialize a graph to a JSON string using spec field names."""
    spec = graph_to_spec(graph, spark_version=spark_version)
    payload = spec.model_dump_standard()
    # Late import to avoid hard dependency for consumers who use Python APIs only
    import json as _json

    return _json.dumps(payload, ensure_ascii=False, indent=indent)


def save_graph_json(path: str, graph: BaseGraph, *, spark_version: str = '1.0', indent: int = 2) -> None:
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
