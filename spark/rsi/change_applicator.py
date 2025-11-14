"""Change application for RSI system.

This module provides the ChangeApplicator that applies hypothesis changes to graph
specifications, creating modified versions for testing and deployment.
"""

import copy
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from spark.rsi.types import ImprovementHypothesis, ChangeSpec
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
