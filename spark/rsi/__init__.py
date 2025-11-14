"""
Recursive Self-Improvement (RSI) subsystem for Spark.

This package provides components for autonomous graph improvement:
- Performance analysis and bottleneck detection
- Hypothesis generation for improvements
- Change validation and automated testing
- Safe deployment with rollback (Phase 4+)

Phase 1 Components:
- PerformanceAnalyzerNode: Analyze telemetry and detect bottlenecks
- GraphIntrospector: Introspect and analyze graph structure
- ExperienceDatabase: Store learning data

Phase 2 Components:
- HypothesisGeneratorNode: Generate improvement hypotheses using LLM reasoning
- ChangeValidatorNode: Validate hypotheses for safety and correctness

Phase 3 Components (NEW):
- HypothesisTesterNode: Automated A/B testing of hypotheses with statistical analysis

Usage:
    from spark.rsi import (
        PerformanceAnalyzerNode,
        GraphIntrospector,
        HypothesisGeneratorNode,
        ChangeValidatorNode,
        HypothesisTesterNode
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
                print(f"Hypothesis passed testing: {hypothesis.rationale}")
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

__version__ = "0.3.0"  # Phase 3

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
]
