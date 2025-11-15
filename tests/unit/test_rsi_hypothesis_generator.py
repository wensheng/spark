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

    prompt = generator._build_hypothesis_prompt(sample_report, None, [])

    # Verify prompt structure
    assert "Generate Graph Improvement Hypotheses" in prompt
    assert "Diagnostic Report" in prompt
    assert sample_report.graph_id in prompt
    assert str(sample_report.summary.success_rate) in prompt or "85" in prompt


@pytest.mark.asyncio
async def test_build_prompt_includes_bottlenecks(sample_report):
    """Test prompt includes bottleneck information."""
    generator = HypothesisGeneratorNode()

    prompt = generator._build_hypothesis_prompt(sample_report, None, [])

    # Verify bottleneck info
    assert "Identified Bottlenecks" in prompt
    assert "SlowProcessor" in prompt
    assert "high_latency" in prompt
    assert "ErrorProneNode" in prompt


@pytest.mark.asyncio
async def test_build_prompt_includes_failures(sample_report):
    """Test prompt includes failure patterns."""
    generator = HypothesisGeneratorNode()

    prompt = generator._build_hypothesis_prompt(sample_report, None, [])

    # Verify failure info
    assert "Failure Patterns" in prompt
    assert "ValidationError" in prompt


@pytest.mark.asyncio
async def test_build_prompt_includes_graph_structure(sample_report, introspector):
    """Test prompt includes graph structure when introspector provided."""
    generator = HypothesisGeneratorNode()

    prompt = generator._build_hypothesis_prompt(sample_report, introspector, [])

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

    prompt = generator._build_hypothesis_prompt(sample_report, None, [])

    assert "parameter_tuning" in prompt
    assert "caching" in prompt


@pytest.mark.asyncio
async def test_build_prompt_includes_instructions(sample_report):
    """Test prompt includes clear instructions."""
    generator = HypothesisGeneratorNode()

    prompt = generator._build_hypothesis_prompt(sample_report, None, [])

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


# ============================================================================
# Pattern-Based Learning Tests (Phase 5)
# ============================================================================

@pytest_asyncio.fixture
async def experience_db_with_patterns():
    """Create experience database with sample patterns."""
    from spark.rsi.experience_db import ExperienceDatabase

    db = ExperienceDatabase()
    await db.initialize()

    # Add successful prompt_optimization hypotheses
    for i in range(5):
        hyp_id = f"hyp_success_{i}"
        await db.store_hypothesis(
            hypothesis_id=hyp_id,
            graph_id="test_graph",
            graph_version_baseline="1.0.0",
            hypothesis_type="prompt_optimization",
            proposal={'test': 'data'},
            target_node="node_a"
        )
        await db.update_test_results(hyp_id, {
            'status': 'passed',
            'comparison': {
                'success_rate_delta': 0.05,
                'avg_duration_delta': -0.1,
                'is_improvement': True,
                'is_regression': False
            }
        })
        await db.update_deployment_outcome(
            hyp_id,
            deployed=True,
            outcome={'successful': True, 'rolled_back': False},
            lessons=['prompt_optimization works'],
            patterns=['prompt_optimization_success']
        )

    # Add failed parameter_tuning hypotheses
    for i in range(4):
        hyp_id = f"hyp_fail_{i}"
        await db.store_hypothesis(
            hypothesis_id=hyp_id,
            graph_id="test_graph",
            graph_version_baseline="1.0.0",
            hypothesis_type="parameter_tuning",
            proposal={'test': 'data'},
            target_node="node_b"
        )
        await db.update_test_results(hyp_id, {
            'status': 'failed',
            'comparison': {
                'success_rate_delta': -0.05,
                'avg_duration_delta': 0.2,
                'is_improvement': False,
                'is_regression': True
            }
        })
        await db.update_deployment_outcome(
            hyp_id,
            deployed=False,
            outcome={'successful': False},
            lessons=['parameter_tuning failed'],
            patterns=['parameter_tuning_failure']
        )

    return db


@pytest.mark.asyncio
async def test_init_with_experience_db(experience_db_with_patterns):
    """Test initialization with experience database."""
    generator = HypothesisGeneratorNode(
        experience_db=experience_db_with_patterns,
        enable_pattern_learning=True
    )

    assert generator.pattern_extractor is not None
    assert generator.enable_pattern_learning is True


@pytest.mark.asyncio
async def test_init_with_pattern_extractor(experience_db_with_patterns):
    """Test initialization with explicit pattern extractor."""
    from spark.rsi.pattern_extractor import PatternExtractor

    extractor = PatternExtractor(experience_db_with_patterns)
    generator = HypothesisGeneratorNode(
        pattern_extractor=extractor,
        enable_pattern_learning=True
    )

    assert generator.pattern_extractor is extractor
    assert generator.enable_pattern_learning is True


@pytest.mark.asyncio
async def test_pattern_extraction_during_generation(sample_report, experience_db_with_patterns):
    """Test that patterns are extracted during hypothesis generation."""
    generator = HypothesisGeneratorNode(
        experience_db=experience_db_with_patterns,
        enable_pattern_learning=True,
        max_hypotheses=2
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'diagnostic_report': sample_report})
    )

    result = await generator.process(context)

    # Should have extracted patterns
    assert 'patterns_used' in result
    assert len(result['patterns_used']) > 0

    # Should have generated hypotheses
    assert result['count'] > 0
    assert len(result['hypotheses']) > 0


@pytest.mark.asyncio
async def test_build_prompt_includes_patterns(sample_report, experience_db_with_patterns):
    """Test that learned patterns are included in the prompt."""
    from spark.rsi.pattern_extractor import PatternExtractor

    extractor = PatternExtractor(experience_db_with_patterns, min_evidence_count=3)
    patterns = await extractor.extract_patterns(graph_id="test_graph")

    generator = HypothesisGeneratorNode(
        pattern_extractor=extractor,
        enable_pattern_learning=True
    )

    prompt = generator._build_hypothesis_prompt(sample_report, None, patterns)

    # Should include patterns section
    assert "Learned Patterns from Experience" in prompt
    assert "Successful Patterns" in prompt or "High-Impact Improvements" in prompt
    assert "Priority Guidance" in prompt

    # Should include specific pattern types
    assert "prompt_optimization" in prompt.lower()


@pytest.mark.asyncio
async def test_mock_generation_prioritizes_by_patterns(sample_report, experience_db_with_patterns):
    """Test that mock generation prioritizes hypothesis types based on patterns."""
    generator = HypothesisGeneratorNode(
        experience_db=experience_db_with_patterns,
        enable_pattern_learning=True,
        max_hypotheses=2,
        hypothesis_types=["prompt_optimization", "parameter_tuning"]
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'diagnostic_report': sample_report})
    )

    result = await generator.process(context)

    # Should generate hypotheses
    assert result['count'] > 0

    # Should prefer prompt_optimization over parameter_tuning (based on patterns)
    hypothesis_types = [h.hypothesis_type.value for h in result['hypotheses']]
    prompt_opt_count = hypothesis_types.count('prompt_optimization')
    param_tune_count = hypothesis_types.count('parameter_tuning')

    # prompt_optimization should be preferred (or at least present)
    assert prompt_opt_count >= param_tune_count


@pytest.mark.asyncio
async def test_pattern_learning_disabled():
    """Test that pattern learning can be disabled."""
    from spark.rsi.experience_db import ExperienceDatabase

    db = ExperienceDatabase()
    await db.initialize()

    generator = HypothesisGeneratorNode(
        experience_db=db,
        enable_pattern_learning=False
    )

    assert generator.pattern_extractor is None
    assert generator.enable_pattern_learning is False


@pytest.mark.asyncio
async def test_generation_without_patterns(sample_report):
    """Test that generation works without patterns (backward compatible)."""
    generator = HypothesisGeneratorNode(
        max_hypotheses=2,
        hypothesis_types=["prompt_optimization"]
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'diagnostic_report': sample_report})
    )

    result = await generator.process(context)

    # Should still generate hypotheses
    assert result['count'] == 2
    assert len(result['hypotheses']) == 2

    # Should not have patterns_used
    assert 'patterns_used' not in result or len(result.get('patterns_used', [])) == 0


@pytest.mark.asyncio
async def test_pattern_extraction_error_handling(sample_report):
    """Test that pattern extraction errors are handled gracefully."""
    from spark.rsi.pattern_extractor import PatternExtractor
    from spark.rsi.experience_db import ExperienceDatabase

    # Create a pattern extractor with empty database
    db = ExperienceDatabase()
    await db.initialize()
    extractor = PatternExtractor(db, min_evidence_count=100)  # Very high threshold

    generator = HypothesisGeneratorNode(
        pattern_extractor=extractor,
        enable_pattern_learning=True,
        max_hypotheses=2
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'diagnostic_report': sample_report})
    )

    result = await generator.process(context)

    # Should still generate hypotheses even with no patterns
    assert result['count'] > 0
    assert len(result['hypotheses']) > 0
