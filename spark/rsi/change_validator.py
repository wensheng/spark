"""Change validator for validating improvement hypotheses before testing."""

from spark.nodes import Node
from spark.rsi.types import (
    ImprovementHypothesis,
    ValidationResult,
    ValidationViolation,
    RiskLevel,
    HypothesisType,
)
from spark.rsi.introspection import GraphIntrospector
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class ChangeValidatorNode(Node):
    """Validates improvement hypotheses for safety and correctness.

    This node applies multiple validation rules to ensure proposed changes
    are safe to test. It checks structural integrity, safety constraints,
    and calculates risk scores.

    Usage:
        validator = ChangeValidatorNode(
            max_nodes_added=5,
            max_nodes_removed=2,
            protected_nodes=["authentication", "payment"]
        )

        result = await validator.run({
            'hypothesis': hypothesis,
            'graph': graph
        })

        if result['validation'].approved:
            # Safe to test
            pass
    """

    def __init__(
        self,
        name: str = "ChangeValidator",
        max_nodes_added: int = 5,
        max_nodes_removed: int = 2,
        max_prompt_length: int = 10000,
        protected_nodes: Optional[List[str]] = None,
        allowed_hypothesis_types: Optional[List[str]] = None,
        auto_approve_risk_threshold: float = 0.3,
        **kwargs
    ):
        """Initialize ChangeValidatorNode.

        Args:
            name: Node name
            max_nodes_added: Maximum nodes that can be added
            max_nodes_removed: Maximum nodes that can be removed
            max_prompt_length: Maximum prompt length
            protected_nodes: List of protected node IDs/names
            allowed_hypothesis_types: Allowed hypothesis types
            auto_approve_risk_threshold: Risk threshold for auto-approval
            **kwargs: Additional node configuration
        """
        super().__init__(name=name, **kwargs)
        self.max_nodes_added = max_nodes_added
        self.max_nodes_removed = max_nodes_removed
        self.max_prompt_length = max_prompt_length
        self.protected_nodes = protected_nodes or []
        self.allowed_hypothesis_types = allowed_hypothesis_types or [
            "prompt_optimization",
            "parameter_tuning"
        ]
        self.auto_approve_risk_threshold = auto_approve_risk_threshold

    async def process(self, context):
        """Validate an improvement hypothesis.

        Args:
            context: Execution context with inputs:
                - hypothesis: ImprovementHypothesis (required)
                - graph: Graph object (optional)
                - introspector: GraphIntrospector (optional)

        Returns:
            Dict with:
                - validation: ValidationResult
                - approved: bool
                - risk_score: float
                - risk_level: str
        """
        # Get inputs
        hypothesis = context.inputs.content.get('hypothesis')
        if hypothesis is None:
            logger.error("hypothesis is required")
            return {
                'validation': None,
                'approved': False,
                'error': 'hypothesis is required'
            }

        graph = context.inputs.content.get('graph')
        introspector = context.inputs.content.get('introspector')

        # Create introspector if graph provided
        if graph is not None and introspector is None:
            introspector = GraphIntrospector(graph)

        # Validate hypothesis
        validation = self._validate_hypothesis(hypothesis, introspector)

        logger.info(
            f"Validated hypothesis {hypothesis.hypothesis_id}: "
            f"approved={validation.approved}, risk_score={validation.risk_score:.2f}"
        )

        return {
            'validation': validation,
            'approved': validation.approved,
            'risk_score': validation.risk_score,
            'risk_level': validation.risk_level.value
        }

    def _validate_hypothesis(
        self,
        hypothesis: ImprovementHypothesis,
        introspector: Optional[GraphIntrospector]
    ) -> ValidationResult:
        """Validate a hypothesis.

        Args:
            hypothesis: Hypothesis to validate
            introspector: Graph introspector (optional)

        Returns:
            ValidationResult with approval status and violations
        """
        violations = []
        risk_score = 0.0

        # Validation 1: Check hypothesis type is allowed
        if hypothesis.hypothesis_type.value not in self.allowed_hypothesis_types:
            violations.append(ValidationViolation(
                rule="allowed_hypothesis_types",
                severity="error",
                message=f"Hypothesis type '{hypothesis.hypothesis_type.value}' not allowed",
                details={"allowed": self.allowed_hypothesis_types}
            ))
            risk_score += 1.0

        # Validation 2: Check for protected nodes
        if hypothesis.target_node in self.protected_nodes:
            violations.append(ValidationViolation(
                rule="protected_nodes",
                severity="error",
                message=f"Node '{hypothesis.target_node}' is protected and cannot be modified",
                details={"protected_nodes": self.protected_nodes}
            ))
            risk_score += 1.0

        # Validation 3: Validate changes
        nodes_added = 0
        nodes_removed = 0

        for change in hypothesis.changes:
            # Check change type
            if change.type == "node_add":
                nodes_added += 1
            elif change.type == "node_remove":
                nodes_removed += 1
                # Check if removing protected node
                if change.target_node_id in self.protected_nodes:
                    violations.append(ValidationViolation(
                        rule="protected_nodes",
                        severity="error",
                        message=f"Cannot remove protected node '{change.target_node_id}'",
                        details={}
                    ))
                    risk_score += 1.0

            # Check prompt length for prompt updates
            if change.type == "node_config_update" and change.config_path == "prompt_template":
                if change.new_value and len(str(change.new_value)) > self.max_prompt_length:
                    violations.append(ValidationViolation(
                        rule="max_prompt_length",
                        severity="warning",
                        message=f"Prompt length {len(str(change.new_value))} exceeds maximum {self.max_prompt_length}",
                        details={"length": len(str(change.new_value))}
                    ))
                    risk_score += 0.2

        # Check node addition/removal limits
        if nodes_added > self.max_nodes_added:
            violations.append(ValidationViolation(
                rule="max_nodes_added",
                severity="error",
                message=f"Cannot add {nodes_added} nodes (max: {self.max_nodes_added})",
                details={"nodes_added": nodes_added}
            ))
            risk_score += 0.5

        if nodes_removed > self.max_nodes_removed:
            violations.append(ValidationViolation(
                rule="max_nodes_removed",
                severity="error",
                message=f"Cannot remove {nodes_removed} nodes (max: {self.max_nodes_removed})",
                details={"nodes_removed": nodes_removed}
            ))
            risk_score += 0.5

        # Validation 4: Check structural integrity (if introspector available)
        if introspector:
            struct_violations = self._validate_structural_integrity(
                hypothesis, introspector
            )
            violations.extend(struct_violations)
            risk_score += len(struct_violations) * 0.1

        # Validation 5: Assess risk factors
        risk_score += len(hypothesis.risk_factors) * 0.1

        # Validation 6: Check for missing required fields
        if not hypothesis.rationale:
            violations.append(ValidationViolation(
                rule="required_fields",
                severity="warning",
                message="Missing rationale",
                details={}
            ))
            risk_score += 0.1

        if not hypothesis.changes:
            violations.append(ValidationViolation(
                rule="required_fields",
                severity="error",
                message="No changes specified",
                details={}
            ))
            risk_score += 0.5

        # Determine approval status
        # Reject if any errors
        has_errors = any(v.severity == "error" for v in violations)
        approved = not has_errors

        # Determine risk level
        risk_level = self._calculate_risk_level(risk_score)

        # Generate recommendations
        recommendations = self._generate_recommendations(violations, risk_score)

        return ValidationResult(
            approved=approved,
            risk_level=risk_level,
            risk_score=risk_score,
            violations=violations,
            recommendations=recommendations
        )

    def _validate_structural_integrity(
        self,
        hypothesis: ImprovementHypothesis,
        introspector: GraphIntrospector
    ) -> List[ValidationViolation]:
        """Validate structural integrity of proposed changes.

        Args:
            hypothesis: Hypothesis to validate
            introspector: Graph introspector

        Returns:
            List of validation violations
        """
        violations = []

        # Get graph structure
        node_ids = introspector.get_node_ids()

        # Check that target nodes exist
        for change in hypothesis.changes:
            if change.target_node_id and change.target_node_id not in node_ids:
                # For node additions, this is expected
                if change.type != "node_add":
                    violations.append(ValidationViolation(
                        rule="node_exists",
                        severity="error",
                        message=f"Target node '{change.target_node_id}' not found in graph",
                        details={"node_id": change.target_node_id}
                    ))

        # Check for cycles (if adding edges)
        # This is a simplified check - full cycle detection would require
        # simulating the graph with proposed changes
        edge_adds = [c for c in hypothesis.changes if c.type == "edge_add"]
        if edge_adds:
            existing_cycles = introspector.find_cycles()
            if existing_cycles:
                violations.append(ValidationViolation(
                    rule="no_new_cycles",
                    severity="warning",
                    message="Graph already has cycles; new edges may create more cycles",
                    details={"existing_cycles": len(existing_cycles)}
                ))

        return violations

    def _calculate_risk_level(self, risk_score: float) -> RiskLevel:
        """Calculate risk level from risk score.

        Args:
            risk_score: Calculated risk score

        Returns:
            RiskLevel
        """
        if risk_score < 0.3:
            return RiskLevel.LOW
        elif risk_score < 0.7:
            return RiskLevel.MEDIUM
        elif risk_score < 1.5:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL

    def _generate_recommendations(
        self,
        violations: List[ValidationViolation],
        risk_score: float
    ) -> List[str]:
        """Generate recommendations based on validation results.

        Args:
            violations: List of violations
            risk_score: Risk score

        Returns:
            List of recommendations
        """
        recommendations = []

        # Recommendations based on violations
        error_count = sum(1 for v in violations if v.severity == "error")
        warning_count = sum(1 for v in violations if v.severity == "warning")

        if error_count > 0:
            recommendations.append(f"Fix {error_count} error(s) before testing")

        if warning_count > 0:
            recommendations.append(f"Review {warning_count} warning(s)")

        # Recommendations based on risk level
        if risk_score < self.auto_approve_risk_threshold:
            recommendations.append("Low risk: Safe to test automatically")
        elif risk_score < 0.7:
            recommendations.append("Medium risk: Review recommended before testing")
        else:
            recommendations.append("High risk: Manual approval required")

        return recommendations
