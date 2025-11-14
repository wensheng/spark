"""
Graph spec diffing and comparison tools.

Provides tools for comparing GraphSpec instances:
- Detailed diffing between specs
- Patch application to transform specs
- Migration script generation
- Visual diff rendering
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Optional, Union
from dataclasses import dataclass, field
from enum import Enum

from spark.nodes.spec import (
    GraphSpec,
    NodeSpec,
    EdgeSpec,
    ToolDefinitionSpec,
    GraphStateSpec,
    ConditionSpec,
)


# ============================================================================
# Diff Result Types
# ============================================================================

class ChangeType(Enum):
    """Type of change in diff."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass
class NodeDiff:
    """Difference in a node."""
    node_id: str
    change_type: ChangeType
    old_node: Optional[NodeSpec] = None
    new_node: Optional[NodeSpec] = None
    field_changes: Dict[str, tuple[Any, Any]] = field(default_factory=dict)

    def __str__(self) -> str:
        if self.change_type == ChangeType.ADDED:
            return f"+ Node '{self.node_id}' added (type: {self.new_node.type if self.new_node else 'unknown'})"
        elif self.change_type == ChangeType.REMOVED:
            return f"- Node '{self.node_id}' removed (type: {self.old_node.type if self.old_node else 'unknown'})"
        elif self.change_type == ChangeType.MODIFIED:
            changes = ", ".join(f"{k}: {v[0]} → {v[1]}" for k, v in self.field_changes.items())
            return f"~ Node '{self.node_id}' modified ({changes})"
        return f"  Node '{self.node_id}' unchanged"


@dataclass
class EdgeDiff:
    """Difference in an edge."""
    edge_id: str
    change_type: ChangeType
    old_edge: Optional[EdgeSpec] = None
    new_edge: Optional[EdgeSpec] = None
    field_changes: Dict[str, tuple[Any, Any]] = field(default_factory=dict)

    def __str__(self) -> str:
        if self.change_type == ChangeType.ADDED:
            edge = self.new_edge
            return f"+ Edge '{self.edge_id}' added ({edge.from_node} → {edge.to_node})" if edge else ""
        elif self.change_type == ChangeType.REMOVED:
            edge = self.old_edge
            return f"- Edge '{self.edge_id}' removed ({edge.from_node} → {edge.to_node})" if edge else ""
        elif self.change_type == ChangeType.MODIFIED:
            changes = ", ".join(f"{k}: {v[0]} → {v[1]}" for k, v in self.field_changes.items())
            return f"~ Edge '{self.edge_id}' modified ({changes})"
        return f"  Edge '{self.edge_id}' unchanged"


@dataclass
class ToolDiff:
    """Difference in a tool."""
    tool_name: str
    change_type: ChangeType
    old_tool: Optional[ToolDefinitionSpec] = None
    new_tool: Optional[ToolDefinitionSpec] = None
    field_changes: Dict[str, tuple[Any, Any]] = field(default_factory=dict)

    def __str__(self) -> str:
        if self.change_type == ChangeType.ADDED:
            return f"+ Tool '{self.tool_name}' added"
        elif self.change_type == ChangeType.REMOVED:
            return f"- Tool '{self.tool_name}' removed"
        elif self.change_type == ChangeType.MODIFIED:
            changes = ", ".join(f"{k}: {v[0]} → {v[1]}" for k, v in self.field_changes.items())
            return f"~ Tool '{self.tool_name}' modified ({changes})"
        return f"  Tool '{self.tool_name}' unchanged"


@dataclass
class DiffResult:
    """Complete diff result between two specs."""
    spec1_id: str
    spec2_id: str
    node_diffs: List[NodeDiff] = field(default_factory=list)
    edge_diffs: List[EdgeDiff] = field(default_factory=list)
    tool_diffs: List[ToolDiff] = field(default_factory=list)
    start_changed: bool = False
    old_start: Optional[str] = None
    new_start: Optional[str] = None
    graph_state_changed: bool = False
    old_graph_state: Optional[GraphStateSpec] = None
    new_graph_state: Optional[GraphStateSpec] = None
    metadata_changes: Dict[str, tuple[Any, Any]] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return (
            any(d.change_type != ChangeType.UNCHANGED for d in self.node_diffs) or
            any(d.change_type != ChangeType.UNCHANGED for d in self.edge_diffs) or
            any(d.change_type != ChangeType.UNCHANGED for d in self.tool_diffs) or
            self.start_changed or
            self.graph_state_changed or
            bool(self.metadata_changes)
        )

    @property
    def summary(self) -> Dict[str, int]:
        """Get summary statistics."""
        return {
            'nodes_added': sum(1 for d in self.node_diffs if d.change_type == ChangeType.ADDED),
            'nodes_removed': sum(1 for d in self.node_diffs if d.change_type == ChangeType.REMOVED),
            'nodes_modified': sum(1 for d in self.node_diffs if d.change_type == ChangeType.MODIFIED),
            'edges_added': sum(1 for d in self.edge_diffs if d.change_type == ChangeType.ADDED),
            'edges_removed': sum(1 for d in self.edge_diffs if d.change_type == ChangeType.REMOVED),
            'edges_modified': sum(1 for d in self.edge_diffs if d.change_type == ChangeType.MODIFIED),
            'tools_added': sum(1 for d in self.tool_diffs if d.change_type == ChangeType.ADDED),
            'tools_removed': sum(1 for d in self.tool_diffs if d.change_type == ChangeType.REMOVED),
            'tools_modified': sum(1 for d in self.tool_diffs if d.change_type == ChangeType.MODIFIED),
        }

    def __str__(self) -> str:
        """Generate human-readable diff."""
        lines = []
        lines.append(f"Diff: {self.spec1_id} → {self.spec2_id}")
        lines.append("=" * 70)

        if not self.has_changes:
            lines.append("No changes detected")
            return "\n".join(lines)

        summary = self.summary
        lines.append(f"Summary: {sum(summary.values())} changes")
        lines.append("")

        # Start node changes
        if self.start_changed:
            lines.append(f"Start: {self.old_start} → {self.new_start}")
            lines.append("")

        # Node changes
        if self.node_diffs:
            lines.append("Nodes:")
            for diff in self.node_diffs:
                if diff.change_type != ChangeType.UNCHANGED:
                    lines.append(f"  {diff}")
            lines.append("")

        # Edge changes
        if self.edge_diffs:
            lines.append("Edges:")
            for diff in self.edge_diffs:
                if diff.change_type != ChangeType.UNCHANGED:
                    lines.append(f"  {diff}")
            lines.append("")

        # Tool changes
        if self.tool_diffs:
            lines.append("Tools:")
            for diff in self.tool_diffs:
                if diff.change_type != ChangeType.UNCHANGED:
                    lines.append(f"  {diff}")
            lines.append("")

        # Graph state changes
        if self.graph_state_changed:
            lines.append("GraphState:")
            lines.append(f"  Changed: {self.old_graph_state} → {self.new_graph_state}")
            lines.append("")

        # Metadata changes
        if self.metadata_changes:
            lines.append("Metadata:")
            for key, (old, new) in self.metadata_changes.items():
                lines.append(f"  {key}: {old} → {new}")
            lines.append("")

        return "\n".join(lines)


# ============================================================================
# Spec Differ
# ============================================================================

class SpecDiffer:
    """Compare and diff GraphSpecs."""

    def diff(self, spec1: GraphSpec, spec2: GraphSpec) -> DiffResult:
        """Generate detailed diff between specs.

        Args:
            spec1: First spec (old)
            spec2: Second spec (new)

        Returns:
            DiffResult containing all differences
        """
        result = DiffResult(
            spec1_id=spec1.id,
            spec2_id=spec2.id
        )

        # Compare nodes
        result.node_diffs = self._diff_nodes(spec1.nodes, spec2.nodes)

        # Compare edges
        result.edge_diffs = self._diff_edges(spec1.edges, spec2.edges)

        # Compare tools
        result.tool_diffs = self._diff_tools(
            spec1.tools if spec1.tools else [],
            spec2.tools if spec2.tools else []
        )

        # Compare start node
        if spec1.start != spec2.start:
            result.start_changed = True
            result.old_start = spec1.start
            result.new_start = spec2.start

        # Compare graph state
        if spec1.graph_state != spec2.graph_state:
            result.graph_state_changed = True
            result.old_graph_state = spec1.graph_state
            result.new_graph_state = spec2.graph_state

        # Compare metadata fields
        if spec1.description != spec2.description:
            result.metadata_changes['description'] = (spec1.description, spec2.description)

        return result

    def _diff_nodes(self, nodes1: List[NodeSpec], nodes2: List[NodeSpec]) -> List[NodeDiff]:
        """Diff node lists."""
        diffs = []

        # Build maps
        map1 = {node.id: node for node in nodes1}
        map2 = {node.id: node for node in nodes2}

        all_ids = set(map1.keys()) | set(map2.keys())

        for node_id in sorted(all_ids):
            node1 = map1.get(node_id)
            node2 = map2.get(node_id)

            if node1 is None:
                # Added
                diffs.append(NodeDiff(
                    node_id=node_id,
                    change_type=ChangeType.ADDED,
                    new_node=node2
                ))
            elif node2 is None:
                # Removed
                diffs.append(NodeDiff(
                    node_id=node_id,
                    change_type=ChangeType.REMOVED,
                    old_node=node1
                ))
            else:
                # Compare fields
                field_changes = self._compare_nodes(node1, node2)
                if field_changes:
                    diffs.append(NodeDiff(
                        node_id=node_id,
                        change_type=ChangeType.MODIFIED,
                        old_node=node1,
                        new_node=node2,
                        field_changes=field_changes
                    ))
                else:
                    diffs.append(NodeDiff(
                        node_id=node_id,
                        change_type=ChangeType.UNCHANGED,
                        old_node=node1,
                        new_node=node2
                    ))

        return diffs

    def _compare_nodes(self, node1: NodeSpec, node2: NodeSpec) -> Dict[str, tuple[Any, Any]]:
        """Compare two nodes and return field changes."""
        changes = {}

        if node1.type != node2.type:
            changes['type'] = (node1.type, node2.type)

        if node1.description != node2.description:
            changes['description'] = (node1.description, node2.description)

        if node1.config != node2.config:
            changes['config'] = (node1.config, node2.config)

        if node1.inputs != node2.inputs:
            changes['inputs'] = (node1.inputs, node2.inputs)

        if node1.outputs != node2.outputs:
            changes['outputs'] = (node1.outputs, node2.outputs)

        return changes

    def _diff_edges(self, edges1: List[EdgeSpec], edges2: List[EdgeSpec]) -> List[EdgeDiff]:
        """Diff edge lists."""
        diffs = []

        # Build maps
        map1 = {edge.id: edge for edge in edges1}
        map2 = {edge.id: edge for edge in edges2}

        all_ids = set(map1.keys()) | set(map2.keys())

        for edge_id in sorted(all_ids):
            edge1 = map1.get(edge_id)
            edge2 = map2.get(edge_id)

            if edge1 is None:
                # Added
                diffs.append(EdgeDiff(
                    edge_id=edge_id,
                    change_type=ChangeType.ADDED,
                    new_edge=edge2
                ))
            elif edge2 is None:
                # Removed
                diffs.append(EdgeDiff(
                    edge_id=edge_id,
                    change_type=ChangeType.REMOVED,
                    old_edge=edge1
                ))
            else:
                # Compare fields
                field_changes = self._compare_edges(edge1, edge2)
                if field_changes:
                    diffs.append(EdgeDiff(
                        edge_id=edge_id,
                        change_type=ChangeType.MODIFIED,
                        old_edge=edge1,
                        new_edge=edge2,
                        field_changes=field_changes
                    ))
                else:
                    diffs.append(EdgeDiff(
                        edge_id=edge_id,
                        change_type=ChangeType.UNCHANGED,
                        old_edge=edge1,
                        new_edge=edge2
                    ))

        return diffs

    def _compare_edges(self, edge1: EdgeSpec, edge2: EdgeSpec) -> Dict[str, tuple[Any, Any]]:
        """Compare two edges and return field changes."""
        changes = {}

        if edge1.from_node != edge2.from_node:
            changes['from_node'] = (edge1.from_node, edge2.from_node)

        if edge1.to_node != edge2.to_node:
            changes['to_node'] = (edge1.to_node, edge2.to_node)

        if edge1.priority != edge2.priority:
            changes['priority'] = (edge1.priority, edge2.priority)

        if edge1.description != edge2.description:
            changes['description'] = (edge1.description, edge2.description)

        # Compare conditions
        if edge1.condition != edge2.condition:
            changes['condition'] = (edge1.condition, edge2.condition)

        return changes

    def _diff_tools(self, tools1: List[ToolDefinitionSpec], tools2: List[ToolDefinitionSpec]) -> List[ToolDiff]:
        """Diff tool lists."""
        diffs = []

        # Build maps
        map1 = {tool.name: tool for tool in tools1}
        map2 = {tool.name: tool for tool in tools2}

        all_names = set(map1.keys()) | set(map2.keys())

        for tool_name in sorted(all_names):
            tool1 = map1.get(tool_name)
            tool2 = map2.get(tool_name)

            if tool1 is None:
                # Added
                diffs.append(ToolDiff(
                    tool_name=tool_name,
                    change_type=ChangeType.ADDED,
                    new_tool=tool2
                ))
            elif tool2 is None:
                # Removed
                diffs.append(ToolDiff(
                    tool_name=tool_name,
                    change_type=ChangeType.REMOVED,
                    old_tool=tool1
                ))
            else:
                # Compare fields
                field_changes = self._compare_tools(tool1, tool2)
                if field_changes:
                    diffs.append(ToolDiff(
                        tool_name=tool_name,
                        change_type=ChangeType.MODIFIED,
                        old_tool=tool1,
                        new_tool=tool2,
                        field_changes=field_changes
                    ))
                else:
                    diffs.append(ToolDiff(
                        tool_name=tool_name,
                        change_type=ChangeType.UNCHANGED,
                        old_tool=tool1,
                        new_tool=tool2
                    ))

        return diffs

    def _compare_tools(self, tool1: ToolDefinitionSpec, tool2: ToolDefinitionSpec) -> Dict[str, tuple[Any, Any]]:
        """Compare two tools and return field changes."""
        changes = {}

        if tool1.function != tool2.function:
            changes['function'] = (tool1.function, tool2.function)

        if tool1.description != tool2.description:
            changes['description'] = (tool1.description, tool2.description)

        if tool1.parameters != tool2.parameters:
            changes['parameters'] = (tool1.parameters, tool2.parameters)

        if tool1.return_type != tool2.return_type:
            changes['return_type'] = (tool1.return_type, tool2.return_type)

        if tool1.is_async != tool2.is_async:
            changes['is_async'] = (tool1.is_async, tool2.is_async)

        return changes

    def apply_diff(self, spec: GraphSpec, diff_result: DiffResult) -> GraphSpec:
        """Apply diff to create new spec.

        Args:
            spec: Base spec to apply diff to
            diff_result: Diff to apply

        Returns:
            New spec with diff applied
        """
        # Start with copy of spec
        new_spec_dict = spec.model_dump()

        # Apply node changes
        node_map = {node['id']: node for node in new_spec_dict['nodes']}
        for node_diff in diff_result.node_diffs:
            if node_diff.change_type == ChangeType.ADDED and node_diff.new_node:
                node_map[node_diff.node_id] = node_diff.new_node.model_dump()
            elif node_diff.change_type == ChangeType.REMOVED:
                node_map.pop(node_diff.node_id, None)
            elif node_diff.change_type == ChangeType.MODIFIED and node_diff.new_node:
                node_map[node_diff.node_id] = node_diff.new_node.model_dump()

        new_spec_dict['nodes'] = list(node_map.values())

        # Apply edge changes
        edge_map = {edge['id']: edge for edge in new_spec_dict['edges']}
        for edge_diff in diff_result.edge_diffs:
            if edge_diff.change_type == ChangeType.ADDED and edge_diff.new_edge:
                edge_map[edge_diff.edge_id] = edge_diff.new_edge.model_dump()
            elif edge_diff.change_type == ChangeType.REMOVED:
                edge_map.pop(edge_diff.edge_id, None)
            elif edge_diff.change_type == ChangeType.MODIFIED and edge_diff.new_edge:
                edge_map[edge_diff.edge_id] = edge_diff.new_edge.model_dump()

        new_spec_dict['edges'] = list(edge_map.values())

        # Apply tool changes
        if 'tools' in new_spec_dict:
            tool_map = {tool['name']: tool for tool in new_spec_dict['tools']}
            for tool_diff in diff_result.tool_diffs:
                if tool_diff.change_type == ChangeType.ADDED and tool_diff.new_tool:
                    tool_map[tool_diff.tool_name] = tool_diff.new_tool.model_dump()
                elif tool_diff.change_type == ChangeType.REMOVED:
                    tool_map.pop(tool_diff.tool_name, None)
                elif tool_diff.change_type == ChangeType.MODIFIED and tool_diff.new_tool:
                    tool_map[tool_diff.tool_name] = tool_diff.new_tool.model_dump()

            new_spec_dict['tools'] = list(tool_map.values())

        # Apply start change
        if diff_result.start_changed and diff_result.new_start:
            new_spec_dict['start'] = diff_result.new_start

        # Apply graph state change
        if diff_result.graph_state_changed and diff_result.new_graph_state:
            new_spec_dict['graph_state'] = diff_result.new_graph_state.model_dump()

        # Apply metadata changes
        for key, (old, new) in diff_result.metadata_changes.items():
            new_spec_dict[key] = new

        return GraphSpec.model_validate(new_spec_dict)

    def generate_migration(self, old: GraphSpec, new: GraphSpec, diff_result: Optional[DiffResult] = None) -> str:
        """Generate migration script.

        Args:
            old: Old spec
            new: New spec
            diff_result: Optional pre-computed diff result

        Returns:
            Python migration script as string
        """
        if diff_result is None:
            diff_result = self.diff(old, new)

        lines = []
        lines.append('"""')
        lines.append(f'Migration script: {old.id} → {new.id}')
        lines.append('')
        lines.append('This script migrates a GraphSpec from the old version to the new version.')
        lines.append('"""')
        lines.append('')
        lines.append('from spark.nodes.spec import GraphSpec, NodeSpec, EdgeSpec')
        lines.append('')
        lines.append('')
        lines.append('def migrate_spec(spec: GraphSpec) -> GraphSpec:')
        lines.append('    """Migrate spec to new version."""')
        lines.append('    # Start with a copy')
        lines.append('    spec_dict = spec.model_dump()')
        lines.append('')

        if diff_result.has_changes:
            # Node changes
            if any(d.change_type != ChangeType.UNCHANGED for d in diff_result.node_diffs):
                lines.append('    # Apply node changes')
                for node_diff in diff_result.node_diffs:
                    if node_diff.change_type == ChangeType.ADDED:
                        lines.append(f"    # TODO: Add node '{node_diff.node_id}'")
                    elif node_diff.change_type == ChangeType.REMOVED:
                        lines.append(f"    # Remove node '{node_diff.node_id}'")
                        lines.append(f"    spec_dict['nodes'] = [n for n in spec_dict['nodes'] if n['id'] != '{node_diff.node_id}']")
                    elif node_diff.change_type == ChangeType.MODIFIED:
                        lines.append(f"    # Modify node '{node_diff.node_id}'")
                        for field, (old_val, new_val) in node_diff.field_changes.items():
                            lines.append(f"    # TODO: Update {field}: {old_val} → {new_val}")
                lines.append('')

            # Edge changes
            if any(d.change_type != ChangeType.UNCHANGED for d in diff_result.edge_diffs):
                lines.append('    # Apply edge changes')
                for edge_diff in diff_result.edge_diffs:
                    if edge_diff.change_type == ChangeType.ADDED:
                        lines.append(f"    # TODO: Add edge '{edge_diff.edge_id}'")
                    elif edge_diff.change_type == ChangeType.REMOVED:
                        lines.append(f"    # Remove edge '{edge_diff.edge_id}'")
                        lines.append(f"    spec_dict['edges'] = [e for e in spec_dict['edges'] if e['id'] != '{edge_diff.edge_id}']")
                    elif edge_diff.change_type == ChangeType.MODIFIED:
                        lines.append(f"    # Modify edge '{edge_diff.edge_id}'")
                        for field, (old_val, new_val) in edge_diff.field_changes.items():
                            lines.append(f"    # TODO: Update {field}: {old_val} → {new_val}")
                lines.append('')

            # Start change
            if diff_result.start_changed:
                lines.append('    # Change start node')
                lines.append(f"    spec_dict['start'] = '{diff_result.new_start}'")
                lines.append('')

            # Metadata changes
            if diff_result.metadata_changes:
                lines.append('    # Apply metadata changes')
                for key, (old_val, new_val) in diff_result.metadata_changes.items():
                    lines.append(f"    spec_dict['{key}'] = {repr(new_val)}")
                lines.append('')

        lines.append('    return GraphSpec.model_validate(spec_dict)')
        lines.append('')
        lines.append('')
        lines.append('if __name__ == "__main__":')
        lines.append('    # Load old spec')
        lines.append('    with open("old_spec.json") as f:')
        lines.append('        old_spec = GraphSpec.model_validate_json(f.read())')
        lines.append('')
        lines.append('    # Migrate')
        lines.append('    new_spec = migrate_spec(old_spec)')
        lines.append('')
        lines.append('    # Save new spec')
        lines.append('    with open("new_spec.json", "w") as f:')
        lines.append('        f.write(new_spec.model_dump_json(indent=2))')
        lines.append('    print("Migration complete!")')
        lines.append('')

        return '\n'.join(lines)
