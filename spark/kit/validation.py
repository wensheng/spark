"""
Round-trip validation for graph specifications.

This module provides utilities to validate that:
- export → import → export produces equivalent specs
- specs can be loaded into working runtime graphs
- all references are valid and loadable

Phase 2 Enhancement: Full-fidelity validation.
"""

from __future__ import annotations

import logging
from typing import Any, List, Tuple

from spark.nodes.spec import GraphSpec, NodeSpec, EdgeSpec
from spark.graphs.base import BaseGraph
from spark.nodes.serde import graph_to_spec
from spark.kit.loader import SpecLoader, SpecLoaderError

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Base exception for validation errors."""
    pass


def validate_round_trip(graph: BaseGraph, import_policy: str = 'safe') -> Tuple[bool, List[str]]:
    """Validate that graph can be serialized and reconstructed.

    Performs a full round-trip test:
    1. Export graph → GraphSpec
    2. Load GraphSpec → new Graph
    3. Export new Graph → GraphSpec2
    4. Compare GraphSpec and GraphSpec2

    Args:
        graph: Runtime Graph to test
        import_policy: Import policy for SpecLoader ('safe' or 'allow_all')

    Returns:
        Tuple of (success: bool, issues: List[str])
        success is True if no issues found, issues lists any problems
    """
    issues: List[str] = []

    try:
        # Step 1: Export to spec
        logger.debug("Step 1: Exporting graph to spec...")
        spec1 = graph_to_spec(graph)

        # Step 2: Load back
        logger.debug("Step 2: Loading spec back to graph...")
        loader = SpecLoader(import_policy=import_policy)
        try:
            graph2 = loader.load_graph(spec1)
        except SpecLoaderError as e:
            issues.append(f"Failed to load spec back into graph: {e}")
            return False, issues

        # Step 3: Export again
        logger.debug("Step 3: Exporting reconstructed graph...")
        spec2 = graph_to_spec(graph2)

        # Step 4: Compare specs
        logger.debug("Step 4: Comparing specs...")
        comparison_issues = compare_specs(spec1, spec2)
        issues.extend(comparison_issues)

        return len(issues) == 0, issues

    except Exception as e:
        issues.append(f"Round-trip validation failed with exception: {e}")
        return False, issues


def compare_specs(spec1: GraphSpec, spec2: GraphSpec, strict: bool = False) -> List[str]:
    """Deep comparison of two GraphSpecs.

    Args:
        spec1: First GraphSpec
        spec2: Second GraphSpec
        strict: If True, requires exact match including IDs and metadata
                If False, allows some differences (e.g., generated IDs)

    Returns:
        List of difference descriptions (empty if specs are equivalent)
    """
    differences: List[str] = []

    # Compare basic fields
    if spec1.spark_version != spec2.spark_version:
        differences.append(
            f"spark_version differs: '{spec1.spark_version}' vs '{spec2.spark_version}'"
        )

    if strict and spec1.id != spec2.id:
        differences.append(f"graph id differs: '{spec1.id}' vs '{spec2.id}'")

    if spec1.description != spec2.description:
        differences.append(
            f"description differs: '{spec1.description}' vs '{spec2.description}'"
        )

    if spec1.start != spec2.start:
        differences.append(f"start node differs: '{spec1.start}' vs '{spec2.start}'")

    # Compare nodes
    node_diffs = _compare_node_lists(spec1.nodes, spec2.nodes, strict)
    differences.extend(node_diffs)

    # Compare edges
    edge_diffs = _compare_edge_lists(spec1.edges, spec2.edges, strict)
    differences.extend(edge_diffs)

    # Compare graph features
    feature_diffs = _compare_graph_features(spec1, spec2)
    differences.extend(feature_diffs)

    return differences


def _compare_node_lists(
    nodes1: List[NodeSpec],
    nodes2: List[NodeSpec],
    strict: bool
) -> List[str]:
    """Compare two lists of NodeSpecs."""
    differences: List[str] = []

    if len(nodes1) != len(nodes2):
        differences.append(
            f"Node count differs: {len(nodes1)} vs {len(nodes2)}"
        )
        return differences

    # Create lookup by ID
    nodes1_map = {n.id: n for n in nodes1}
    nodes2_map = {n.id: n for n in nodes2}

    # Check all nodes from spec1 exist in spec2
    for node_id, node1 in nodes1_map.items():
        if node_id not in nodes2_map:
            differences.append(f"Node '{node_id}' missing in second spec")
            continue

        node2 = nodes2_map[node_id]

        # Compare node attributes
        if node1.type != node2.type:
            differences.append(
                f"Node '{node_id}' type differs: '{node1.type}' vs '{node2.type}'"
            )

        if node1.description != node2.description:
            differences.append(
                f"Node '{node_id}' description differs"
            )

        # Compare configs (fuzzy comparison for non-strict mode)
        if node1.config != node2.config:
            if strict:
                differences.append(f"Node '{node_id}' config differs")
            else:
                # In non-strict mode, check key fields only
                config_diffs = _compare_configs(node1.config, node2.config, node_id)
                differences.extend(config_diffs)

    # Check for extra nodes in spec2
    for node_id in nodes2_map:
        if node_id not in nodes1_map:
            differences.append(f"Extra node '{node_id}' in second spec")

    return differences


def _compare_configs(
    config1: Any,
    config2: Any,
    node_id: str
) -> List[str]:
    """Compare node configurations with fuzzy matching."""
    differences: List[str] = []

    if config1 is None and config2 is None:
        return differences

    if config1 is None or config2 is None:
        differences.append(f"Node '{node_id}' config presence differs")
        return differences

    # Compare key fields for common node types
    if isinstance(config1, dict) and isinstance(config2, dict):
        # Check important fields
        key_fields = ['model', 'system_prompt', 'tool_choice', 'max_steps']
        for field in key_fields:
            if field in config1 or field in config2:
                val1 = config1.get(field)
                val2 = config2.get(field)
                if val1 != val2:
                    differences.append(
                        f"Node '{node_id}' config.{field} differs: {val1} vs {val2}"
                    )

    return differences


def _compare_edge_lists(
    edges1: List[EdgeSpec],
    edges2: List[EdgeSpec],
    strict: bool
) -> List[str]:
    """Compare two lists of EdgeSpecs."""
    differences: List[str] = []

    if len(edges1) != len(edges2):
        differences.append(
            f"Edge count differs: {len(edges1)} vs {len(edges2)}"
        )
        # Continue to check what's different

    # Create lookup by (from_node, to_node)
    def edge_key(e: EdgeSpec) -> Tuple[str, str]:
        return (e.from_node, e.to_node)

    edges1_map = {edge_key(e): e for e in edges1}
    edges2_map = {edge_key(e): e for e in edges2}

    # Check all edges from spec1 exist in spec2
    for key, edge1 in edges1_map.items():
        if key not in edges2_map:
            differences.append(
                f"Edge {key[0]} → {key[1]} missing in second spec"
            )
            continue

        edge2 = edges2_map[key]

        # Compare edge attributes
        if edge1.priority != edge2.priority:
            differences.append(
                f"Edge {key[0]} → {key[1]} priority differs: "
                f"{edge1.priority} vs {edge2.priority}"
            )

        # Compare conditions (flexible comparison)
        if edge1.condition != edge2.condition:
            # Allow some flexibility in condition representation
            if not _conditions_equivalent(edge1.condition, edge2.condition):
                differences.append(
                    f"Edge {key[0]} → {key[1]} condition differs"
                )

    # Check for extra edges in spec2
    for key in edges2_map:
        if key not in edges1_map:
            differences.append(
                f"Extra edge {key[0]} → {key[1]} in second spec"
            )

    return differences


def _conditions_equivalent(cond1: Any, cond2: Any) -> bool:
    """Check if two conditions are equivalent (flexible comparison)."""
    # Both None
    if cond1 is None and cond2 is None:
        return True

    # One None, one not
    if (cond1 is None) != (cond2 is None):
        return False

    # String comparison
    if isinstance(cond1, str) and isinstance(cond2, str):
        return cond1 == cond2

    # ConditionSpec comparison
    from spark.nodes.spec import ConditionSpec
    if isinstance(cond1, ConditionSpec) and isinstance(cond2, ConditionSpec):
        # Compare kind and relevant fields
        if cond1.kind != cond2.kind:
            return False

        if cond1.kind == 'expr':
            return cond1.expr == cond2.expr
        elif cond1.kind == 'equals':
            return cond1.equals == cond2.equals
        elif cond1.kind == 'lambda':
            return cond1.lambda_source == cond2.lambda_source
        elif cond1.kind == 'always':
            return True

    return False


def _compare_graph_features(spec1: GraphSpec, spec2: GraphSpec) -> List[str]:
    """Compare graph-level features (state, event bus, tools)."""
    differences: List[str] = []

    # Compare graph state
    has_state1 = spec1.graph_state is not None
    has_state2 = spec2.graph_state is not None

    if has_state1 != has_state2:
        differences.append(
            f"GraphState presence differs: {has_state1} vs {has_state2}"
        )
    elif has_state1 and has_state2:
        # Both have state - compare initial state keys
        state1_keys = set(spec1.graph_state.initial_state.keys())  # type: ignore
        state2_keys = set(spec2.graph_state.initial_state.keys())  # type: ignore

        if state1_keys != state2_keys:
            differences.append(
                f"GraphState keys differ: {state1_keys} vs {state2_keys}"
            )

    # Compare event bus
    has_bus1 = spec1.event_bus is not None
    has_bus2 = spec2.event_bus is not None

    if has_bus1 != has_bus2:
        differences.append(
            f"EventBus presence differs: {has_bus1} vs {has_bus2}"
        )

    # Compare tools count
    if len(spec1.tools) != len(spec2.tools):
        differences.append(
            f"Tool count differs: {len(spec1.tools)} vs {len(spec2.tools)}"
        )

    return differences


def validate_spec_loadable(spec: GraphSpec, import_policy: str = 'safe') -> Tuple[bool, List[str]]:
    """Validate that a spec can be loaded into a working graph.

    Args:
        spec: GraphSpec to validate
        import_policy: Import policy for SpecLoader

    Returns:
        Tuple of (loadable: bool, errors: List[str])
    """
    errors: List[str] = []

    try:
        # Try to load the graph
        loader = SpecLoader(import_policy=import_policy)

        # Validate imports first
        import_errors = loader.validate_imports(spec)
        errors.extend(import_errors)

        # Try to construct the graph
        try:
            graph = loader.load_graph(spec)
            # Basic sanity checks
            if not graph:
                errors.append("Loaded graph is None")
            elif not hasattr(graph, 'start'):
                errors.append("Loaded graph has no start node")
        except SpecLoaderError as e:
            errors.append(f"Failed to construct graph: {e}")

        return len(errors) == 0, errors

    except Exception as e:
        errors.append(f"Validation failed with exception: {e}")
        return False, errors
