"""RSI Meta-Graph for autonomous graph improvement.

This module provides the RSIMetaGraph class that orchestrates the complete
Recursive Self-Improvement loop:
1. Analyze performance → Identify bottlenecks
2. Generate hypotheses → Create improvement proposals
3. Validate changes → Assess safety and risk
4. Test hypotheses → A/B comparison
5. Deploy → Safe rollout with monitoring
6. Learn → Extract patterns from outcomes

The RSIMetaGraph runs as a separate meta-system that can autonomously improve
production graphs based on telemetry data and learned patterns.
"""

from spark.graphs import Graph
from spark.nodes import Node
from spark.nodes.types import NodeMessage, ExecutionContext
from spark.rsi.performance_analyzer import PerformanceAnalyzerNode
from spark.rsi.hypothesis_generator import HypothesisGeneratorNode
from spark.rsi.change_validator import ChangeValidatorNode
from spark.rsi.hypothesis_tester import HypothesisTesterNode
from spark.rsi.deployment_controller import (
    DeploymentControllerNode,
    DeploymentConfig
)
from spark.rsi.experience_db import ExperienceDatabase
from spark.rsi.pattern_extractor import PatternExtractor
from spark.rsi.types import TestStatus
from spark.nodes.serde import graph_to_spec
from typing import Optional, Any, Dict, List
from dataclasses import dataclass, field
import logging
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class RSIMetaGraphConfig:
    """Configuration for RSI meta-graph.

    Attributes:
        graph_id: ID of the graph to improve
        graph_version: Current version of the graph
        analysis_window_hours: Hours of telemetry to analyze
        max_hypotheses: Maximum hypotheses to generate
        hypothesis_types: Types of hypotheses to consider
        enable_pattern_learning: Whether to use pattern-based learning
        deployment_strategy: Deployment strategy (direct, canary)
        auto_deploy: Whether to auto-deploy successful hypotheses
        enable_mock_mode: Use mock generation/testing for testing
    """
    graph_id: str
    graph_version: str = "1.0.0"
    analysis_window_hours: int = 24
    max_hypotheses: int = 3
    hypothesis_types: List[str] = field(default_factory=lambda: ["prompt_optimization"])
    enable_pattern_learning: bool = True
    deployment_strategy: str = "direct"
    auto_deploy: bool = True
    enable_mock_mode: bool = False


class AnalysisGateNode(Node):
    """Gate node that checks if analysis found issues worth addressing."""

    async def process(self, context):
        """Check if we should continue with hypothesis generation.

        Args:
            context: Execution context with analysis results

        Returns:
            Dict with continue flag and report
        """
        report = context.inputs.content.get('report')
        has_issues = context.inputs.content.get('has_issues', False)

        if not has_issues or not report:
            logger.info("No issues found in analysis - stopping RSI loop")
            return {
                'should_continue': False,
                'reason': 'No issues found'
            }

        logger.info(f"Found {len(report.bottlenecks)} bottlenecks - continuing to hypothesis generation")
        return {
            'should_continue': True,
            'report': report
        }


class ValidationGateNode(Node):
    """Gate node that filters validated hypotheses."""

    async def process(self, context):
        """Filter to only approved hypotheses.

        Args:
            context: Execution context with validation results

        Returns:
            Dict with approved hypotheses
        """
        hypotheses = context.inputs.content.get('hypotheses', [])
        validation_results = context.inputs.content.get('validation_results', [])

        # Filter approved hypotheses
        approved = []
        for hyp, result in zip(hypotheses, validation_results):
            if result.get('approved', False):
                approved.append(hyp)

        logger.info(f"Approved {len(approved)} of {len(hypotheses)} hypotheses for testing")

        if not approved:
            return {
                'should_continue': False,
                'reason': 'No hypotheses approved'
            }

        return {
            'should_continue': True,
            'approved_hypotheses': approved
        }


class TestGateNode(Node):
    """Gate node that filters hypotheses that passed testing."""

    async def process(self, context):
        """Filter to only hypotheses that passed testing.

        Args:
            context: Execution context with test results

        Returns:
            Dict with passed hypotheses and their test results
        """
        test_results = context.inputs.content.get('test_results', [])

        # Filter passed tests
        passed = []
        for result in test_results:
            test_result = result.get('test_result')
            hypothesis = result.get('hypothesis')

            if test_result and test_result.status == TestStatus.PASSED:
                passed.append({
                    'hypothesis': hypothesis,
                    'test_result': test_result
                })

        logger.info(f"{len(passed)} hypotheses passed testing")

        if not passed:
            return {
                'should_continue': False,
                'reason': 'No hypotheses passed testing'
            }

        return {
            'should_continue': True,
            'passed_tests': passed
        }


class RSIMetaGraph:
    """RSI Meta-Graph for autonomous graph improvement.

    This class creates and manages a complete RSI workflow graph that can
    autonomously improve a target graph based on telemetry data.

    Example:
        from spark.rsi import RSIMetaGraph, RSIMetaGraphConfig
        from spark.rsi import ExperienceDatabase
        from spark.telemetry import TelemetryManager

        # Create experience database
        experience_db = ExperienceDatabase()
        await experience_db.initialize()

        # Create RSI meta-graph
        config = RSIMetaGraphConfig(
            graph_id="my_graph",
            graph_version="1.0.0",
            max_hypotheses=3
        )

        rsi = RSIMetaGraph(
            config=config,
            experience_db=experience_db,
            model=model
        )

        # Run RSI loop
        result = await rsi.run(target_graph=my_graph)
    """

    def __init__(
        self,
        config: RSIMetaGraphConfig,
        experience_db: ExperienceDatabase,
        model: Optional[Any] = None,
        telemetry_manager: Optional[Any] = None
    ):
        """Initialize RSI meta-graph.

        Args:
            config: RSI configuration
            experience_db: Experience database for learning
            model: LLM model for hypothesis generation (optional, uses mock if None)
            telemetry_manager: Telemetry manager (optional, uses singleton if None)
        """
        self.config = config
        self.experience_db = experience_db
        self.model = model
        self.telemetry_manager = telemetry_manager

        # Create the RSI workflow graph
        self.graph = self._build_graph()

        logger.info(f"RSIMetaGraph created for graph_id={config.graph_id}")

    def _build_graph(self) -> Graph:
        """Build the RSI workflow graph.

        Returns:
            Complete RSI workflow graph
        """
        # Phase 1: Analyze performance
        analyzer = PerformanceAnalyzerNode(
            name="PerformanceAnalyzer",
            analysis_window_hours=self.config.analysis_window_hours,
            telemetry_manager=self.telemetry_manager
        )

        # Gate: Check if issues found
        analysis_gate = AnalysisGateNode(name="AnalysisGate")

        # Phase 2: Generate hypotheses
        generator = HypothesisGeneratorNode(
            name="HypothesisGenerator",
            model=self.model if not self.config.enable_mock_mode else None,
            max_hypotheses=self.config.max_hypotheses,
            hypothesis_types=self.config.hypothesis_types,
            experience_db=self.experience_db,
            enable_pattern_learning=self.config.enable_pattern_learning
        )

        # Phase 2: Validate hypotheses
        validator = ChangeValidatorNode(
            name="ChangeValidator",
            allowed_hypothesis_types=self.config.hypothesis_types
        )

        # Gate: Filter approved hypotheses
        validation_gate = ValidationGateNode(name="ValidationGate")

        # Phase 3: Test hypotheses
        tester = HypothesisTesterNode(
            name="HypothesisTester",
            enable_mock_mode=self.config.enable_mock_mode
        )

        # Gate: Filter passed tests
        test_gate = TestGateNode(name="TestGate")

        # Phase 4: Deploy hypotheses
        deployer = DeploymentControllerNode(
            name="DeploymentController",
            deployment_config=DeploymentConfig(
                strategy=self.config.deployment_strategy,
                monitoring_duration_seconds=10.0 if not self.config.enable_mock_mode else 0.5
            ),
            experience_db=self.experience_db,
            enable_monitoring=True,
            enable_rollback=True
        )

        # Connect the workflow
        # Step 1: Analyze → Gate
        analyzer >> analysis_gate

        # Step 2: Gate → Generate (if issues found)
        analysis_gate.on(should_continue=True) >> generator

        # Step 3: Generate → Validate
        generator >> validator

        # Step 4: Validate → Gate
        validator >> validation_gate

        # Step 5: Gate → Test (if approved)
        validation_gate.on(should_continue=True) >> tester

        # Step 6: Test → Gate
        tester >> test_gate

        # Step 7: Gate → Deploy (if passed and auto_deploy)
        if self.config.auto_deploy:
            test_gate.on(should_continue=True) >> deployer

        # Create graph
        return Graph(start=analyzer)

    async def run(
        self,
        target_graph: Optional[Graph] = None,
        target_graph_spec: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run the RSI loop to improve the target graph.

        Args:
            target_graph: Target graph to improve (optional)
            target_graph_spec: Target graph spec (optional, will be created from graph if not provided)

        Returns:
            Dict with:
                - success: Whether RSI loop completed successfully
                - phase: Last phase completed
                - report: Performance analysis report (if available)
                - hypotheses_generated: Number of hypotheses generated
                - hypotheses_approved: Number of hypotheses approved
                - hypotheses_passed: Number of hypotheses that passed testing
                - hypotheses_deployed: Number of hypotheses deployed
                - deployments: List of deployment results
                - error: Error message (if failed)
        """
        try:
            # Convert target_graph to spec if provided
            if target_graph is not None and target_graph_spec is None:
                target_graph_spec = graph_to_spec(target_graph, spark_version="2.0")

            # Prepare inputs
            inputs = NodeMessage(content={
                'graph_id': self.config.graph_id,
                'graph_version': self.config.graph_version,
                'target_graph': target_graph,
                'target_graph_spec': target_graph_spec
            })

            # Run the RSI workflow
            logger.info(f"Starting RSI loop for {self.config.graph_id}")
            result = await self.graph.run(inputs)

            # Extract results from final node
            result_content = result.content if hasattr(result, 'content') else result

            # Summarize results
            summary = {
                'success': True,
                'graph_id': self.config.graph_id,
                'graph_version': self.config.graph_version
            }

            # Add deployment info if available
            if 'deployments' in result_content:
                summary['deployments'] = result_content['deployments']
                summary['hypotheses_deployed'] = len(result_content['deployments'])

            logger.info(f"RSI loop completed successfully for {self.config.graph_id}")
            return summary

        except Exception as e:
            logger.error(f"RSI loop failed: {e}", exc_info=True)
            return {
                'success': False,
                'graph_id': self.config.graph_id,
                'error': str(e)
            }

    async def run_once(self, **kwargs) -> Dict[str, Any]:
        """Run the RSI loop once.

        Alias for run() for convenience.

        Args:
            **kwargs: Arguments passed to run()

        Returns:
            RSI loop results
        """
        return await self.run(**kwargs)

    async def run_continuous(
        self,
        interval_seconds: int = 3600,
        max_iterations: Optional[int] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Run the RSI loop continuously at regular intervals.

        Args:
            interval_seconds: Seconds between RSI loop executions (default: 1 hour)
            max_iterations: Maximum iterations (None for infinite)
            **kwargs: Arguments passed to run()

        Returns:
            List of RSI loop results
        """
        results = []
        iteration = 0

        logger.info(
            f"Starting continuous RSI loop (interval={interval_seconds}s, "
            f"max_iterations={max_iterations})"
        )

        while max_iterations is None or iteration < max_iterations:
            iteration += 1
            logger.info(f"RSI loop iteration {iteration}")

            # Run RSI loop
            result = await self.run(**kwargs)
            results.append(result)

            # Wait before next iteration (if not last)
            if max_iterations is None or iteration < max_iterations:
                await asyncio.sleep(interval_seconds)

        logger.info(f"Continuous RSI loop completed after {iteration} iterations")
        return results
