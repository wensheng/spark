import importlib.util
import os
from typing import Any

from spark.nodes import Node
from spark.graphs.graph import Graph
from spark.nodes.base import ExecutionContext, EdgeCondition
from spark.nodes.serde import graph_to_spec
from spark.kit.codegen import generate


class StartNode(Node):
    async def process(self, context: ExecutionContext) -> Any:
        # Pass through inputs
        return context.inputs or {}


class SinkNode(Node):
    async def process(self, context: ExecutionContext) -> Any:
        # Pass through
        return context.inputs or {}


def build_sample_graph() -> Graph:
    start = StartNode()
    a = SinkNode()
    b = SinkNode()
    # equals routing: action == 'search' -> a
    start.on(action='search') >> a
    # expr routing: action == 'answer' -> b
    cond = EdgeCondition(expr="$.inputs.action == 'answer'")
    start.goto(b, condition=cond)
    # Graph auto-discovers all nodes and edges from start_node
    return Graph(start=start)


def _read_text(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def test_serde_preserves_equals_and_expr(tmp_path):
    g = build_sample_graph()
    spec = graph_to_spec(g)
    # Collect conditions
    kinds = []
    for e in spec.edges:
        cond = e.condition
        if isinstance(cond, str) or cond is None:
            kinds.append('str' if isinstance(cond, str) else 'none')
        else:
            kinds.append(cond.kind)
    # Expect one equals and one expr
    assert 'equals' in kinds
    assert 'expr' in kinds


def test_codegen_generates_single_file_with_conditions(tmp_path):
    g = build_sample_graph()
    spec = graph_to_spec(g)
    out_file = generate(spec, str(tmp_path))
    code = _read_text(out_file)
    # File should contain one .on(action='search') and one EdgeCondition(expr=...)
    assert ".on(action='search')" in code or '.on(action="search")' in code
    assert 'EdgeCondition(expr=' in code
    assert '$.inputs.action' in code
