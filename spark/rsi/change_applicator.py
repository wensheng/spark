"""Change application for RSI system.

This module provides the ChangeApplicator that applies hypothesis changes to graph
specifications, creating modified versions for testing and deployment.
"""

import copy
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from spark.rsi.types import (
    ImprovementHypothesis,
    ChangeSpec,
    StructuralDiff,
    StructuralValidationResult,
    NodeModification,
    EdgeModification,
    ParallelGraphStructure,
)
from spark.nodes.spec import GraphSpec, NodeSpec, EdgeSpec

logger = logging.getLogger(__name__)


class ChangeApplicationError(Exception):
    """Error applying changes to graph spec."""
    pass


class ChangeApplicator:
    """Applies hypothesis changes to graph specifications.

    The ChangeApplicator is responsible for:
    1. Taking a hypothesis with one or more ChangeSpec(s)
    2. Applying those changes to a GraphSpec (immutably)
    3. Validating the modified spec
    4. Generating diffs for audit trail

    Design Principles:
    - Immutable: Never modifies the original spec
    - Validated: All changes are validated before returning
    - Auditable: Generates diff records for tracking
    - Safe: Rolls back on validation errors

    Example:
        applicator = ChangeApplicator()

        # Apply changes from hypothesis
        modified_spec, diff = applicator.apply_hypothesis(
            baseline_spec=graph_spec,
            hypothesis=improvement_hypothesis
        )

        # Or apply individual changes
        modified_spec = applicator.apply_change(
            baseline_spec=graph_spec,
            change=change_spec
        )
    """

    def __init__(self, validate_changes: bool = True, strict_mode: bool = False):
        """Initialize the ChangeApplicator.

        Args:
            validate_changes: Whether to validate changes after application (default: True)
            strict_mode: If True, fail on any validation warning (default: False)
        """
        self.validate_changes = validate_changes
        self.strict_mode = strict_mode

    def apply_hypothesis(
        self,
        baseline_spec: GraphSpec,
        hypothesis: ImprovementHypothesis
    ) -> tuple[GraphSpec, Dict[str, Any]]:
        """Apply all changes from a hypothesis to a graph spec.

        Args:
            baseline_spec: The baseline graph specification
            hypothesis: The improvement hypothesis with changes to apply

        Returns:
            Tuple of (modified_spec, diff_record)

        Raises:
            ChangeApplicationError: If changes cannot be applied
        """
        logger.info(f"Applying hypothesis {hypothesis.hypothesis_id} with {len(hypothesis.changes)} change(s)")

        # Start with a deep copy
        modified_spec = self._deep_copy_spec(baseline_spec)

        # Track applied changes for diff
        applied_changes = []
        failed_changes = []

        # Apply each change sequentially (using internal method to avoid double-copy)
        for i, change in enumerate(hypothesis.changes):
            try:
                logger.debug(f"Applying change {i+1}/{len(hypothesis.changes)}: {change.type}")
                modified_spec = self._apply_change_to_spec(modified_spec, change)
                applied_changes.append({
                    'change': change,
                    'status': 'success'
                })
            except Exception as e:
                logger.error(f"Failed to apply change {i+1}: {e}")
                failed_changes.append({
                    'change': change,
                    'status': 'failed',
                    'error': str(e)
                })

                if self.strict_mode:
                    raise ChangeApplicationError(
                        f"Failed to apply change {i+1}/{len(hypothesis.changes)}: {e}"
                    )

        # Validate the modified spec
        if self.validate_changes:
            try:
                self._validate_spec(modified_spec)
            except Exception as e:
                raise ChangeApplicationError(f"Modified spec validation failed: {e}")

        # Generate diff record
        diff = self._generate_diff(
            baseline_spec=baseline_spec,
            modified_spec=modified_spec,
            hypothesis=hypothesis,
            applied_changes=applied_changes,
            failed_changes=failed_changes
        )

        logger.info(f"Applied {len(applied_changes)} changes successfully, {len(failed_changes)} failed")

        return modified_spec, diff

    def apply_change(self, spec: GraphSpec, change: ChangeSpec) -> GraphSpec:
        """Apply a single change to a graph spec.

        Args:
            spec: The graph specification to modify
            change: The change to apply

        Returns:
            Modified graph specification (immutable - returns new copy)

        Raises:
            ChangeApplicationError: If change cannot be applied
        """
        # Create a deep copy to ensure immutability
        modified_spec = self._deep_copy_spec(spec)

        # Apply change to the copy
        return self._apply_change_to_spec(modified_spec, change)

    def _apply_change_to_spec(self, spec: GraphSpec, change: ChangeSpec) -> GraphSpec:
        """Internal method to apply change to spec (mutates in place).

        This is used internally by apply_hypothesis to avoid redundant copies.
        Public API should use apply_change() which ensures immutability.

        Args:
            spec: The graph specification to modify (will be mutated)
            change: The change to apply

        Returns:
            The modified spec (same object, mutated)

        Raises:
            ChangeApplicationError: If change cannot be applied
        """
        # Dispatch to specific handler based on change type
        handlers = {
            'node_config_update': self._apply_node_config_update,
            'node_add': self._apply_node_add,
            'node_remove': self._apply_node_remove,
            'edge_add': self._apply_edge_add,
            'edge_remove': self._apply_edge_remove,
            'edge_modify': self._apply_edge_modify,
            # Phase 6: Structural changes
            'node_replacement': self._apply_node_replacement,
            'edge_batch_modifications': self._apply_edge_batch_modifications,
            'parallelization': self._apply_parallelization,
        }

        handler = handlers.get(change.type)
        if not handler:
            raise ChangeApplicationError(f"Unsupported change type: {change.type}")

        try:
            return handler(spec, change)
        except Exception as e:
            raise ChangeApplicationError(f"Failed to apply {change.type}: {e}")

    # ============================================================================
    # Change Type Handlers
    # ============================================================================

    def _apply_node_config_update(self, spec: GraphSpec, change: ChangeSpec) -> GraphSpec:
        """Apply node configuration update.

        Updates a specific configuration value within a node's config dict.
        """
        target_node_id = change.target_node_id
        config_path = change.config_path
        new_value = change.new_value

        if not target_node_id:
            raise ChangeApplicationError("node_config_update requires target_node_id")
        if not config_path:
            raise ChangeApplicationError("node_config_update requires config_path")

        # Find the target node
        node_idx = self._find_node_index(spec, target_node_id)
        if node_idx is None:
            raise ChangeApplicationError(f"Node not found: {target_node_id}")

        # Update the config
        node = spec.nodes[node_idx]
        if node.config is None:
            node.config = {}

        # Support nested paths like "prompt.template"
        config_keys = config_path.split('.')
        config_dict = node.config

        # Navigate to the parent dict
        for key in config_keys[:-1]:
            if key not in config_dict:
                config_dict[key] = {}
            config_dict = config_dict[key]

        # Set the value
        final_key = config_keys[-1]
        config_dict[final_key] = new_value

        logger.debug(f"Updated {target_node_id}.config.{config_path} = {new_value}")

        return spec

    def _apply_node_add(self, spec: GraphSpec, change: ChangeSpec) -> GraphSpec:
        """Add a new node to the graph."""
        node_spec_dict = change.additional_params.get('node_spec')
        if not node_spec_dict:
            raise ChangeApplicationError("node_add requires 'node_spec' in additional_params")

        # Create NodeSpec from dict
        new_node = NodeSpec(**node_spec_dict)

        # Check for duplicate ID
        if self._find_node_index(spec, new_node.id) is not None:
            raise ChangeApplicationError(f"Node ID already exists: {new_node.id}")

        # Add the node
        spec.nodes.append(new_node)

        logger.debug(f"Added node: {new_node.id} (type: {new_node.type})")

        return spec

    def _apply_node_remove(self, spec: GraphSpec, change: ChangeSpec) -> GraphSpec:
        """Remove a node from the graph.

        Also removes all edges connected to this node.
        """
        target_node_id = change.target_node_id
        if not target_node_id:
            raise ChangeApplicationError("node_remove requires target_node_id")

        # Check if this is the start node
        if spec.start == target_node_id:
            raise ChangeApplicationError(f"Cannot remove start node: {target_node_id}")

        # Find and remove the node
        node_idx = self._find_node_index(spec, target_node_id)
        if node_idx is None:
            raise ChangeApplicationError(f"Node not found: {target_node_id}")

        removed_node = spec.nodes.pop(node_idx)

        # Remove all edges connected to this node
        edges_before = len(spec.edges)
        spec.edges = [
            edge for edge in spec.edges
            if edge.from_node != target_node_id and edge.to_node != target_node_id
        ]
        edges_removed = edges_before - len(spec.edges)

        logger.debug(f"Removed node: {target_node_id}, removed {edges_removed} connected edge(s)")

        return spec

    def _apply_edge_add(self, spec: GraphSpec, change: ChangeSpec) -> GraphSpec:
        """Add a new edge to the graph."""
        edge_spec_dict = change.additional_params.get('edge_spec')
        if not edge_spec_dict:
            raise ChangeApplicationError("edge_add requires 'edge_spec' in additional_params")

        # Create EdgeSpec from dict
        new_edge = EdgeSpec(**edge_spec_dict)

        # Validate that both nodes exist
        if self._find_node_index(spec, new_edge.from_node) is None:
            raise ChangeApplicationError(f"Source node not found: {new_edge.from_node}")
        if self._find_node_index(spec, new_edge.to_node) is None:
            raise ChangeApplicationError(f"Target node not found: {new_edge.to_node}")

        # Check for duplicate edge ID
        if any(e.id == new_edge.id for e in spec.edges):
            raise ChangeApplicationError(f"Edge ID already exists: {new_edge.id}")

        # Add the edge
        spec.edges.append(new_edge)

        logger.debug(f"Added edge: {new_edge.id} ({new_edge.from_node} -> {new_edge.to_node})")

        return spec

    def _apply_edge_remove(self, spec: GraphSpec, change: ChangeSpec) -> GraphSpec:
        """Remove an edge from the graph."""
        target_edge_id = change.target_edge_id
        if not target_edge_id:
            raise ChangeApplicationError("edge_remove requires target_edge_id")

        # Find and remove the edge
        edge_idx = self._find_edge_index(spec, target_edge_id)
        if edge_idx is None:
            raise ChangeApplicationError(f"Edge not found: {target_edge_id}")

        removed_edge = spec.edges.pop(edge_idx)

        logger.debug(f"Removed edge: {target_edge_id} ({removed_edge.from_node} -> {removed_edge.to_node})")

        return spec

    def _apply_edge_modify(self, spec: GraphSpec, change: ChangeSpec) -> GraphSpec:
        """Modify an existing edge (typically the condition)."""
        target_edge_id = change.target_edge_id
        if not target_edge_id:
            raise ChangeApplicationError("edge_modify requires target_edge_id")

        # Find the edge
        edge_idx = self._find_edge_index(spec, target_edge_id)
        if edge_idx is None:
            raise ChangeApplicationError(f"Edge not found: {target_edge_id}")

        edge = spec.edges[edge_idx]

        # Update fields from additional_params
        updates = change.additional_params
        if 'condition' in updates:
            edge.condition = updates['condition']
        if 'priority' in updates:
            edge.priority = updates['priority']
        if 'description' in updates:
            edge.description = updates['description']

        logger.debug(f"Modified edge: {target_edge_id}")

        return spec

    # ============================================================================
    # Helper Methods
    # ============================================================================

    def _deep_copy_spec(self, spec: GraphSpec) -> GraphSpec:
        """Create a deep copy of a GraphSpec using Pydantic."""
        # Use Python's deep copy to ensure complete independence
        return copy.deepcopy(spec)

    def _find_node_index(self, spec: GraphSpec, node_id: str) -> Optional[int]:
        """Find the index of a node by ID."""
        for i, node in enumerate(spec.nodes):
            if node.id == node_id:
                return i
        return None

    def _find_edge_index(self, spec: GraphSpec, edge_id: str) -> Optional[int]:
        """Find the index of an edge by ID."""
        for i, edge in enumerate(spec.edges):
            if edge.id == edge_id:
                return i
        return None

    def _validate_spec(self, spec: GraphSpec) -> None:
        """Validate a graph spec using Pydantic validation.

        GraphSpec has built-in validators that check:
        - Unique node IDs
        - Start node exists
        - All edge references are valid
        """
        # Pydantic validation happens automatically on construction
        # We can force re-validation by reconstructing
        try:
            GraphSpec(**spec.model_dump())
        except Exception as e:
            raise ChangeApplicationError(f"Spec validation failed: {e}")

    def _generate_diff(
        self,
        baseline_spec: GraphSpec,
        modified_spec: GraphSpec,
        hypothesis: ImprovementHypothesis,
        applied_changes: List[Dict[str, Any]],
        failed_changes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate a diff record for audit trail."""
        return {
            'hypothesis_id': hypothesis.hypothesis_id,
            'baseline_version': baseline_spec.id,
            'modified_version': modified_spec.id,
            'timestamp': datetime.now().isoformat(),
            'changes_applied': len(applied_changes),
            'changes_failed': len(failed_changes),
            'applied_changes': [
                {
                    'type': change['change'].type,
                    'target': change['change'].target_node_id or change['change'].target_edge_id,
                    'status': change['status']
                }
                for change in applied_changes
            ],
            'failed_changes': [
                {
                    'type': change['change'].type,
                    'target': change['change'].target_node_id or change['change'].target_edge_id,
                    'error': change['error']
                }
                for change in failed_changes
            ],
            'summary': {
                'nodes_added': sum(1 for c in applied_changes if c['change'].type == 'node_add'),
                'nodes_removed': sum(1 for c in applied_changes if c['change'].type == 'node_remove'),
                'nodes_modified': sum(1 for c in applied_changes if c['change'].type == 'node_config_update'),
                'edges_added': sum(1 for c in applied_changes if c['change'].type == 'edge_add'),
                'edges_removed': sum(1 for c in applied_changes if c['change'].type == 'edge_remove'),
                'edges_modified': sum(1 for c in applied_changes if c['change'].type == 'edge_modify'),
            }
        }

    # ============================================================================
    # Phase 6: Structural Change Methods
    # ============================================================================

    def validate_structural_integrity(self, spec: GraphSpec) -> StructuralValidationResult:
        """Validate graph structure after changes.

        Checks:
        - All nodes reachable from start_node
        - No orphaned nodes (unless intentional)
        - All edge targets exist
        - No cycles (unless graph allows them)
        - Start node exists
        - At least one execution path

        Args:
            spec: The graph specification to validate

        Returns:
            Validation result with errors, warnings, and analysis
        """
        errors = []
        warnings = []
        reachable_nodes = []
        orphaned_nodes = []
        cycles = []

        # Check start node exists
        if not spec.start:
            errors.append("Graph has no start node")
            return StructuralValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                reachable_nodes=reachable_nodes,
                orphaned_nodes=orphaned_nodes,
                cycles=cycles
            )

        # Check start node is in nodes list
        start_node_exists = any(node.id == spec.start for node in spec.nodes)
        if not start_node_exists:
            errors.append(f"Start node '{spec.start}' does not exist in nodes list")

        # Build adjacency list for graph traversal
        adjacency = {}
        for node in spec.nodes:
            adjacency[node.id] = []

        for edge in spec.edges:
            # Check edge references valid nodes
            if edge.from_node not in adjacency:
                errors.append(f"Edge '{edge.id}' references non-existent source node: {edge.from_node}")
            if edge.to_node not in adjacency:
                errors.append(f"Edge '{edge.id}' references non-existent target node: {edge.to_node}")

            # Add to adjacency list
            if edge.from_node in adjacency:
                adjacency[edge.from_node].append(edge.to_node)

        # Find reachable nodes via BFS
        if start_node_exists:
            visited = set()
            queue = [spec.start]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                reachable_nodes.append(current)

                # Add neighbors
                if current in adjacency:
                    for neighbor in adjacency[current]:
                        if neighbor not in visited:
                            queue.append(neighbor)

            # Find orphaned nodes
            all_node_ids = {node.id for node in spec.nodes}
            orphaned_nodes = list(all_node_ids - visited)

            if orphaned_nodes:
                warnings.append(f"Found {len(orphaned_nodes)} unreachable node(s): {', '.join(orphaned_nodes)}")

        # Detect cycles using DFS
        def find_cycles_dfs(node, path, visited_in_path):
            if node in visited_in_path:
                # Found a cycle
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                if cycle not in cycles:
                    cycles.append(cycle)
                return

            visited_in_path.add(node)
            path.append(node)

            if node in adjacency:
                for neighbor in adjacency[node]:
                    find_cycles_dfs(neighbor, path[:], visited_in_path.copy())

        # Check for cycles from start node
        if start_node_exists:
            find_cycles_dfs(spec.start, [], set())

        if cycles:
            # Cycles might be intentional in some graphs
            warnings.append(f"Found {len(cycles)} cycle(s) in graph")

        # Check if graph has at least one execution path
        if start_node_exists and len(reachable_nodes) == 0:
            errors.append("Graph has no executable nodes")

        # Determine validity
        is_valid = len(errors) == 0

        return StructuralValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            reachable_nodes=reachable_nodes,
            orphaned_nodes=orphaned_nodes,
            cycles=cycles
        )

    def compute_structural_diff(
        self,
        baseline: GraphSpec,
        modified: GraphSpec
    ) -> StructuralDiff:
        """Compute detailed structural differences.

        Args:
            baseline: Baseline graph specification
            modified: Modified graph specification

        Returns:
            Detailed structural diff
        """
        # Get node IDs
        baseline_node_ids = {node.id for node in baseline.nodes}
        modified_node_ids = {node.id for node in modified.nodes}

        # Compute node differences
        nodes_added = list(modified_node_ids - baseline_node_ids)
        nodes_removed = list(baseline_node_ids - modified_node_ids)

        # Find modified nodes
        nodes_modified = []
        common_nodes = baseline_node_ids & modified_node_ids
        for node_id in common_nodes:
            baseline_node = next(n for n in baseline.nodes if n.id == node_id)
            modified_node = next(n for n in modified.nodes if n.id == node_id)

            # Check for modifications
            if baseline_node.type != modified_node.type:
                nodes_modified.append(NodeModification(
                    node_id=node_id,
                    field='type',
                    old_value=baseline_node.type,
                    new_value=modified_node.type
                ))

            if baseline_node.config != modified_node.config:
                nodes_modified.append(NodeModification(
                    node_id=node_id,
                    field='config',
                    old_value=baseline_node.config,
                    new_value=modified_node.config
                ))

        # Get edge IDs
        baseline_edge_ids = {edge.id for edge in baseline.edges}
        modified_edge_ids = {edge.id for edge in modified.edges}

        # Compute edge differences
        edges_added = list(modified_edge_ids - baseline_edge_ids)
        edges_removed = list(baseline_edge_ids - modified_edge_ids)

        # Find modified edges
        edges_modified = []
        common_edges = baseline_edge_ids & modified_edge_ids
        for edge_id in common_edges:
            baseline_edge = next(e for e in baseline.edges if e.id == edge_id)
            modified_edge = next(e for e in modified.edges if e.id == edge_id)

            # Check for modifications
            if baseline_edge.condition != modified_edge.condition:
                edges_modified.append(EdgeModification(
                    edge_id=edge_id,
                    field='condition',
                    old_value=baseline_edge.condition,
                    new_value=modified_edge.condition
                ))

            if baseline_edge.priority != modified_edge.priority:
                edges_modified.append(EdgeModification(
                    edge_id=edge_id,
                    field='priority',
                    old_value=baseline_edge.priority,
                    new_value=modified_edge.priority
                ))

        # Calculate complexity delta
        complexity_delta = len(modified.nodes) - len(baseline.nodes)

        # Generate summary
        summary_parts = []
        if nodes_added:
            summary_parts.append(f"{len(nodes_added)} node(s) added")
        if nodes_removed:
            summary_parts.append(f"{len(nodes_removed)} node(s) removed")
        if nodes_modified:
            summary_parts.append(f"{len(nodes_modified)} node(s) modified")
        if edges_added:
            summary_parts.append(f"{len(edges_added)} edge(s) added")
        if edges_removed:
            summary_parts.append(f"{len(edges_removed)} edge(s) removed")
        if edges_modified:
            summary_parts.append(f"{len(edges_modified)} edge(s) modified")

        summary = ", ".join(summary_parts) if summary_parts else "No changes"

        return StructuralDiff(
            nodes_added=nodes_added,
            nodes_removed=nodes_removed,
            nodes_modified=nodes_modified,
            edges_added=edges_added,
            edges_removed=edges_removed,
            edges_modified=edges_modified,
            complexity_delta=complexity_delta,
            summary=summary
        )

    def _apply_node_replacement(self, spec: GraphSpec, change: ChangeSpec) -> GraphSpec:
        """Replace one node with another, preserving edges.

        Steps:
        1. Get all edges to/from original node
        2. Remove original node
        3. Add replacement node
        4. Rewire edges to replacement node
        5. Validate connectivity

        Args:
            spec: The graph specification to modify
            change: The change specification with replacement details

        Returns:
            Modified graph specification

        Raises:
            ChangeApplicationError: If replacement cannot be applied
        """
        target_node_id = change.target_node_id
        if not target_node_id:
            raise ChangeApplicationError("node_replacement requires target_node_id")

        replacement_spec_dict = change.additional_params.get('replacement_node_spec')
        if not replacement_spec_dict:
            raise ChangeApplicationError("node_replacement requires 'replacement_node_spec' in additional_params")

        # Find original node
        node_idx = self._find_node_index(spec, target_node_id)
        if node_idx is None:
            raise ChangeApplicationError(f"Node not found: {target_node_id}")

        original_node = spec.nodes[node_idx]

        # Create replacement node
        replacement_node = NodeSpec(**replacement_spec_dict)

        # Get all edges connected to original node
        incoming_edges = [e for e in spec.edges if e.to_node == target_node_id]
        outgoing_edges = [e for e in spec.edges if e.from_node == target_node_id]

        # Remove original node (this also removes connected edges)
        spec.nodes.pop(node_idx)
        spec.edges = [
            edge for edge in spec.edges
            if edge.from_node != target_node_id and edge.to_node != target_node_id
        ]

        # Add replacement node
        spec.nodes.append(replacement_node)

        # Rewire incoming edges to replacement
        for edge in incoming_edges:
            new_edge = EdgeSpec(
                id=f"{edge.id}_rewired",
                from_node=edge.from_node,
                to_node=replacement_node.id,
                condition=edge.condition,
                priority=edge.priority,
                description=edge.description
            )
            spec.edges.append(new_edge)

        # Rewire outgoing edges from replacement
        for edge in outgoing_edges:
            new_edge = EdgeSpec(
                id=f"{edge.id}_rewired",
                from_node=replacement_node.id,
                to_node=edge.to_node,
                condition=edge.condition,
                priority=edge.priority,
                description=edge.description
            )
            spec.edges.append(new_edge)

        # Update start node if needed
        if spec.start == target_node_id:
            spec.start = replacement_node.id

        logger.debug(f"Replaced node {target_node_id} with {replacement_node.id}, rewired {len(incoming_edges) + len(outgoing_edges)} edge(s)")

        return spec

    def _apply_edge_batch_modifications(self, spec: GraphSpec, change: ChangeSpec) -> GraphSpec:
        """Apply multiple edge changes atomically.

        Used by EdgeOptimizer to:
        - Remove redundant edges
        - Add shortcuts
        - Modify conditions

        All-or-nothing: either all succeed or none applied.

        Args:
            spec: The graph specification to modify
            change: The change specification with batch modifications

        Returns:
            Modified graph specification

        Raises:
            ChangeApplicationError: If batch modifications cannot be applied
        """
        edge_modifications = change.additional_params.get('edge_modifications', [])
        if not edge_modifications:
            raise ChangeApplicationError("edge_batch_modifications requires 'edge_modifications' in additional_params")

        # Validate all modifications first (all-or-nothing)
        for mod in edge_modifications:
            mod_type = mod.get('type')
            if mod_type == 'remove':
                edge_id = mod.get('edge_id')
                if self._find_edge_index(spec, edge_id) is None:
                    raise ChangeApplicationError(f"Edge not found for removal: {edge_id}")

            elif mod_type == 'add':
                edge_spec_dict = mod.get('edge_spec')
                if not edge_spec_dict:
                    raise ChangeApplicationError("Edge add requires 'edge_spec'")
                # Validate nodes exist
                from_node = edge_spec_dict.get('from_node')
                to_node = edge_spec_dict.get('to_node')
                if self._find_node_index(spec, from_node) is None:
                    raise ChangeApplicationError(f"Source node not found: {from_node}")
                if self._find_node_index(spec, to_node) is None:
                    raise ChangeApplicationError(f"Target node not found: {to_node}")

            elif mod_type == 'modify':
                edge_id = mod.get('edge_id')
                if self._find_edge_index(spec, edge_id) is None:
                    raise ChangeApplicationError(f"Edge not found for modification: {edge_id}")

            else:
                raise ChangeApplicationError(f"Unknown edge modification type: {mod_type}")

        # Apply all modifications
        for mod in edge_modifications:
            mod_type = mod['type']

            if mod_type == 'remove':
                edge_id = mod['edge_id']
                edge_idx = self._find_edge_index(spec, edge_id)
                spec.edges.pop(edge_idx)
                logger.debug(f"Batch: Removed edge {edge_id}")

            elif mod_type == 'add':
                edge_spec_dict = mod['edge_spec']
                new_edge = EdgeSpec(**edge_spec_dict)
                spec.edges.append(new_edge)
                logger.debug(f"Batch: Added edge {new_edge.id}")

            elif mod_type == 'modify':
                edge_id = mod['edge_id']
                edge_idx = self._find_edge_index(spec, edge_id)
                edge = spec.edges[edge_idx]

                updates = mod.get('updates', {})
                if 'condition' in updates:
                    edge.condition = updates['condition']
                if 'priority' in updates:
                    edge.priority = updates['priority']
                if 'description' in updates:
                    edge.description = updates['description']

                logger.debug(f"Batch: Modified edge {edge_id}")

        logger.info(f"Applied {len(edge_modifications)} edge modification(s) in batch")

        return spec

    def _apply_parallelization(self, spec: GraphSpec, change: ChangeSpec) -> GraphSpec:
        """Convert sequential path to parallel branches.

        Steps:
        1. Parse ParallelGraphStructure from change
        2. Create parallel branch nodes
        3. Remove sequential edges
        4. Add parallel edges from entry node
        5. Add merge node if needed
        6. Connect branches to merge node
        7. Validate no cycles introduced

        Args:
            spec: The graph specification to modify
            change: The change specification with parallelization details

        Returns:
            Modified graph specification

        Raises:
            ChangeApplicationError: If parallelization cannot be applied
        """
        parallel_structure_dict = change.additional_params.get('parallel_structure')
        if not parallel_structure_dict:
            raise ChangeApplicationError("parallelization requires 'parallel_structure' in additional_params")

        # Parse parallel structure
        parallel_structure = ParallelGraphStructure(**parallel_structure_dict)

        entry_node = change.additional_params.get('entry_node')
        if not entry_node:
            raise ChangeApplicationError("parallelization requires 'entry_node' in additional_params")

        # Validate entry node exists
        if self._find_node_index(spec, entry_node) is None:
            raise ChangeApplicationError(f"Entry node not found: {entry_node}")

        # Validate all branch nodes exist
        for branch_idx, branch in enumerate(parallel_structure.parallel_branches):
            for node_id in branch:
                if self._find_node_index(spec, node_id) is None:
                    raise ChangeApplicationError(f"Branch node not found: {node_id} (branch {branch_idx})")

        # Remove sequential edges between nodes in the parallelizable sequence
        sequential_nodes = [entry_node]
        for branch in parallel_structure.parallel_branches:
            sequential_nodes.extend(branch)

        # Remove edges between sequential nodes
        spec.edges = [
            edge for edge in spec.edges
            if not (edge.from_node in sequential_nodes and edge.to_node in sequential_nodes)
        ]

        # Add parallel edges from entry node to first node of each branch
        for branch_idx, branch in enumerate(parallel_structure.parallel_branches):
            if branch:  # Non-empty branch
                first_node = branch[0]
                parallel_edge = EdgeSpec(
                    id=f"{entry_node}_to_branch{branch_idx}",
                    from_node=entry_node,
                    to_node=first_node,
                    condition=None,  # Parallel branches run unconditionally
                    priority=branch_idx,
                    description=f"Parallel branch {branch_idx}"
                )
                spec.edges.append(parallel_edge)

                # Add edges within branch (sequential within branch)
                for i in range(len(branch) - 1):
                    branch_edge = EdgeSpec(
                        id=f"branch{branch_idx}_edge{i}",
                        from_node=branch[i],
                        to_node=branch[i+1],
                        condition=None,
                        priority=0,
                        description=f"Branch {branch_idx} internal"
                    )
                    spec.edges.append(branch_edge)

        # Add merge node if required
        if parallel_structure.requires_merge and parallel_structure.merge_node_id:
            merge_node_id = parallel_structure.merge_node_id

            # Check if merge node already exists
            if self._find_node_index(spec, merge_node_id) is None:
                # Create merge node
                merge_node = NodeSpec(
                    id=merge_node_id,
                    type="MergeNode",
                    config={'merge_strategy': parallel_structure.merge_strategy}
                )
                spec.nodes.append(merge_node)
                logger.debug(f"Created merge node: {merge_node_id}")

            # Remove any existing edges to merge node from branch nodes
            branch_last_nodes = {branch[-1] for branch in parallel_structure.parallel_branches if branch}
            spec.edges = [
                edge for edge in spec.edges
                if not (edge.to_node == merge_node_id and edge.from_node in branch_last_nodes)
            ]

            # Connect last node of each branch to merge node
            for branch_idx, branch in enumerate(parallel_structure.parallel_branches):
                if branch:  # Non-empty branch
                    last_node = branch[-1]
                    merge_edge = EdgeSpec(
                        id=f"branch{branch_idx}_to_merge",
                        from_node=last_node,
                        to_node=merge_node_id,
                        condition=None,
                        priority=0,
                        description=f"Branch {branch_idx} to merge"
                    )
                    spec.edges.append(merge_edge)

        logger.info(f"Parallelized {len(parallel_structure.parallel_branches)} branches from {entry_node}")

        return spec
