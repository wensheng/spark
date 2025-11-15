"""
Recursive Self-Improvement (RSI) subsystem for Spark.

This package provides components for autonomous graph improvement:
- Performance analysis and bottleneck detection
- Hypothesis generation for improvements
- Change validation and automated testing
- Safe deployment with rollback

Phase 1 Components:
- PerformanceAnalyzerNode: Analyze telemetry and detect bottlenecks
- GraphIntrospector: Introspect and analyze graph structure
- ExperienceDatabase: Store learning data

Phase 2 Components:
- HypothesisGeneratorNode: Generate improvement hypotheses using LLM reasoning
- ChangeValidatorNode: Validate hypotheses for safety and correctness

Phase 3 Components:
- HypothesisTesterNode: Automated A/B testing of hypotheses with statistical analysis

Phase 4 Components:
- ChangeApplicator: Apply hypothesis changes to graph specifications
- DeploymentControllerNode: Safe deployment with monitoring and rollback

Phase 5 Components:
- PatternExtractor: Learn from historical improvement attempts
- RSIMetaGraph: Complete autonomous RSI workflow orchestration

Phase 6 Components:
- NodeReplacementAnalyzer: Identify node replacement opportunities
- EdgeOptimizer: Optimize graph edges (shortcuts, redundancy removal)
- ParallelizationAnalyzer: Convert sequential to parallel execution
- HumanReviewNode: Human-in-the-loop review for high-risk changes
- GraphDiffer: Visualize graph changes in multiple formats
- MultiObjectiveOptimizer: Balance latency, cost, quality, reliability trade-offs

Usage:
    from spark.rsi import (
        PerformanceAnalyzerNode,
        GraphIntrospector,
        HypothesisGeneratorNode,
        ChangeValidatorNode,
        HypothesisTesterNode,
        ChangeApplicator,
        DeploymentControllerNode,
        DeploymentConfig
    )
    from spark.telemetry import TelemetryConfig
    from spark.graphs import Graph
    from spark.models.openai import OpenAIModel

    # Phase 1: Analyze performance
    analyzer = PerformanceAnalyzerNode()
    result = await analyzer.run({'graph_id': 'my_graph'})
    report = result['report']

    # Phase 2: Generate and validate hypotheses
    model = OpenAIModel(model_id="gpt-4o")
    generator = HypothesisGeneratorNode(model=model)
    validator = ChangeValidatorNode(protected_nodes=["critical_node"])

    hyp_result = await generator.run({'diagnostic_report': report, 'graph': graph})
    for hypothesis in hyp_result['hypotheses']:
        val_result = await validator.run({'hypothesis': hypothesis})
        if val_result['approved']:
            # Phase 3: Test hypothesis
            tester = HypothesisTesterNode(num_baseline_runs=20, num_candidate_runs=20)
            test_result = await tester.run({'hypothesis': hypothesis, 'graph': graph})
            if test_result['passed']:
                # Phase 4: Deploy hypothesis
                controller = DeploymentControllerNode(
                    deployment_config=DeploymentConfig(strategy="direct")
                )
                deploy_result = await controller.run({
                    'hypothesis': hypothesis,
                    'test_result': test_result['test_result'],
                    'baseline_spec': graph_spec
                })
                if deploy_result['success']:
                    print(f"Hypothesis deployed: {hypothesis.rationale}")
"""

# Phase 1 exports
from spark.rsi.performance_analyzer import PerformanceAnalyzerNode
from spark.rsi.introspection import GraphIntrospector
from spark.rsi.experience_db import ExperienceDatabase

# Phase 2 exports
from spark.rsi.hypothesis_generator import HypothesisGeneratorNode
from spark.rsi.change_validator import ChangeValidatorNode

# Phase 3 exports
from spark.rsi.hypothesis_tester import HypothesisTesterNode

# Phase 4 exports
from spark.rsi.change_applicator import ChangeApplicator, ChangeApplicationError
from spark.rsi.deployment_controller import (
    DeploymentControllerNode,
    DeploymentConfig,
    DeploymentRecord
)

# Phase 5 exports
from spark.rsi.pattern_extractor import PatternExtractor, ExtractedPattern
from spark.rsi.rsi_meta_graph import (
    RSIMetaGraph,
    RSIMetaGraphConfig,
    AnalysisGateNode,
    ValidationGateNode,
    TestGateNode
)

# Phase 6 exports - Structural Analysis
from spark.rsi.node_replacement import NodeReplacementAnalyzer
from spark.rsi.edge_optimizer import EdgeOptimizer
from spark.rsi.parallelization_analyzer import ParallelizationAnalyzer

# Phase 6 exports - Safety and Optimization
from spark.rsi.human_review import (
    HumanReviewNode,
    HumanReviewConfig,
    ReviewRequestStore,
    ReviewRequest,
    ReviewDecision,
    FeedbackIntegrator
)
from spark.rsi.graph_differ import GraphDiffer
from spark.rsi.multi_objective_optimizer import (
    MultiObjectiveOptimizer,
    OptimizationObjectives,
    MultiObjectiveScore,
    RankedHypothesis,
    ParetoFrontier
)

__version__ = "0.6.0"  # Phase 6 complete

__all__ = [
    # Phase 1
    "PerformanceAnalyzerNode",
    "GraphIntrospector",
    "ExperienceDatabase",
    # Phase 2
    "HypothesisGeneratorNode",
    "ChangeValidatorNode",
    # Phase 3
    "HypothesisTesterNode",
    # Phase 4
    "ChangeApplicator",
    "ChangeApplicationError",
    "DeploymentControllerNode",
    "DeploymentConfig",
    "DeploymentRecord",
    # Phase 5
    "PatternExtractor",
    "ExtractedPattern",
    "RSIMetaGraph",
    "RSIMetaGraphConfig",
    "AnalysisGateNode",
    "ValidationGateNode",
    "TestGateNode",
    # Phase 6 - Structural Analysis
    "NodeReplacementAnalyzer",
    "EdgeOptimizer",
    "ParallelizationAnalyzer",
    # Phase 6 - Safety and Optimization
    "HumanReviewNode",
    "HumanReviewConfig",
    "ReviewRequestStore",
    "ReviewRequest",
    "ReviewDecision",
    "FeedbackIntegrator",
    "GraphDiffer",
    "MultiObjectiveOptimizer",
    "OptimizationObjectives",
    "MultiObjectiveScore",
    "RankedHypothesis",
    "ParetoFrontier",
]
