"""
Graph spec diffing and comparison tools.

Provides tools for comparing GraphSpec instances:
- Detailed diffing between specs
- Patch application to transform specs
- Migration script generation
- Visual diff rendering
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Optional, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum
import textwrap

from spark.nodes.spec import (
    GraphSpec,
    NodeSpec,
    EdgeSpec,
    ToolDefinitionSpec,
    GraphStateSpec,
    ConditionSpec,
    MissionSpec,
    MissionPlanSpec,
    MissionPlanStepSpec,
    MissionStrategyBindingSpec,
    MissionStateSchemaSpec,
    MissionDeploymentSpec,
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


# ==============================================================================
# Mission Spec Diffing
# ==============================================================================

@dataclass
class PlanDiffSummary:
    """Diff summary for mission plans."""

    plan_added: bool = False
    plan_removed: bool = False
    metadata_changes: Dict[str, tuple[Any, Any]] = field(default_factory=dict)
    added_steps: List[MissionPlanStepSpec] = field(default_factory=list)
    removed_steps: List[MissionPlanStepSpec] = field(default_factory=list)
    changed_steps: List[Tuple[str, MissionPlanStepSpec, MissionPlanStepSpec]] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return (
            self.plan_added
            or self.plan_removed
            or bool(self.metadata_changes)
            or bool(self.added_steps)
            or bool(self.removed_steps)
            or bool(self.changed_steps)
        )


@dataclass
class StrategyDiffSummary:
    """Diff summary for mission strategy bindings."""

    added: List[MissionStrategyBindingSpec] = field(default_factory=list)
    removed: List[MissionStrategyBindingSpec] = field(default_factory=list)
    changed: List[Tuple[MissionStrategyBindingSpec, MissionStrategyBindingSpec]] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)


@dataclass
class MissionSpecDiffResult:
    """Aggregate diff for mission specs."""

    mission1_id: str
    mission2_id: str
    mission1_version: str
    mission2_version: str
    metadata_changes: Dict[str, tuple[Any, Any]] = field(default_factory=dict)
    plan_diff: PlanDiffSummary = field(default_factory=PlanDiffSummary)
    strategy_diff: StrategyDiffSummary = field(default_factory=StrategyDiffSummary)
    state_schema_changed: bool = False
    state_schema_old: Optional[MissionStateSchemaSpec] = None
    state_schema_new: Optional[MissionStateSchemaSpec] = None
    telemetry_changed: bool = False
    telemetry_old: Optional[Any] = None
    telemetry_new: Optional[Any] = None
    deployment_changed: bool = False
    deployment_old: Optional[MissionDeploymentSpec] = None
    deployment_new: Optional[MissionDeploymentSpec] = None
    graph_diff: Optional[DiffResult] = None

    @property
    def has_changes(self) -> bool:
        return (
            bool(self.metadata_changes)
            or (self.graph_diff.has_changes if self.graph_diff else False)
            or self.plan_diff.has_changes
            or self.strategy_diff.has_changes
            or self.state_schema_changed
            or self.telemetry_changed
            or self.deployment_changed
        )

    @property
    def summary(self) -> Dict[str, Any]:
        summary = {}
        if self.graph_diff:
            summary.update(self.graph_diff.summary)
        summary.update(
            {
                'metadata_changes': len(self.metadata_changes),
                'plan_changes': len(self.plan_diff.added_steps)
                + len(self.plan_diff.removed_steps)
                + len(self.plan_diff.changed_steps)
                + (1 if self.plan_diff.plan_added or self.plan_diff.plan_removed else 0)
                + len(self.plan_diff.metadata_changes),
                'strategy_changes': len(self.strategy_diff.added)
                + len(self.strategy_diff.removed)
                + len(self.strategy_diff.changed),
                'state_schema_changed': self.state_schema_changed,
                'telemetry_changed': self.telemetry_changed,
                'deployment_changed': self.deployment_changed,
            }
        )
        return summary

    def as_dict(self) -> Dict[str, Any]:
        return {
            'mission_old': {'id': self.mission1_id, 'version': self.mission1_version},
            'mission_new': {'id': self.mission2_id, 'version': self.mission2_version},
            'metadata_changes': self.metadata_changes,
            'plan': {
                'plan_added': self.plan_diff.plan_added,
                'plan_removed': self.plan_diff.plan_removed,
                'metadata_changes': self.plan_diff.metadata_changes,
                'added_steps': [step.model_dump() for step in self.plan_diff.added_steps],
                'removed_steps': [step.model_dump() for step in self.plan_diff.removed_steps],
                'changed_steps': [
                    {'id': step_id, 'old': old.model_dump(), 'new': new.model_dump()}
                    for step_id, old, new in self.plan_diff.changed_steps
                ],
            },
            'strategies': {
                'added': [binding.model_dump() for binding in self.strategy_diff.added],
                'removed': [binding.model_dump() for binding in self.strategy_diff.removed],
                'changed': [
                    {
                        'target': old.target,
                        'reference': old.reference,
                        'old': old.model_dump(),
                        'new': new.model_dump(),
                    }
                    for (old, new) in self.strategy_diff.changed
                ],
            },
            'state_schema_changed': self.state_schema_changed,
            'state_schema_old': self.state_schema_old.model_dump() if self.state_schema_old else None,
            'state_schema_new': self.state_schema_new.model_dump() if self.state_schema_new else None,
            'telemetry_changed': self.telemetry_changed,
            'deployment_changed': self.deployment_changed,
            'graph_summary': self.graph_diff.summary if self.graph_diff else {},
            'graph_has_changes': self.graph_diff.has_changes if self.graph_diff else False,
        }

    def __str__(self) -> str:
        lines = [
            f"Mission diff: {self.mission1_id} ({self.mission1_version}) → "
            f"{self.mission2_id} ({self.mission2_version})",
            "=" * 70,
        ]

        if not self.has_changes:
            lines.append("No mission changes detected")
            return "\n".join(lines)

        if self.metadata_changes:
            lines.append("Metadata changes:")
            for key, (old, new) in self.metadata_changes.items():
                lines.append(f"  - {key}: {old} → {new}")
            lines.append("")

        if self.plan_diff.has_changes:
            lines.append("Plan changes:")
            if self.plan_diff.plan_added:
                lines.append("  + Plan added")
            if self.plan_diff.plan_removed:
                lines.append("  - Plan removed")
            for key, (old, new) in self.plan_diff.metadata_changes.items():
                lines.append(f"  * {key}: {old} → {new}")
            for step in self.plan_diff.added_steps:
                lines.append(f"  + Step {step.id}: {step.description}")
            for step in self.plan_diff.removed_steps:
                lines.append(f"  - Step {step.id}: {step.description}")
            for step_id, old_step, new_step in self.plan_diff.changed_steps:
                lines.append(f"  ~ Step {step_id}: {old_step.description} → {new_step.description}")
            lines.append("")

        if self.strategy_diff.has_changes:
            lines.append("Strategy changes:")
            for binding in self.strategy_diff.added:
                lines.append(f"  + {binding.target}:{binding.reference} strategy {binding.strategy.type}")
            for binding in self.strategy_diff.removed:
                lines.append(f"  - {binding.target}:{binding.reference} strategy {binding.strategy.type}")
            for old, new in self.strategy_diff.changed:
                lines.append(
                    f"  ~ {old.target}:{old.reference} strategy changed "
                    f"{old.strategy.type} → {new.strategy.type}"
                )
            lines.append("")

        if self.state_schema_changed:
            lines.append("State schema changed.")
            lines.append("")

        if self.telemetry_changed:
            lines.append("Telemetry configuration changed.")
            lines.append("")

        if self.deployment_changed:
            lines.append("Deployment metadata changed.")
            lines.append("")

        if self.graph_diff and self.graph_diff.has_changes:
            lines.append("Graph diff:")
            lines.append(textwrap.indent(str(self.graph_diff), "  "))

        return "\n".join(lines)


def diff_mission_specs(
    mission1: MissionSpec,
    mission2: MissionSpec,
    *,
    differ: Optional[SpecDiffer] = None,
) -> MissionSpecDiffResult:
    """Diff two mission specs (graph + plan/strategy metadata)."""

    differ = differ or SpecDiffer()
    result = MissionSpecDiffResult(
        mission1_id=mission1.mission_id,
        mission2_id=mission2.mission_id,
        mission1_version=mission1.version,
        mission2_version=mission2.version,
    )
    result.graph_diff = differ.diff(mission1.graph, mission2.graph)

    for key in ('mission_id', 'version', 'description'):
        if getattr(mission1, key) != getattr(mission2, key):
            result.metadata_changes[key] = (getattr(mission1, key), getattr(mission2, key))

    result.plan_diff = _diff_plans(mission1.plan, mission2.plan)
    result.strategy_diff = _diff_strategies(mission1.strategies, mission2.strategies)

    if _schema_dump(mission1.state_schema) != _schema_dump(mission2.state_schema):
        result.state_schema_changed = True
        result.state_schema_old = mission1.state_schema
        result.state_schema_new = mission2.state_schema

    if _telemetry_dump(mission1.telemetry) != _telemetry_dump(mission2.telemetry):
        result.telemetry_changed = True
        result.telemetry_old = mission1.telemetry
        result.telemetry_new = mission2.telemetry

    if _deployment_dump(mission1.deployment) != _deployment_dump(mission2.deployment):
        result.deployment_changed = True
        result.deployment_old = mission1.deployment
        result.deployment_new = mission2.deployment

    return result


def _diff_plans(plan1: Optional[MissionPlanSpec], plan2: Optional[MissionPlanSpec]) -> PlanDiffSummary:
    summary = PlanDiffSummary()
    if plan1 is None and plan2 is None:
        return summary
    if plan1 is None and plan2 is not None:
        summary.plan_added = True
        summary.added_steps = list(plan2.steps)
        return summary
    if plan1 is not None and plan2 is None:
        summary.plan_removed = True
        summary.removed_steps = list(plan1.steps)
        return summary

    plan1 = plan1 or MissionPlanSpec(name='mission_plan')
    plan2 = plan2 or MissionPlanSpec(name='mission_plan')

    if plan1.name != plan2.name:
        summary.metadata_changes['name'] = (plan1.name, plan2.name)
    if plan1.description != plan2.description:
        summary.metadata_changes['description'] = (plan1.description, plan2.description)
    if plan1.auto_advance != plan2.auto_advance:
        summary.metadata_changes['auto_advance'] = (plan1.auto_advance, plan2.auto_advance)
    if plan1.telemetry_topic != plan2.telemetry_topic:
        summary.metadata_changes['telemetry_topic'] = (plan1.telemetry_topic, plan2.telemetry_topic)

    steps1 = {step.id: step for step in plan1.steps}
    steps2 = {step.id: step for step in plan2.steps}

    for step_id, step in steps2.items():
        if step_id not in steps1:
            summary.added_steps.append(step)
        else:
            if step != steps1[step_id]:
                summary.changed_steps.append((step_id, steps1[step_id], step))

    for step_id, step in steps1.items():
        if step_id not in steps2:
            summary.removed_steps.append(step)

    return summary


def _diff_strategies(
    strategies1: List[MissionStrategyBindingSpec],
    strategies2: List[MissionStrategyBindingSpec],
) -> StrategyDiffSummary:
    summary = StrategyDiffSummary()

    map1 = {(s.target, s.reference): s for s in strategies1}
    map2 = {(s.target, s.reference): s for s in strategies2}

    for key, binding in map2.items():
        if key not in map1:
            summary.added.append(binding)
        else:
            other = map1[key]
            if other.strategy != binding.strategy or other.metadata != binding.metadata:
                summary.changed.append((other, binding))

    for key, binding in map1.items():
        if key not in map2:
            summary.removed.append(binding)

    return summary


def _schema_dump(schema: Optional[MissionStateSchemaSpec]) -> Optional[Dict[str, Any]]:
    return schema.model_dump() if schema else None


def _telemetry_dump(telemetry: Optional[Any]) -> Optional[Dict[str, Any]]:
    return telemetry.model_dump() if telemetry else None


def _deployment_dump(deployment: Optional[MissionDeploymentSpec]) -> Optional[Dict[str, Any]]:
    return deployment.model_dump() if deployment else None
