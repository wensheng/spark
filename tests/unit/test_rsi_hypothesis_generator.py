"""Tests for HypothesisGeneratorNode."""

import pytest
import pytest_asyncio
from spark.rsi.hypothesis_generator import HypothesisGeneratorNode
from spark.rsi.types import (
    DiagnosticReport,
    PerformanceSummary,
    Bottleneck,
    FailurePattern,
    AnalysisPeriod,
    HypothesisType,
    RiskLevel,
)
from spark.rsi.introspection import GraphIntrospector
from spark.nodes.types import NodeMessage, ExecutionContext
from spark.nodes import Node
from spark.graphs import Graph


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def sample_report():
    """Create a sample diagnostic report for testing."""
    return DiagnosticReport(
        graph_id="test_graph",
        graph_version="1.0.0",
        analysis_period=AnalysisPeriod(
            start="2025-01-01T00:00:00",
            end="2025-01-01T01:00:00"
        ),
        summary=PerformanceSummary(
            total_executions=100,
            success_rate=0.85,
            avg_duration=0.5,
            p50_duration=0.4,
            p95_duration=0.8,
            p99_duration=1.0,
            total_cost=10.0
        ),
        bottlenecks=[
            Bottleneck(
                node_id="slow_node",
                node_name="SlowProcessor",
                issue="high_latency",
                severity="high",
                impact_score=0.8,
                metrics={"avg_duration": 0.8, "p95_duration": 1.2}
            ),
            Bottleneck(
                node_id="error_node",
                node_name="ErrorProneNode",
                issue="high_error_rate",
                severity="medium",
                impact_score=0.6,
                metrics={"error_rate": 0.15, "avg_duration": 0.2}
            )
        ],
        failures=[
            FailurePattern(
                node_id="error_node",
                node_name="ErrorProneNode",
                error_type="ValidationError",
                count=15,
                sample_messages=["Invalid input format", "Missing required field"]
            )
        ],
        opportunities=[
            "Optimize SlowProcessor prompt for faster responses",
            "Improve ErrorProneNode validation logic"
        ]
    )


@pytest_asyncio.fixture
async def simple_graph():
    """Create a simple graph for introspection testing."""
    class NodeA(Node):
        async def process(self, context):
            return {"result": "A"}

    class NodeB(Node):
        async def process(self, context):
            return {"result": "B"}

    node_a = NodeA(name="NodeA")
    node_b = NodeB(name="NodeB")
    node_a >> node_b

    return Graph(start=node_a)


@pytest_asyncio.fixture
async def introspector(simple_graph):
    """Create a graph introspector."""
    return GraphIntrospector(simple_graph)


# ============================================================================
# Initialization Tests
# ============================================================================

def test_init_without_model():
    """Test initialization without model (mock mode)."""
    generator = HypothesisGeneratorNode()

    assert generator.name == "HypothesisGenerator"
    assert generator.model is None
    assert generator.max_hypotheses == 3
    assert generator.hypothesis_types == ["prompt_optimization"]


def test_init_with_config():
    """Test initialization with custom configuration."""
    generator = HypothesisGeneratorNode(
        name="CustomGenerator",
        max_hypotheses=5,
        hypothesis_types=["prompt_optimization", "parameter_tuning"]
    )

    assert generator.name == "CustomGenerator"
    assert generator.max_hypotheses == 5
    assert generator.hypothesis_types == ["prompt_optimization", "parameter_tuning"]


# ============================================================================
# Mock Hypothesis Generation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_generate_mock_hypotheses_basic(sample_report):
    """Test basic mock hypothesis generation."""
    generator = HypothesisGeneratorNode(max_hypotheses=2)

    # Create context
    context = ExecutionContext(
        inputs=NodeMessage(content={
            'diagnostic_report': sample_report
        })
    )

    # Run node
    result = await generator.process(context)

    # Verify result structure
    assert 'hypotheses' in result
    assert 'count' in result
    assert 'generation_method' in result
    assert result['generation_method'] == 'mock'

    # Verify hypotheses
    hypotheses = result['hypotheses']
    assert len(hypotheses) == 2  # max_hypotheses=2
    assert len(hypotheses) <= len(sample_report.bottlenecks)


@pytest.mark.asyncio
async def test_mock_hypothesis_for_latency_bottleneck(sample_report):
    """Test mock hypothesis targets latency bottleneck."""
    generator = HypothesisGeneratorNode(max_hypotheses=1)

    context = ExecutionContext(
        inputs=NodeMessage(content={'diagnostic_report': sample_report})
    )

    result = await generator.process(context)

    hypothesis = result['hypotheses'][0]

    # Verify hypothesis targets first bottleneck (high_latency)
    assert hypothesis.hypothesis_type == HypothesisType.PROMPT_OPTIMIZATION
    assert "SlowProcessor" in hypothesis.rationale
    assert hypothesis.target_node == "SlowProcessor"
    assert hypothesis.expected_improvement.latency_delta < 0  # Negative = improvement
    assert len(hypothesis.changes) == 1
    assert hypothesis.changes[0].type == "node_config_update"
    assert hypothesis.changes[0].target_node_id == "slow_node"


@pytest.mark.asyncio
async def test_mock_hypothesis_for_error_bottleneck(sample_report):
    """Test mock hypothesis targets error rate bottleneck."""
    generator = HypothesisGeneratorNode(max_hypotheses=2)

    context = ExecutionContext(
        inputs=NodeMessage(content={'diagnostic_report': sample_report})
    )

    result = await generator.process(context)

    # Second hypothesis should target error rate
    hypothesis = result['hypotheses'][1]

    assert hypothesis.hypothesis_type == HypothesisType.PROMPT_OPTIMIZATION
    assert "ErrorProneNode" in hypothesis.rationale
    assert hypothesis.target_node == "ErrorProneNode"
    assert hypothesis.expected_improvement.success_rate_delta > 0  # Positive = improvement
    assert "error rate" in hypothesis.rationale.lower()


@pytest.mark.asyncio
async def test_mock_hypothesis_respects_max_hypotheses(sample_report):
    """Test that mock generation respects max_hypotheses limit."""
    generator = HypothesisGeneratorNode(max_hypotheses=1)

    context = ExecutionContext(
        inputs=NodeMessage(content={'diagnostic_report': sample_report})
    )

    result = await generator.process(context)

    assert result['count'] == 1
    assert len(result['hypotheses']) == 1


@pytest.mark.asyncio
async def test_mock_hypothesis_with_introspector(sample_report, introspector):
    """Test mock generation with graph introspector."""
    generator = HypothesisGeneratorNode(max_hypotheses=1)

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'diagnostic_report': sample_report,
            'introspector': introspector
        })
    )

    result = await generator.process(context)

    assert result['generation_method'] == 'mock'
    assert len(result['hypotheses']) == 1


@pytest.mark.asyncio
async def test_mock_hypothesis_with_graph(sample_report, simple_graph):
    """Test mock generation with graph (creates introspector automatically)."""
    generator = HypothesisGeneratorNode(max_hypotheses=1)

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'diagnostic_report': sample_report,
            'graph': simple_graph
        })
    )

    result = await generator.process(context)

    assert result['generation_method'] == 'mock'
    assert len(result['hypotheses']) == 1


# ============================================================================
# Prompt Building Tests
# ============================================================================

@pytest.mark.asyncio
async def test_build_prompt_basic(sample_report):
    """Test basic prompt building."""
    generator = HypothesisGeneratorNode()

    prompt = generator._build_hypothesis_prompt(sample_report, None)

    # Verify prompt structure
    assert "Generate Graph Improvement Hypotheses" in prompt
    assert "Diagnostic Report" in prompt
    assert sample_report.graph_id in prompt
    assert str(sample_report.summary.success_rate) in prompt or "85" in prompt


@pytest.mark.asyncio
async def test_build_prompt_includes_bottlenecks(sample_report):
    """Test prompt includes bottleneck information."""
    generator = HypothesisGeneratorNode()

    prompt = generator._build_hypothesis_prompt(sample_report, None)

    # Verify bottleneck info
    assert "Identified Bottlenecks" in prompt
    assert "SlowProcessor" in prompt
    assert "high_latency" in prompt
    assert "ErrorProneNode" in prompt


@pytest.mark.asyncio
async def test_build_prompt_includes_failures(sample_report):
    """Test prompt includes failure patterns."""
    generator = HypothesisGeneratorNode()

    prompt = generator._build_hypothesis_prompt(sample_report, None)

    # Verify failure info
    assert "Failure Patterns" in prompt
    assert "ValidationError" in prompt


@pytest.mark.asyncio
async def test_build_prompt_includes_graph_structure(sample_report, introspector):
    """Test prompt includes graph structure when introspector provided."""
    generator = HypothesisGeneratorNode()

    prompt = generator._build_hypothesis_prompt(sample_report, introspector)

    # Verify graph structure info
    assert "Graph Structure" in prompt
    assert "Total Nodes:" in prompt
    assert "Max Depth:" in prompt


@pytest.mark.asyncio
async def test_build_prompt_respects_hypothesis_types(sample_report):
    """Test prompt respects configured hypothesis types."""
    generator = HypothesisGeneratorNode(
        hypothesis_types=["parameter_tuning", "caching"]
    )

    prompt = generator._build_hypothesis_prompt(sample_report, None)

    assert "parameter_tuning" in prompt
    assert "caching" in prompt


@pytest.mark.asyncio
async def test_build_prompt_includes_instructions(sample_report):
    """Test prompt includes clear instructions."""
    generator = HypothesisGeneratorNode()

    prompt = generator._build_hypothesis_prompt(sample_report, None)

    # Verify instructions
    assert "Instructions" in prompt
    assert "hypothesis_type" in prompt
    assert "rationale" in prompt
    assert "expected_improvement" in prompt
    assert "Phase 2" in prompt


# ============================================================================
# Hypothesis Parsing Tests
# ============================================================================

def test_parse_llm_hypothesis_basic():
    """Test parsing basic LLM hypothesis."""
    generator = HypothesisGeneratorNode()

    hyp_data = {
        "hypothesis_type": "prompt_optimization",
        "target_node": "TestNode",
        "rationale": "Improve prompt clarity",
        "expected_improvement": {
            "success_rate_delta": 0.1,
            "latency_delta": -0.2
        },
        "changes": [
            {
                "type": "node_config_update",
                "target_node_id": "test_node",
                "config_path": "prompt_template",
                "old_value": "old prompt",
                "new_value": "new prompt"
            }
        ],
        "risk_factors": ["prompt_change"]
    }

    hypothesis = generator._parse_llm_hypothesis(hyp_data, "graph_1", "1.0.0")

    assert hypothesis is not None
    assert hypothesis.hypothesis_type == HypothesisType.PROMPT_OPTIMIZATION
    assert hypothesis.target_node == "TestNode"
    assert hypothesis.rationale == "Improve prompt clarity"
    assert hypothesis.expected_improvement.success_rate_delta == 0.1
    assert hypothesis.expected_improvement.latency_delta == -0.2
    assert len(hypothesis.changes) == 1
    assert hypothesis.changes[0].type == "node_config_update"
    assert len(hypothesis.risk_factors) == 1


def test_parse_llm_hypothesis_with_defaults():
    """Test parsing hypothesis with missing fields (uses defaults)."""
    generator = HypothesisGeneratorNode()

    hyp_data = {
        "rationale": "Simple improvement"
    }

    hypothesis = generator._parse_llm_hypothesis(hyp_data, "graph_1", "1.0.0")

    assert hypothesis is not None
    assert hypothesis.hypothesis_type == HypothesisType.PROMPT_OPTIMIZATION  # Default
    assert hypothesis.rationale == "Simple improvement"
    assert hypothesis.expected_improvement.success_rate_delta == 0.0
    assert len(hypothesis.changes) == 0


def test_parse_llm_hypothesis_invalid_type():
    """Test parsing hypothesis with invalid type (falls back to default)."""
    generator = HypothesisGeneratorNode()

    hyp_data = {
        "hypothesis_type": "invalid_type",
        "rationale": "Test"
    }

    hypothesis = generator._parse_llm_hypothesis(hyp_data, "graph_1", "1.0.0")

    assert hypothesis is not None
    assert hypothesis.hypothesis_type == HypothesisType.PROMPT_OPTIMIZATION  # Fallback


# ============================================================================
# Risk Assessment Tests
# ============================================================================

def test_assess_risk_level_low():
    """Test risk assessment for low-risk changes."""
    generator = HypothesisGeneratorNode()

    risk_factors = []
    changes = [{"type": "node_config_update"}]

    risk_level = generator._assess_risk_level(risk_factors, changes)

    assert risk_level == RiskLevel.LOW


def test_assess_risk_level_medium():
    """Test risk assessment for medium-risk changes."""
    generator = HypothesisGeneratorNode()

    risk_factors = ["prompt_change"]
    changes = [{"type": "node_config_update"}] * 2

    risk_level = generator._assess_risk_level(risk_factors, changes)

    assert risk_level == RiskLevel.MEDIUM


def test_assess_risk_level_high():
    """Test risk assessment for high-risk changes."""
    generator = HypothesisGeneratorNode()

    risk_factors = ["structural_change", "data_loss_possible"]
    changes = [{"type": "node_remove"}] * 3

    risk_level = generator._assess_risk_level(risk_factors, changes)

    assert risk_level == RiskLevel.HIGH


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_missing_diagnostic_report():
    """Test error handling when diagnostic report is missing."""
    generator = HypothesisGeneratorNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={})  # Missing report
    )

    result = await generator.process(context)

    assert 'error' in result
    assert result['count'] == 0
    assert len(result['hypotheses']) == 0


@pytest.mark.asyncio
async def test_empty_bottlenecks_list(sample_report):
    """Test handling of report with no bottlenecks."""
    # Create report with no bottlenecks
    report = DiagnosticReport(
        graph_id="test_graph",
        graph_version="1.0.0",
        summary=sample_report.summary,
        bottlenecks=[],  # Empty
        failures=[]
    )

    generator = HypothesisGeneratorNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={'diagnostic_report': report})
    )

    result = await generator.process(context)

    # Should return empty hypotheses
    assert result['count'] == 0
    assert len(result['hypotheses']) == 0


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_full_workflow_mock_generation(sample_report):
    """Test complete workflow with mock generation."""
    generator = HypothesisGeneratorNode(
        max_hypotheses=2,
        hypothesis_types=["prompt_optimization"]
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'diagnostic_report': sample_report})
    )

    result = await generator.process(context)

    # Verify complete result
    assert result['generation_method'] == 'mock'
    assert result['count'] == 2
    assert len(result['hypotheses']) == 2

    # Verify each hypothesis is well-formed
    for hyp in result['hypotheses']:
        assert hyp.hypothesis_id.startswith('hyp_')
        assert hyp.graph_id == sample_report.graph_id
        assert hyp.graph_version_baseline == sample_report.graph_version
        assert hyp.rationale != ""
        assert hyp.expected_improvement is not None
        assert len(hyp.changes) > 0
        assert hyp.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]
