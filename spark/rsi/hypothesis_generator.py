"""Hypothesis generator for creating improvement proposals using LLM reasoning."""

from spark.nodes import Node
from spark.rsi.types import (
    DiagnosticReport,
    ImprovementHypothesis,
    HypothesisType,
    RiskLevel,
    ExpectedImprovement,
    ChangeSpec,
)
from spark.rsi.introspection import GraphIntrospector
from typing import List, Dict, Any, Optional
from uuid import uuid4
import logging
import json

logger = logging.getLogger(__name__)

# Check for model availability
try:
    from spark.models.base import Model
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False
    logger.warning("Models not available - HypothesisGeneratorNode requires model support")


class HypothesisGeneratorNode(Node):
    """Generates improvement hypotheses using LLM reasoning.

    This node analyzes diagnostic reports and uses an LLM to generate
    structured improvement proposals. Phase 2 focuses on prompt optimization.

    Usage:
        from spark.models.openai import OpenAIModel

        model = OpenAIModel(model_id="gpt-4o")
        generator = HypothesisGeneratorNode(
            model=model,
            max_hypotheses=3,
            hypothesis_types=["prompt_optimization"]
        )

        result = await generator.run({
            'diagnostic_report': report,
            'graph': graph
        })

        hypotheses = result['hypotheses']
    """

    def __init__(
        self,
        model: Optional[Any] = None,
        name: str = "HypothesisGenerator",
        max_hypotheses: int = 3,
        hypothesis_types: Optional[List[str]] = None,
        **kwargs
    ):
        """Initialize HypothesisGeneratorNode.

        Args:
            model: LLM model to use (OpenAIModel or BedrockModel)
            name: Node name
            max_hypotheses: Maximum number of hypotheses to generate
            hypothesis_types: Types of hypotheses to generate (default: prompt_optimization only)
            **kwargs: Additional node configuration
        """
        super().__init__(name=name, **kwargs)
        self.model = model
        self.max_hypotheses = max_hypotheses
        self.hypothesis_types = hypothesis_types or ["prompt_optimization"]

        if not MODELS_AVAILABLE:
            logger.warning(
                "Models system not available. Install model dependencies "
                "or HypothesisGeneratorNode will not function."
            )

        if self.model is None:
            logger.warning("No model provided. Hypotheses will be mock-generated.")

    async def process(self, context):
        """Generate improvement hypotheses from diagnostic report.

        Args:
            context: Execution context with inputs:
                - diagnostic_report: DiagnosticReport (required)
                - graph: Graph object (optional, for introspection)
                - introspector: GraphIntrospector (optional)

        Returns:
            Dict with:
                - hypotheses: List[ImprovementHypothesis]
                - count: int
                - generation_method: str (llm or mock)
        """
        # Get inputs
        report = context.inputs.content.get('diagnostic_report')
        if report is None:
            logger.error("diagnostic_report is required")
            return {
                'hypotheses': [],
                'count': 0,
                'error': 'diagnostic_report is required'
            }

        graph = context.inputs.content.get('graph')
        introspector = context.inputs.content.get('introspector')

        # Create introspector if graph provided
        if graph is not None and introspector is None:
            introspector = GraphIntrospector(graph)

        # Generate hypotheses
        if self.model is not None and MODELS_AVAILABLE:
            logger.info(f"Generating hypotheses using LLM: {self.model.__class__.__name__}")
            hypotheses = await self._generate_with_llm(report, introspector)
            generation_method = "llm"
        else:
            logger.info("Generating mock hypotheses (no model provided)")
            hypotheses = self._generate_mock_hypotheses(report, introspector)
            generation_method = "mock"

        logger.info(f"Generated {len(hypotheses)} hypotheses")

        return {
            'hypotheses': hypotheses,
            'count': len(hypotheses),
            'generation_method': generation_method
        }

    async def _generate_with_llm(
        self,
        report: DiagnosticReport,
        introspector: Optional[GraphIntrospector]
    ) -> List[ImprovementHypothesis]:
        """Generate hypotheses using LLM.

        Args:
            report: Diagnostic report
            introspector: Graph introspector (optional)

        Returns:
            List of improvement hypotheses
        """
        # Build prompt
        prompt = self._build_hypothesis_prompt(report, introspector)

        try:
            # Call LLM
            messages = [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ]

            response = await self.model.get_json(
                messages=messages,
                schema={
                    "type": "object",
                    "properties": {
                        "hypotheses": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "hypothesis_type": {"type": "string"},
                                    "target_node": {"type": "string"},
                                    "rationale": {"type": "string"},
                                    "expected_improvement": {
                                        "type": "object",
                                        "properties": {
                                            "success_rate_delta": {"type": "number"},
                                            "latency_delta": {"type": "number"},
                                            "cost_delta": {"type": "number"}
                                        }
                                    },
                                    "changes": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "type": {"type": "string"},
                                                "target_node_id": {"type": "string"},
                                                "config_path": {"type": "string"},
                                                "old_value": {"type": "string"},
                                                "new_value": {"type": "string"}
                                            }
                                        }
                                    },
                                    "risk_factors": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    }
                                },
                                "required": ["hypothesis_type", "rationale"]
                            }
                        }
                    },
                    "required": ["hypotheses"]
                }
            )

            # Parse response
            hypotheses = []
            for i, hyp_data in enumerate(response.get('hypotheses', [])[:self.max_hypotheses]):
                hypothesis = self._parse_llm_hypothesis(
                    hyp_data,
                    report.graph_id,
                    report.graph_version
                )
                if hypothesis:
                    hypotheses.append(hypothesis)

            return hypotheses

        except Exception as e:
            logger.error(f"Error generating hypotheses with LLM: {e}", exc_info=True)
            # Fallback to mock generation
            return self._generate_mock_hypotheses(report, introspector)

    def _build_hypothesis_prompt(
        self,
        report: DiagnosticReport,
        introspector: Optional[GraphIntrospector]
    ) -> str:
        """Build prompt for LLM hypothesis generation.

        Args:
            report: Diagnostic report
            introspector: Graph introspector (optional)

        Returns:
            Prompt string
        """
        prompt_parts = []

        prompt_parts.append("# Task: Generate Graph Improvement Hypotheses")
        prompt_parts.append("\nYou are an expert at analyzing software system performance and generating improvement proposals.")
        prompt_parts.append(f"\nAnalyze the following diagnostic report and generate up to {self.max_hypotheses} improvement hypotheses.")
        prompt_parts.append(f"\nFocus on: {', '.join(self.hypothesis_types)}")

        # Add diagnostic report
        prompt_parts.append("\n\n## Diagnostic Report")
        prompt_parts.append(f"\nGraph: {report.graph_id} (version {report.graph_version})")
        prompt_parts.append(f"\nTotal Executions: {report.summary.total_executions}")
        prompt_parts.append(f"\nSuccess Rate: {report.summary.success_rate:.1%}")
        prompt_parts.append(f"\nAvg Duration: {report.summary.avg_duration:.3f}s")
        prompt_parts.append(f"\nP95 Duration: {report.summary.p95_duration:.3f}s")

        # Add bottlenecks
        if report.bottlenecks:
            prompt_parts.append("\n\n### Identified Bottlenecks:")
            for b in report.bottlenecks[:5]:
                prompt_parts.append(f"\n- {b.node_name} ({b.issue})")
                prompt_parts.append(f"  Severity: {b.severity}")
                prompt_parts.append(f"  Impact Score: {b.impact_score:.2f}")
                if 'avg_duration' in b.metrics:
                    prompt_parts.append(f"  Avg Duration: {b.metrics['avg_duration']:.3f}s")
                if 'error_rate' in b.metrics:
                    prompt_parts.append(f"  Error Rate: {b.metrics['error_rate']:.1%}")

        # Add failure patterns
        if report.failures:
            prompt_parts.append("\n\n### Failure Patterns:")
            for f in report.failures[:3]:
                prompt_parts.append(f"\n- {f.node_name}: {f.error_type}")
                prompt_parts.append(f"  Occurrences: {f.count}")

        # Add graph structure info if available
        if introspector:
            stats = introspector.get_node_stats()
            prompt_parts.append("\n\n## Graph Structure")
            prompt_parts.append(f"\nTotal Nodes: {stats.get('total_nodes', 'N/A')}")
            prompt_parts.append(f"\nMax Depth: {stats.get('max_depth', 'N/A')}")
            prompt_parts.append(f"\nHas Cycles: {stats.get('has_cycles', False)}")

        # Add instructions
        prompt_parts.append("\n\n## Instructions")
        prompt_parts.append("\nFor each hypothesis, provide:")
        prompt_parts.append("\n1. hypothesis_type: Type of improvement (prompt_optimization, parameter_tuning, etc.)")
        prompt_parts.append("\n2. target_node: Name of the node to improve")
        prompt_parts.append("\n3. rationale: Clear explanation of why this improvement will help")
        prompt_parts.append("\n4. expected_improvement: Expected impact (success_rate_delta, latency_delta, cost_delta)")
        prompt_parts.append("\n5. changes: Specific changes to make")
        prompt_parts.append("\n6. risk_factors: Potential risks")

        prompt_parts.append("\n\nFor Phase 2, focus primarily on prompt optimization hypotheses.")
        prompt_parts.append("\nBe specific and actionable in your recommendations.")

        return "".join(prompt_parts)

    def _parse_llm_hypothesis(
        self,
        hyp_data: Dict[str, Any],
        graph_id: str,
        graph_version: str
    ) -> Optional[ImprovementHypothesis]:
        """Parse LLM response into ImprovementHypothesis.

        Args:
            hyp_data: Hypothesis data from LLM
            graph_id: Graph identifier
            graph_version: Graph version

        Returns:
            ImprovementHypothesis or None if parsing fails
        """
        try:
            # Parse hypothesis type
            hyp_type_str = hyp_data.get('hypothesis_type', 'prompt_optimization')
            try:
                hyp_type = HypothesisType(hyp_type_str)
            except ValueError:
                hyp_type = HypothesisType.PROMPT_OPTIMIZATION

            # Parse expected improvement
            exp_imp_data = hyp_data.get('expected_improvement', {})
            expected_improvement = ExpectedImprovement(
                success_rate_delta=exp_imp_data.get('success_rate_delta', 0.0),
                latency_delta=exp_imp_data.get('latency_delta', 0.0),
                cost_delta=exp_imp_data.get('cost_delta', 0.0)
            )

            # Parse changes
            changes = []
            for change_data in hyp_data.get('changes', []):
                change = ChangeSpec(
                    type=change_data.get('type', 'node_config_update'),
                    target_node_id=change_data.get('target_node_id'),
                    config_path=change_data.get('config_path'),
                    old_value=change_data.get('old_value'),
                    new_value=change_data.get('new_value')
                )
                changes.append(change)

            # Assess risk level
            risk_factors = hyp_data.get('risk_factors', [])
            risk_level = self._assess_risk_level(risk_factors, changes)

            # Create hypothesis
            hypothesis = ImprovementHypothesis(
                hypothesis_id=f"hyp_{uuid4().hex[:8]}",
                graph_id=graph_id,
                graph_version_baseline=graph_version,
                hypothesis_type=hyp_type,
                target_node=hyp_data.get('target_node'),
                rationale=hyp_data.get('rationale', ''),
                expected_improvement=expected_improvement,
                changes=changes,
                risk_level=risk_level,
                risk_factors=risk_factors
            )

            return hypothesis

        except Exception as e:
            logger.error(f"Error parsing LLM hypothesis: {e}")
            return None

    def _assess_risk_level(
        self,
        risk_factors: List[str],
        changes: List[ChangeSpec]
    ) -> RiskLevel:
        """Assess risk level based on factors and changes.

        Args:
            risk_factors: List of risk factors
            changes: List of proposed changes

        Returns:
            RiskLevel
        """
        risk_score = 0.0

        # Risk from number of changes
        risk_score += len(changes) * 0.1

        # Risk from number of risk factors
        risk_score += len(risk_factors) * 0.2

        # Classify risk level
        if risk_score < 0.3:
            return RiskLevel.LOW
        elif risk_score < 0.7:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.HIGH

    def _generate_mock_hypotheses(
        self,
        report: DiagnosticReport,
        introspector: Optional[GraphIntrospector]
    ) -> List[ImprovementHypothesis]:
        """Generate mock hypotheses for testing (no LLM required).

        Args:
            report: Diagnostic report
            introspector: Graph introspector (optional)

        Returns:
            List of improvement hypotheses
        """
        hypotheses = []

        # Generate hypothesis for each bottleneck (up to max_hypotheses)
        for i, bottleneck in enumerate(report.bottlenecks[:self.max_hypotheses]):
            # Determine hypothesis type based on bottleneck
            if bottleneck.issue == 'high_latency':
                hyp_type = HypothesisType.PROMPT_OPTIMIZATION
                rationale = f"Optimize {bottleneck.node_name} to reduce latency from {bottleneck.metrics.get('avg_duration', 0):.3f}s"
                expected_improvement = ExpectedImprovement(
                    latency_delta=-bottleneck.metrics.get('avg_duration', 0) * 0.5
                )
            elif bottleneck.issue == 'high_error_rate':
                hyp_type = HypothesisType.PROMPT_OPTIMIZATION
                rationale = f"Improve {bottleneck.node_name} prompt to reduce error rate from {bottleneck.metrics.get('error_rate', 0):.1%}"
                expected_improvement = ExpectedImprovement(
                    success_rate_delta=bottleneck.metrics.get('error_rate', 0) * 0.5
                )
            else:
                hyp_type = HypothesisType.PARAMETER_TUNING
                rationale = f"Tune parameters for {bottleneck.node_name}"
                expected_improvement = ExpectedImprovement()

            # Create change spec
            change = ChangeSpec(
                type="node_config_update",
                target_node_id=bottleneck.node_id,
                config_path="prompt_template",
                old_value="(current prompt)",
                new_value="(optimized prompt)"
            )

            # Create hypothesis
            hypothesis = ImprovementHypothesis(
                hypothesis_id=f"hyp_{uuid4().hex[:8]}",
                graph_id=report.graph_id,
                graph_version_baseline=report.graph_version,
                hypothesis_type=hyp_type,
                target_node=bottleneck.node_name,
                rationale=rationale,
                expected_improvement=expected_improvement,
                changes=[change],
                risk_level=RiskLevel.LOW,
                risk_factors=["mock_hypothesis"]
            )

            hypotheses.append(hypothesis)

        return hypotheses
