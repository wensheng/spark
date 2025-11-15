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
from spark.rsi.pattern_extractor import PatternExtractor, ExtractedPattern
from spark.rsi.experience_db import ExperienceDatabase
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
        pattern_extractor: Optional[PatternExtractor] = None,
        experience_db: Optional[ExperienceDatabase] = None,
        enable_pattern_learning: bool = True,
        # Phase 6: Structural analyzers
        node_replacement_analyzer: Optional[Any] = None,
        edge_optimizer: Optional[Any] = None,
        parallelization_analyzer: Optional[Any] = None,
        enable_structural_improvements: bool = True,
        **kwargs
    ):
        """Initialize HypothesisGeneratorNode.

        Args:
            model: LLM model to use (OpenAIModel or BedrockModel)
            name: Node name
            max_hypotheses: Maximum number of hypotheses to generate
            hypothesis_types: Types of hypotheses to generate (default: prompt_optimization only)
            pattern_extractor: PatternExtractor for learning from past attempts (optional)
            experience_db: ExperienceDatabase to create pattern extractor (optional)
            enable_pattern_learning: Whether to use pattern-based learning (default: True)
            node_replacement_analyzer: NodeReplacementAnalyzer for node replacement (Phase 6)
            edge_optimizer: EdgeOptimizer for edge optimizations (Phase 6)
            parallelization_analyzer: ParallelizationAnalyzer for parallelization (Phase 6)
            enable_structural_improvements: Whether to generate structural hypotheses (Phase 6)
            **kwargs: Additional node configuration
        """
        super().__init__(name=name, **kwargs)
        self.model = model
        self.max_hypotheses = max_hypotheses
        self.hypothesis_types = hypothesis_types or ["prompt_optimization"]
        self.enable_pattern_learning = enable_pattern_learning

        # Set up pattern extractor
        if pattern_extractor is not None:
            self.pattern_extractor = pattern_extractor
        elif experience_db is not None and enable_pattern_learning:
            # Create pattern extractor from experience database
            self.pattern_extractor = PatternExtractor(experience_db)
            logger.info("Created PatternExtractor from experience database")
        else:
            self.pattern_extractor = None
            if enable_pattern_learning:
                logger.info("Pattern learning disabled: no experience database provided")

        # Phase 6: Structural analyzers
        self.node_replacement_analyzer = node_replacement_analyzer
        self.edge_optimizer = edge_optimizer
        self.parallelization_analyzer = parallelization_analyzer
        self.enable_structural_improvements = enable_structural_improvements

        if enable_structural_improvements:
            analyzers_available = []
            if node_replacement_analyzer is not None:
                analyzers_available.append("node_replacement")
            if edge_optimizer is not None:
                analyzers_available.append("edge_optimization")
            if parallelization_analyzer is not None:
                analyzers_available.append("parallelization")

            if analyzers_available:
                logger.info(f"Structural analyzers available: {', '.join(analyzers_available)}")
            else:
                logger.info("Structural improvements enabled but no analyzers provided")

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
                - patterns_used: List[ExtractedPattern] (if pattern learning enabled)
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

        # Extract patterns from experience if enabled
        patterns = []
        if self.pattern_extractor is not None and self.enable_pattern_learning:
            logger.info("Extracting patterns from experience database")
            try:
                patterns = await self.pattern_extractor.extract_patterns(
                    graph_id=report.graph_id
                )
                logger.info(f"Extracted {len(patterns)} patterns from experience")
            except Exception as e:
                logger.warning(f"Error extracting patterns: {e}")
                patterns = []

        # Generate hypotheses
        if self.model is not None and MODELS_AVAILABLE:
            logger.info(f"Generating hypotheses using LLM: {self.model.__class__.__name__}")
            hypotheses = await self._generate_with_llm(report, introspector, patterns)
            generation_method = "llm"
        else:
            logger.info("Generating mock hypotheses (no model provided)")
            hypotheses = self._generate_mock_hypotheses(report, introspector, patterns)
            generation_method = "mock"

        logger.info(f"Generated {len(hypotheses)} hypotheses")

        result = {
            'hypotheses': hypotheses,
            'count': len(hypotheses),
            'generation_method': generation_method
        }

        if patterns:
            result['patterns_used'] = patterns

        return result

    async def _generate_with_llm(
        self,
        report: DiagnosticReport,
        introspector: Optional[GraphIntrospector],
        patterns: List[ExtractedPattern]
    ) -> List[ImprovementHypothesis]:
        """Generate hypotheses using LLM.

        Args:
            report: Diagnostic report
            introspector: Graph introspector (optional)
            patterns: Extracted patterns from experience (optional)

        Returns:
            List of improvement hypotheses
        """
        # Build prompt with patterns
        prompt = self._build_hypothesis_prompt(report, introspector, patterns)

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
            return self._generate_mock_hypotheses(report, introspector, patterns)

    def _build_hypothesis_prompt(
        self,
        report: DiagnosticReport,
        introspector: Optional[GraphIntrospector],
        patterns: List[ExtractedPattern]
    ) -> str:
        """Build prompt for LLM hypothesis generation.

        Args:
            report: Diagnostic report
            introspector: Graph introspector (optional)
            patterns: Extracted patterns from experience (optional)

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

        # Add learned patterns if available
        if patterns:
            prompt_parts.append("\n\n## Learned Patterns from Experience")
            prompt_parts.append("\nThe system has learned the following patterns from past improvement attempts:")
            prompt_parts.append("\nUse these patterns to guide your hypothesis generation.")

            # Group patterns by type
            success_patterns = [p for p in patterns if p.pattern_type == 'success']
            failure_patterns = [p for p in patterns if p.pattern_type == 'failure']
            improvement_patterns = [p for p in patterns if p.pattern_type == 'improvement']
            regression_patterns = [p for p in patterns if p.pattern_type == 'regression']

            if success_patterns:
                prompt_parts.append("\n\n### Successful Patterns (Repeat These):")
                for pattern in success_patterns[:3]:  # Top 3
                    prompt_parts.append(f"\n- {pattern.hypothesis_type}: {pattern.recommendation}")
                    prompt_parts.append(f"  Confidence: {pattern.confidence:.1%}, Evidence: {pattern.evidence_count} examples")
                    prompt_parts.append(f"  Success Rate: {pattern.success_rate:.1%}")

            if improvement_patterns:
                prompt_parts.append("\n\n### High-Impact Improvements (Prioritize These):")
                for pattern in improvement_patterns[:3]:  # Top 3
                    prompt_parts.append(f"\n- {pattern.hypothesis_type}: {pattern.recommendation}")
                    prompt_parts.append(f"  Confidence: {pattern.confidence:.1%}, Evidence: {pattern.evidence_count} examples")
                    if 'avg_success_delta' in pattern.context:
                        prompt_parts.append(f"  Avg Success Rate Improvement: {pattern.context['avg_success_delta']:+.1%}")

            if failure_patterns:
                prompt_parts.append("\n\n### Failure Patterns (Avoid These):")
                for pattern in failure_patterns[:3]:  # Top 3
                    prompt_parts.append(f"\n- {pattern.hypothesis_type}: {pattern.recommendation}")
                    prompt_parts.append(f"  Confidence: {pattern.confidence:.1%}, Evidence: {pattern.evidence_count} examples")
                    if 'common_reasons' in pattern.context:
                        reasons = pattern.context['common_reasons']
                        if reasons:
                            prompt_parts.append(f"  Common Reasons: {', '.join(str(r) for r in reasons[:3])}")

            if regression_patterns:
                prompt_parts.append("\n\n### Regression Patterns (Use Caution):")
                for pattern in regression_patterns[:3]:  # Top 3
                    prompt_parts.append(f"\n- {pattern.hypothesis_type}: {pattern.recommendation}")
                    prompt_parts.append(f"  Confidence: {pattern.confidence:.1%}, Evidence: {pattern.evidence_count} examples")
                    if 'common_reason' in pattern.context:
                        prompt_parts.append(f"  Common Rollback Reason: {pattern.context['common_reason']}")

            # Add priority guidance
            prompt_parts.append("\n\n### Priority Guidance:")
            prompt_parts.append("\nBased on learned patterns, prioritize hypothesis types in this order:")

            # Calculate priority scores for all types
            hypothesis_types_with_scores = []
            for hyp_type in self.hypothesis_types:
                score = self.pattern_extractor.get_priority_score(patterns, hyp_type)
                hypothesis_types_with_scores.append((hyp_type, score))

            # Sort by priority score (descending)
            hypothesis_types_with_scores.sort(key=lambda x: x[1], reverse=True)

            for i, (hyp_type, score) in enumerate(hypothesis_types_with_scores, 1):
                prompt_parts.append(f"\n{i}. {hyp_type} (priority score: {score:.2f})")

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
        introspector: Optional[GraphIntrospector],
        patterns: List[ExtractedPattern]
    ) -> List[ImprovementHypothesis]:
        """Generate mock hypotheses for testing (no LLM required).

        Args:
            report: Diagnostic report
            introspector: Graph introspector (optional)
            patterns: Extracted patterns from experience (optional)

        Returns:
            List of improvement hypotheses
        """
        hypotheses = []

        # If patterns available, prioritize hypothesis types based on learned patterns
        prioritized_types = self.hypothesis_types.copy()
        if patterns and self.pattern_extractor:
            # Calculate priority scores
            types_with_scores = []
            for hyp_type in self.hypothesis_types:
                score = self.pattern_extractor.get_priority_score(patterns, hyp_type)
                # Avoid types with very low scores
                if not self.pattern_extractor.should_avoid_hypothesis_type(patterns, hyp_type, threshold=0.7):
                    types_with_scores.append((hyp_type, score))

            # Sort by priority
            types_with_scores.sort(key=lambda x: x[1], reverse=True)
            prioritized_types = [t for t, _ in types_with_scores] if types_with_scores else self.hypothesis_types

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

    # ========================================================================
    # Phase 6: Structural Hypothesis Generation
    # ========================================================================

    async def _generate_node_replacement_hypotheses(
        self,
        report: DiagnosticReport,
        graph_introspector: GraphIntrospector
    ) -> List[ImprovementHypothesis]:
        """Generate node replacement hypotheses using NodeReplacementAnalyzer.

        Args:
            report: Diagnostic report with bottlenecks
            graph_introspector: Graph introspector for node analysis

        Returns:
            List of node replacement hypotheses
        """
        if self.node_replacement_analyzer is None:
            return []

        hypotheses = []

        # Analyze each bottleneck node
        for bottleneck in report.bottlenecks:
            node_id = bottleneck.node_id

            # Get node spec
            node_spec = graph_introspector.get_node_spec(node_id)
            if not node_spec:
                continue

            # Find replacement candidates
            try:
                candidates = await self.node_replacement_analyzer.find_replacement_candidates(
                    node_spec=node_spec,
                    graph_introspector=graph_introspector,
                    node_metrics=None  # Could pass bottleneck.metrics
                )

                # Generate hypothesis for best candidate
                if candidates:
                    best_candidate = candidates[0]  # Already sorted by compatibility

                    # Create change spec
                    change = ChangeSpec(
                        type='node_replacement',
                        target_node_id=node_id,
                        additional_params={
                            'replacement_node_spec': {
                                'id': f"{node_id}_replacement",
                                'type': best_candidate.replacement_node_type,
                                'config': {}
                            }
                        }
                    )

                    # Create hypothesis
                    hypothesis = ImprovementHypothesis(
                        hypothesis_id=f"hyp_{uuid4().hex[:8]}",
                        graph_id=report.graph_id,
                        graph_version_baseline=report.graph_version,
                        hypothesis_type=HypothesisType.NODE_REPLACEMENT,
                        target_node=node_id,
                        rationale=f"Replace {node_spec.type} with {best_candidate.replacement_node_type} "
                                 f"(compatibility: {best_candidate.compatibility_score:.2f}). "
                                 f"Notes: {', '.join(best_candidate.compatibility_notes[:2])}",
                        expected_improvement=best_candidate.expected_improvement or ExpectedImprovement(),
                        changes=[change],
                        risk_level=self._assess_replacement_risk(best_candidate),
                        risk_factors=best_candidate.risk_factors
                    )

                    hypotheses.append(hypothesis)

            except Exception as e:
                logger.warning(f"Error generating replacement hypothesis for {node_id}: {e}")

        return hypotheses

    async def _generate_edge_modification_hypotheses(
        self,
        report: DiagnosticReport,
        graph_introspector: GraphIntrospector,
        telemetry_data: Optional[List[Dict]] = None
    ) -> List[ImprovementHypothesis]:
        """Generate edge modification hypotheses using EdgeOptimizer.

        Args:
            report: Diagnostic report
            graph_introspector: Graph introspector
            telemetry_data: Telemetry data for edge analysis (optional)

        Returns:
            List of edge modification hypotheses
        """
        if self.edge_optimizer is None:
            return []

        hypotheses = []
        telemetry_data = telemetry_data or []

        try:
            # Find redundant edges
            redundant_edges = await self.edge_optimizer.find_redundant_edges(
                graph_introspector=graph_introspector,
                telemetry_data=telemetry_data
            )

            # Generate hypothesis for redundant edge removal
            if redundant_edges:
                edge_modifications = [
                    {'type': 'remove', 'edge_id': edge.from_node + '_to_' + edge.to_node}
                    for edge in redundant_edges[:3]  # Limit to top 3
                ]

                change = ChangeSpec(
                    type='edge_batch_modifications',
                    additional_params={'edge_modifications': edge_modifications}
                )

                hypothesis = ImprovementHypothesis(
                    hypothesis_id=f"hyp_{uuid4().hex[:8]}",
                    graph_id=report.graph_id,
                    graph_version_baseline=report.graph_version,
                    hypothesis_type=HypothesisType.EDGE_MODIFICATION,
                    target_node=None,
                    rationale=f"Remove {len(edge_modifications)} redundant edge(s) with low traversal rates",
                    expected_improvement=ExpectedImprovement(latency_delta=-0.1),
                    changes=[change],
                    risk_level=RiskLevel.LOW,
                    risk_factors=["edge_removal"]
                )

                hypotheses.append(hypothesis)

            # Find shortcut opportunities
            execution_patterns = {}  # Would come from telemetry
            shortcuts = await self.edge_optimizer.find_shortcut_opportunities(
                graph_introspector=graph_introspector,
                execution_patterns=execution_patterns
            )

            # Generate hypothesis for shortcut additions
            if shortcuts:
                edge_modifications = [
                    {
                        'type': 'add',
                        'edge_spec': {
                            'id': f"shortcut_{sc.from_node}_to_{sc.to_node}",
                            'from_node': sc.from_node,
                            'to_node': sc.to_node,
                            'condition': sc.condition_suggestion,
                            'description': 'Shortcut edge'
                        }
                    }
                    for sc in shortcuts[:2]  # Limit to top 2
                ]

                change = ChangeSpec(
                    type='edge_batch_modifications',
                    additional_params={'edge_modifications': edge_modifications}
                )

                total_savings = sum(sc.potential_latency_savings for sc in shortcuts[:2])

                hypothesis = ImprovementHypothesis(
                    hypothesis_id=f"hyp_{uuid4().hex[:8]}",
                    graph_id=report.graph_id,
                    graph_version_baseline=report.graph_version,
                    hypothesis_type=HypothesisType.EDGE_MODIFICATION,
                    target_node=None,
                    rationale=f"Add {len(edge_modifications)} shortcut edge(s) to reduce latency by ~{total_savings:.2f}s",
                    expected_improvement=ExpectedImprovement(latency_delta=-total_savings),
                    changes=[change],
                    risk_level=RiskLevel.MEDIUM,
                    risk_factors=["structural_change", "new_edge"]
                )

                hypotheses.append(hypothesis)

        except Exception as e:
            logger.warning(f"Error generating edge modification hypothesis: {e}")

        return hypotheses

    async def _generate_parallelization_hypotheses(
        self,
        report: DiagnosticReport,
        graph_introspector: GraphIntrospector
    ) -> List[ImprovementHypothesis]:
        """Generate parallelization hypotheses using ParallelizationAnalyzer.

        Args:
            report: Diagnostic report
            graph_introspector: Graph introspector

        Returns:
            List of parallelization hypotheses
        """
        if self.parallelization_analyzer is None:
            return []

        hypotheses = []

        try:
            # Find parallelizable sequences
            sequences = await self.parallelization_analyzer.find_parallelizable_sequences(
                graph_introspector=graph_introspector
            )

            # Generate hypothesis for top sequences
            for sequence in sequences[:2]:  # Limit to top 2
                # Generate parallel structure
                parallel_structure = await self.parallelization_analyzer.generate_parallel_structure(
                    sequence=sequence
                )

                # Create change spec
                change = ChangeSpec(
                    type='parallelization',
                    additional_params={
                        'parallel_structure': {
                            'parallel_branches': parallel_structure.parallel_branches,
                            'merge_node_id': parallel_structure.merge_node_id,
                            'requires_merge': parallel_structure.requires_merge,
                            'merge_strategy': parallel_structure.merge_strategy
                        },
                        'entry_node': sequence.entry_node
                    }
                )

                # Estimate benefit
                benefit = await self.parallelization_analyzer.estimate_parallelization_benefit(
                    sequence=sequence,
                    historical_latency={}
                )

                hypothesis = ImprovementHypothesis(
                    hypothesis_id=f"hyp_{uuid4().hex[:8]}",
                    graph_id=report.graph_id,
                    graph_version_baseline=report.graph_version,
                    hypothesis_type=HypothesisType.PARALLELIZATION,
                    target_node=sequence.entry_node,
                    rationale=f"Parallelize {len(sequence.sequential_nodes)} node(s) for {sequence.estimated_speedup:.1f}x speedup "
                             f"(confidence: {sequence.confidence:.0%})",
                    expected_improvement=ExpectedImprovement(
                        latency_delta=-benefit.latency_reduction
                    ),
                    changes=[change],
                    risk_level=self._assess_parallelization_risk(sequence, benefit),
                    risk_factors=["structural_change", "parallel_execution"]
                )

                hypotheses.append(hypothesis)

        except Exception as e:
            logger.warning(f"Error generating parallelization hypothesis: {e}")

        return hypotheses

    def _assess_replacement_risk(self, candidate) -> RiskLevel:
        """Assess risk level for node replacement."""
        if candidate.compatibility_score >= 0.9:
            return RiskLevel.LOW
        elif candidate.compatibility_score >= 0.7:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.HIGH

    def _assess_parallelization_risk(self, sequence, benefit) -> RiskLevel:
        """Assess risk level for parallelization."""
        if sequence.has_dependencies:
            return RiskLevel.HIGH

        if benefit.complexity_increase > 10:
            return RiskLevel.MEDIUM

        if sequence.confidence < 0.6:
            return RiskLevel.MEDIUM

        return RiskLevel.LOW
