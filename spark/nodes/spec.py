"""
Specification models for Spark graphs, nodes, edges, and tools.

These Pydantic models mirror the JSON contracts described in spec/spark001.md
and are used for validation, (de)serialization, and code generation inputs.
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


class ConditionSpec(BaseModel):
    """Serializable description of an edge condition.

    - kind='expr': expression string evaluated at runtime (e.g., "$.inputs.action == 'search'")
    - kind='equals': direct equals routing (e.g., {'action': 'search'})
    - kind='python': non-serializable callable; captured best-effort representation
    """

    model_config = ConfigDict(extra='ignore')

    kind: Literal['expr', 'equals', 'python'] = 'expr'
    expr: Optional[str] = None
    equals: Optional[dict[str, Any]] = None
    python_repr: Optional[str] = None


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
    """Serialized edge descriptor connecting two nodes in a graph spec."""

    model_config = ConfigDict(extra='ignore')

    id: str
    from_node: str = Field(alias='from_id')
    to_node: str = Field(alias='to_id')
    condition: Optional[Union[str, ConditionSpec]] = None
    description: Optional[str] = None
    priority: int = 0

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


class GraphSpec(BaseModel):
    """Top-level graph specification including nodes and edges."""

    model_config = ConfigDict(extra='ignore')

    spark_version: str = '1.0'
    id: str
    description: Optional[str] = None
    start: str
    nodes: list[NodeSpec] = Field(default_factory=list)
    edges: list[EdgeSpec] = Field(default_factory=list)

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
