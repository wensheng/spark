"""Node replacement analysis for RSI system.

This module identifies opportunities to replace underperforming nodes with
better implementations while maintaining interface compatibility.
"""

from typing import Dict, List, Optional, Any
from spark.rsi.types import (
    NodeReplacementCandidate,
    CompatibilityReport,
    ImpactEstimate,
    ExpectedImprovement,
    NodeMetrics,
)
from spark.rsi.introspection import GraphIntrospector
from spark.nodes.spec import NodeSpec


class NodeReplacementAnalyzer:
    """Analyzes nodes and identifies replacement candidates.

    Capabilities:
    - Identify functionally equivalent node types
    - Validate interface compatibility (inputs/outputs)
    - Assess replacement risk
    - Generate replacement proposals
    """

    def __init__(
        self,
        min_compatibility_score: float = 0.7,
        enable_mock_mode: bool = False
    ):
        """Initialize the node replacement analyzer.

        Args:
            min_compatibility_score: Minimum compatibility score for candidates (0.0 to 1.0)
            enable_mock_mode: If True, use mock data instead of real analysis
        """
        self.min_compatibility_score = min_compatibility_score
        self.enable_mock_mode = enable_mock_mode

        # Registry of known node types and their relationships
        self._node_type_registry: Dict[str, Dict[str, Any]] = {}
        self._initialize_node_registry()

    def _initialize_node_registry(self):
        """Initialize the registry of known node types and their properties."""
        # This would be populated from Spark's node system
        # For now, we define some common patterns

        # LLM nodes - different providers but same interface
        self._node_type_registry["OpenAINode"] = {
            "category": "llm",
            "input_schema": {"messages": "list", "system_prompt": "str"},
            "output_schema": {"text": "str", "model_output": "dict"},
            "capabilities": ["text_generation", "chat"],
            "equivalent_types": ["BedrockNode", "GeminiNode"],
        }

        self._node_type_registry["BedrockNode"] = {
            "category": "llm",
            "input_schema": {"messages": "list", "system_prompt": "str"},
            "output_schema": {"text": "str", "model_output": "dict"},
            "capabilities": ["text_generation", "chat"],
            "equivalent_types": ["OpenAINode", "GeminiNode"],
        }

        self._node_type_registry["GeminiNode"] = {
            "category": "llm",
            "input_schema": {"messages": "list", "system_prompt": "str"},
            "output_schema": {"text": "str", "model_output": "dict"},
            "capabilities": ["text_generation", "chat"],
            "equivalent_types": ["OpenAINode", "BedrockNode"],
        }

        # Processing nodes
        self._node_type_registry["TransformNode"] = {
            "category": "processing",
            "input_schema": {"data": "any"},
            "output_schema": {"result": "any"},
            "capabilities": ["transformation"],
            "equivalent_types": [],
        }

    async def find_replacement_candidates(
        self,
        node_spec: NodeSpec,
        graph_introspector: GraphIntrospector,
        node_metrics: Optional[NodeMetrics] = None
    ) -> List[NodeReplacementCandidate]:
        """Find suitable replacement nodes for the given node.

        Args:
            node_spec: Specification of the node to replace
            graph_introspector: Graph introspector for context
            node_metrics: Performance metrics for the node (optional)

        Returns:
            List of replacement candidates sorted by compatibility score
        """
        if self.enable_mock_mode:
            return self._generate_mock_candidates(node_spec, node_metrics)

        candidates = []
        node_type = node_spec.type

        # Look up node in registry
        if node_type not in self._node_type_registry:
            # Unknown node type, cannot find replacements
            return candidates

        node_info = self._node_type_registry[node_type]
        equivalent_types = node_info.get("equivalent_types", [])

        # Evaluate each equivalent type
        for equiv_type in equivalent_types:
            if equiv_type not in self._node_type_registry:
                continue

            equiv_info = self._node_type_registry[equiv_type]

            # Calculate compatibility score
            compatibility_score = self._calculate_compatibility_score(
                node_info, equiv_info
            )

            if compatibility_score < self.min_compatibility_score:
                continue

            # Estimate expected improvement
            expected_improvement = self._estimate_improvement(
                node_spec, equiv_type, node_metrics
            )

            # Identify risk factors
            risk_factors = self._identify_risk_factors(
                node_spec, equiv_type, node_metrics
            )

            # Create candidate
            candidate = NodeReplacementCandidate(
                replacement_node_type=equiv_type,
                replacement_node_name=f"{equiv_type}_{node_spec.id}",
                compatibility_score=compatibility_score,
                expected_improvement=expected_improvement,
                compatibility_notes=[
                    f"Category: {equiv_info.get('category', 'unknown')}",
                    f"Capabilities: {', '.join(equiv_info.get('capabilities', []))}",
                ],
                risk_factors=risk_factors
            )
            candidates.append(candidate)

        # Sort by compatibility score (descending)
        candidates.sort(key=lambda c: c.compatibility_score, reverse=True)

        return candidates

    def _calculate_compatibility_score(
        self,
        original_info: Dict[str, Any],
        replacement_info: Dict[str, Any]
    ) -> float:
        """Calculate compatibility score between two node types.

        Args:
            original_info: Info about original node type
            replacement_info: Info about replacement node type

        Returns:
            Compatibility score from 0.0 to 1.0
        """
        score = 0.0
        weights = {
            "category": 0.3,
            "input_schema": 0.25,
            "output_schema": 0.25,
            "capabilities": 0.2,
        }

        # Category match
        if original_info.get("category") == replacement_info.get("category"):
            score += weights["category"]

        # Input schema compatibility
        orig_inputs = original_info.get("input_schema", {})
        repl_inputs = replacement_info.get("input_schema", {})
        input_match = self._schema_compatibility(orig_inputs, repl_inputs)
        score += weights["input_schema"] * input_match

        # Output schema compatibility
        orig_outputs = original_info.get("output_schema", {})
        repl_outputs = replacement_info.get("output_schema", {})
        output_match = self._schema_compatibility(orig_outputs, repl_outputs)
        score += weights["output_schema"] * output_match

        # Capabilities overlap
        orig_caps = set(original_info.get("capabilities", []))
        repl_caps = set(replacement_info.get("capabilities", []))
        if orig_caps:
            cap_overlap = len(orig_caps & repl_caps) / len(orig_caps)
            score += weights["capabilities"] * cap_overlap
        else:
            score += weights["capabilities"]

        return min(score, 1.0)

    def _schema_compatibility(
        self,
        schema1: Dict[str, str],
        schema2: Dict[str, str]
    ) -> float:
        """Calculate schema compatibility.

        Args:
            schema1: First schema
            schema2: Second schema

        Returns:
            Compatibility score from 0.0 to 1.0
        """
        if not schema1 and not schema2:
            return 1.0

        if not schema1 or not schema2:
            return 0.0

        # Check if all keys in schema1 exist in schema2
        keys1 = set(schema1.keys())
        keys2 = set(schema2.keys())

        if not keys1:
            return 1.0

        # Keys that match
        matching_keys = keys1 & keys2
        match_ratio = len(matching_keys) / len(keys1)

        # Type compatibility for matching keys
        type_matches = 0
        for key in matching_keys:
            if schema1[key] == schema2[key] or schema1[key] == "any" or schema2[key] == "any":
                type_matches += 1

        if matching_keys:
            type_ratio = type_matches / len(matching_keys)
        else:
            type_ratio = 0.0

        # Weighted average
        return 0.5 * match_ratio + 0.5 * type_ratio

    def _estimate_improvement(
        self,
        node_spec: NodeSpec,
        replacement_type: str,
        node_metrics: Optional[NodeMetrics]
    ) -> ExpectedImprovement:
        """Estimate expected improvement from replacement.

        Args:
            node_spec: Original node spec
            replacement_type: Replacement node type
            node_metrics: Performance metrics for the node

        Returns:
            Expected improvement metrics
        """
        # Default: no expected improvement without metrics
        if not node_metrics:
            return ExpectedImprovement()

        # Heuristics based on node type patterns
        improvement = ExpectedImprovement()

        # Example heuristics
        if "OpenAI" in node_spec.type and "Bedrock" in replacement_type:
            # Bedrock might have better latency
            improvement.latency_delta = -0.1  # 10% faster
            improvement.cost_delta = -0.05  # 5% cheaper
        elif "Bedrock" in node_spec.type and "OpenAI" in replacement_type:
            # OpenAI might have better quality
            improvement.quality_delta = 0.05  # 5% better quality

        # If node has high error rate, replacement might improve it
        if node_metrics and node_metrics.error_rate > 0.1:
            improvement.success_rate_delta = 0.05  # 5% improvement

        return improvement

    def _identify_risk_factors(
        self,
        node_spec: NodeSpec,
        replacement_type: str,
        node_metrics: Optional[NodeMetrics]
    ) -> List[str]:
        """Identify risk factors for node replacement.

        Args:
            node_spec: Original node spec
            replacement_type: Replacement node type
            node_metrics: Performance metrics for the node

        Returns:
            List of risk factor descriptions
        """
        risk_factors = []

        # Different provider = higher risk
        if node_spec.type != replacement_type:
            risk_factors.append(
                f"Changing node type from {node_spec.type} to {replacement_type}"
            )

        # High traffic node = higher risk
        if node_metrics and node_metrics.executions > 1000:
            risk_factors.append(
                f"High-traffic node ({node_metrics.executions} executions)"
            )

        # Currently reliable node = higher risk if it breaks
        if node_metrics and node_metrics.success_rate > 0.95:
            risk_factors.append(
                f"Currently highly reliable ({node_metrics.success_rate:.1%} success rate)"
            )

        # API compatibility risk
        risk_factors.append(
            "API differences may require configuration adjustments"
        )

        return risk_factors

    async def validate_replacement_compatibility(
        self,
        original: NodeSpec,
        replacement: NodeSpec
    ) -> CompatibilityReport:
        """Validate that replacement node is compatible with original.

        Args:
            original: Original node specification
            replacement: Replacement node specification

        Returns:
            Compatibility report with detailed analysis
        """
        if self.enable_mock_mode:
            return self._generate_mock_compatibility_report(original, replacement)

        issues = []
        warnings = []
        recommendations = []

        # Check node type
        orig_type = original.type
        repl_type = replacement.type

        if orig_type not in self._node_type_registry:
            warnings.append(f"Original node type '{orig_type}' not in registry")

        if repl_type not in self._node_type_registry:
            warnings.append(f"Replacement node type '{repl_type}' not in registry")

        # Get node info
        orig_info = self._node_type_registry.get(orig_type, {})
        repl_info = self._node_type_registry.get(repl_type, {})

        # Check input compatibility
        input_compatible = True
        if orig_info and repl_info:
            orig_inputs = orig_info.get("input_schema", {})
            repl_inputs = repl_info.get("input_schema", {})

            for key, type_hint in orig_inputs.items():
                if key not in repl_inputs:
                    issues.append(f"Missing input field: {key}")
                    input_compatible = False
                elif repl_inputs[key] != type_hint and repl_inputs[key] != "any":
                    warnings.append(
                        f"Input type mismatch for '{key}': "
                        f"{type_hint} -> {repl_inputs[key]}"
                    )

        # Check output compatibility
        output_compatible = True
        if orig_info and repl_info:
            orig_outputs = orig_info.get("output_schema", {})
            repl_outputs = repl_info.get("output_schema", {})

            for key, type_hint in orig_outputs.items():
                if key not in repl_outputs:
                    issues.append(f"Missing output field: {key}")
                    output_compatible = False
                elif repl_outputs[key] != type_hint and repl_outputs[key] != "any":
                    warnings.append(
                        f"Output type mismatch for '{key}': "
                        f"{type_hint} -> {repl_outputs[key]}"
                    )

        # Generate recommendations
        if issues:
            recommendations.append("Address interface compatibility issues before replacement")
        if warnings:
            recommendations.append("Test replacement thoroughly to verify compatibility")
        if not issues and not warnings:
            recommendations.append("Replacement appears compatible, proceed with testing")

        # Calculate overall compatibility score
        compatibility_score = self._calculate_compatibility_score(orig_info, repl_info)

        # Determine if compatible
        is_compatible = len(issues) == 0 and compatibility_score >= self.min_compatibility_score

        return CompatibilityReport(
            is_compatible=is_compatible,
            compatibility_score=compatibility_score,
            input_compatibility=input_compatible,
            output_compatibility=output_compatible,
            interface_issues=issues,
            warnings=warnings,
            recommendations=recommendations
        )

    async def estimate_replacement_impact(
        self,
        node_id: str,
        replacement_candidate: NodeReplacementCandidate,
        historical_metrics: Dict[str, Any]
    ) -> ImpactEstimate:
        """Estimate impact of replacing a node.

        Args:
            node_id: ID of node to replace
            replacement_candidate: Candidate replacement
            historical_metrics: Historical performance metrics

        Returns:
            Impact estimate with confidence level
        """
        if self.enable_mock_mode:
            return self._generate_mock_impact_estimate(node_id, replacement_candidate)

        # Extract metrics
        avg_latency = historical_metrics.get("avg_duration", 0.0)
        success_rate = historical_metrics.get("success_rate", 1.0)
        cost_per_exec = historical_metrics.get("cost_per_execution", 0.0)

        # Use expected improvement from candidate
        expected = replacement_candidate.expected_improvement
        if not expected:
            expected = ExpectedImprovement()

        # Calculate impacts
        latency_impact = expected.latency_delta * 100  # Convert to percentage
        cost_impact = expected.cost_delta * 100
        reliability_impact = expected.success_rate_delta * 100

        # Complexity delta (replacement doesn't change complexity much)
        complexity_delta = 0

        # Confidence based on data availability and compatibility
        confidence = replacement_candidate.compatibility_score * 0.7
        if historical_metrics.get("execution_count", 0) > 100:
            confidence += 0.2  # More data = higher confidence
        if not replacement_candidate.risk_factors:
            confidence += 0.1
        confidence = min(confidence, 1.0)

        # Assumptions
        assumptions = [
            "Replacement maintains same functional behavior",
            "Configuration can be migrated successfully",
            f"Based on {historical_metrics.get('execution_count', 0)} historical executions",
        ]
        assumptions.extend(replacement_candidate.compatibility_notes)

        return ImpactEstimate(
            latency_impact=latency_impact,
            cost_impact=cost_impact,
            reliability_impact=reliability_impact,
            complexity_delta=complexity_delta,
            confidence=confidence,
            assumptions=assumptions
        )

    # ========================================================================
    # Mock Mode Helpers
    # ========================================================================

    def _generate_mock_candidates(
        self,
        node_spec: NodeSpec,
        node_metrics: Optional[NodeMetrics]
    ) -> List[NodeReplacementCandidate]:
        """Generate mock replacement candidates for testing."""
        candidates = []

        # Generate 2-3 mock candidates
        if "OpenAI" in node_spec.type or "LLM" in node_spec.type:
            candidates.append(NodeReplacementCandidate(
                replacement_node_type="BedrockNode",
                replacement_node_name=f"BedrockNode_{node_spec.id}",
                compatibility_score=0.85,
                expected_improvement=ExpectedImprovement(
                    latency_delta=-0.15,
                    cost_delta=-0.10,
                ),
                compatibility_notes=[
                    "Category: llm",
                    "Capabilities: text_generation, chat",
                ],
                risk_factors=[
                    "Different API format",
                    "Configuration migration required",
                ]
            ))

            candidates.append(NodeReplacementCandidate(
                replacement_node_type="GeminiNode",
                replacement_node_name=f"GeminiNode_{node_spec.id}",
                compatibility_score=0.78,
                expected_improvement=ExpectedImprovement(
                    latency_delta=-0.08,
                    cost_delta=-0.15,
                ),
                compatibility_notes=[
                    "Category: llm",
                    "Capabilities: text_generation, chat, multimodal",
                ],
                risk_factors=[
                    "Different API format",
                    "May require prompt adjustments",
                ]
            ))

        return candidates

    def _generate_mock_compatibility_report(
        self,
        original: NodeSpec,
        replacement: NodeSpec
    ) -> CompatibilityReport:
        """Generate mock compatibility report for testing."""
        return CompatibilityReport(
            is_compatible=True,
            compatibility_score=0.85,
            input_compatibility=True,
            output_compatibility=True,
            interface_issues=[],
            warnings=["Mock mode: Compatibility not fully validated"],
            recommendations=["Test replacement in staging environment"]
        )

    def _generate_mock_impact_estimate(
        self,
        node_id: str,
        replacement_candidate: NodeReplacementCandidate
    ) -> ImpactEstimate:
        """Generate mock impact estimate for testing."""
        return ImpactEstimate(
            latency_impact=-12.0,  # 12% improvement
            cost_impact=-8.0,  # 8% reduction
            reliability_impact=2.0,  # 2% improvement
            complexity_delta=0,
            confidence=0.75,
            assumptions=[
                "Mock mode: Estimates are simulated",
                "Based on typical replacement patterns",
                "Actual results may vary",
            ]
        )
