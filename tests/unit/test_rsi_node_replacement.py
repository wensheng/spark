"""Tests for RSI node replacement analyzer."""

import pytest
from spark.rsi.node_replacement import NodeReplacementAnalyzer
from spark.rsi.types import (
    NodeMetrics,
    NodeReplacementCandidate,
    CompatibilityReport,
    ImpactEstimate,
    ExpectedImprovement,
)
from spark.nodes.spec import NodeSpec
from spark.rsi.introspection import GraphIntrospector


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def analyzer():
    """Create node replacement analyzer."""
    return NodeReplacementAnalyzer(min_compatibility_score=0.7)


@pytest.fixture
def mock_analyzer():
    """Create analyzer in mock mode."""
    return NodeReplacementAnalyzer(enable_mock_mode=True)


@pytest.fixture
def openai_node_spec():
    """Create OpenAI node spec."""
    return NodeSpec(
        id="llm_node_1",
        type="OpenAINode",
        description="LLM Processor",
        config={}
    )


@pytest.fixture
def bedrock_node_spec():
    """Create Bedrock node spec."""
    return NodeSpec(
        id="llm_node_1",
        type="BedrockNode",
        description="LLM Processor",
        config={}
    )


@pytest.fixture
def node_metrics_high_traffic():
    """Create node metrics for high-traffic node."""
    return NodeMetrics(
        node_id="llm_node_1",
        node_name="LLMProcessor",
        executions=5000,
        successes=4750,
        failures=250,
        success_rate=0.95,
        error_rate=0.05,
        avg_duration=1.2,
        p95_duration=2.0
    )


@pytest.fixture
def node_metrics_low_reliability():
    """Create node metrics for low-reliability node."""
    return NodeMetrics(
        node_id="llm_node_2",
        node_name="UnreliableProcessor",
        executions=1000,
        successes=850,
        failures=150,
        success_rate=0.85,
        error_rate=0.15,
        avg_duration=1.5,
        p95_duration=3.0
    )


@pytest.fixture
def graph_introspector():
    """Create mock graph introspector."""
    # For now, return None - we'll enhance this when needed
    return None


# ============================================================================
# Test NodeReplacementAnalyzer Initialization
# ============================================================================

def test_analyzer_initialization():
    """Test analyzer initialization."""
    analyzer = NodeReplacementAnalyzer(min_compatibility_score=0.8)
    assert analyzer.min_compatibility_score == 0.8
    assert not analyzer.enable_mock_mode
    assert len(analyzer._node_type_registry) > 0


def test_analyzer_mock_mode():
    """Test analyzer initialization in mock mode."""
    analyzer = NodeReplacementAnalyzer(enable_mock_mode=True)
    assert analyzer.enable_mock_mode


def test_node_registry_initialization(analyzer):
    """Test that node registry is initialized with known types."""
    registry = analyzer._node_type_registry

    # Check LLM nodes are registered
    assert "OpenAINode" in registry
    assert "BedrockNode" in registry
    assert "GeminiNode" in registry

    # Check OpenAI node info
    openai_info = registry["OpenAINode"]
    assert openai_info["category"] == "llm"
    assert "text_generation" in openai_info["capabilities"]
    assert "BedrockNode" in openai_info["equivalent_types"]


# ============================================================================
# Test Finding Replacement Candidates
# ============================================================================

@pytest.mark.asyncio
async def test_find_candidates_for_openai_node(
    mock_analyzer,
    openai_node_spec,
    graph_introspector,
    node_metrics_high_traffic
):
    """Test finding replacement candidates for OpenAI node."""
    candidates = await mock_analyzer.find_replacement_candidates(
        openai_node_spec,
        graph_introspector,
        node_metrics_high_traffic
    )

    assert len(candidates) > 0
    assert all(isinstance(c, NodeReplacementCandidate) for c in candidates)

    # Check candidate properties
    for candidate in candidates:
        assert candidate.replacement_node_type
        assert candidate.replacement_node_name
        assert 0.0 <= candidate.compatibility_score <= 1.0
        assert candidate.expected_improvement is not None


@pytest.mark.asyncio
async def test_find_candidates_unknown_node_type(
    analyzer,
    graph_introspector
):
    """Test finding candidates for unknown node type returns empty list."""
    unknown_spec = NodeSpec(
        id="unknown_1",
        type="UnknownNodeType",
        description="Unknown",
        config={}
    )

    candidates = await analyzer.find_replacement_candidates(
        unknown_spec,
        graph_introspector
    )

    assert len(candidates) == 0


@pytest.mark.asyncio
async def test_candidates_sorted_by_compatibility(
    mock_analyzer,
    openai_node_spec,
    graph_introspector
):
    """Test that candidates are sorted by compatibility score."""
    candidates = await mock_analyzer.find_replacement_candidates(
        openai_node_spec,
        graph_introspector
    )

    if len(candidates) > 1:
        scores = [c.compatibility_score for c in candidates]
        assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_candidates_filtered_by_min_score(analyzer, graph_introspector):
    """Test that candidates below min score are filtered."""
    # Use real analyzer with high threshold
    high_threshold_analyzer = NodeReplacementAnalyzer(
        min_compatibility_score=0.95
    )

    openai_spec = NodeSpec(
        id="llm_1",
        type="OpenAINode",
        description="LLM",
        config={}
    )

    candidates = await high_threshold_analyzer.find_replacement_candidates(
        openai_spec,
        graph_introspector
    )

    # With very high threshold, few or no candidates should pass
    for candidate in candidates:
        assert candidate.compatibility_score >= 0.95


# ============================================================================
# Test Compatibility Calculation
# ============================================================================

def test_calculate_compatibility_score_identical(analyzer):
    """Test compatibility score for identical node types."""
    node_info = {
        "category": "llm",
        "input_schema": {"text": "str"},
        "output_schema": {"result": "str"},
        "capabilities": ["generation"],
    }

    score = analyzer._calculate_compatibility_score(node_info, node_info)
    assert score == 1.0


def test_calculate_compatibility_score_different_category(analyzer):
    """Test compatibility score for different categories."""
    node_info1 = {
        "category": "llm",
        "input_schema": {"text": "str"},
        "output_schema": {"result": "str"},
        "capabilities": ["generation"],
    }

    node_info2 = {
        "category": "processing",
        "input_schema": {"text": "str"},
        "output_schema": {"result": "str"},
        "capabilities": ["generation"],
    }

    score = analyzer._calculate_compatibility_score(node_info1, node_info2)
    assert score < 1.0


def test_schema_compatibility_identical(analyzer):
    """Test schema compatibility for identical schemas."""
    schema = {"field1": "str", "field2": "int"}
    compatibility = analyzer._schema_compatibility(schema, schema)
    assert compatibility == 1.0


def test_schema_compatibility_partial_match(analyzer):
    """Test schema compatibility for partial match."""
    schema1 = {"field1": "str", "field2": "int"}
    schema2 = {"field1": "str"}  # Missing field2

    compatibility = analyzer._schema_compatibility(schema1, schema2)
    assert 0.0 < compatibility < 1.0


def test_schema_compatibility_no_match(analyzer):
    """Test schema compatibility for no match."""
    schema1 = {"field1": "str"}
    schema2 = {"field2": "int"}

    compatibility = analyzer._schema_compatibility(schema1, schema2)
    assert compatibility < 0.5


def test_schema_compatibility_empty_schemas(analyzer):
    """Test schema compatibility for empty schemas."""
    compatibility = analyzer._schema_compatibility({}, {})
    assert compatibility == 1.0


# ============================================================================
# Test Validation
# ============================================================================

@pytest.mark.asyncio
async def test_validate_compatibility_compatible_nodes(
    mock_analyzer,
    openai_node_spec,
    bedrock_node_spec
):
    """Test validation of compatible node replacement."""
    report = await mock_analyzer.validate_replacement_compatibility(
        openai_node_spec,
        bedrock_node_spec
    )

    assert isinstance(report, CompatibilityReport)
    assert report.is_compatible
    assert 0.0 <= report.compatibility_score <= 1.0
    assert report.input_compatibility
    assert report.output_compatibility


@pytest.mark.asyncio
async def test_validate_compatibility_has_recommendations(
    mock_analyzer,
    openai_node_spec,
    bedrock_node_spec
):
    """Test that compatibility validation provides recommendations."""
    report = await mock_analyzer.validate_replacement_compatibility(
        openai_node_spec,
        bedrock_node_spec
    )

    assert len(report.recommendations) > 0


# ============================================================================
# Test Impact Estimation
# ============================================================================

@pytest.mark.asyncio
async def test_estimate_impact(
    mock_analyzer,
    node_metrics_high_traffic
):
    """Test impact estimation for node replacement."""
    candidate = NodeReplacementCandidate(
        replacement_node_type="BedrockNode",
        replacement_node_name="Bedrock_LLM",
        compatibility_score=0.85,
        expected_improvement=ExpectedImprovement(
            latency_delta=-0.10,
            cost_delta=-0.05,
        )
    )

    historical_metrics = {
        "avg_duration": 1.5,
        "success_rate": 0.95,
        "cost_per_execution": 0.01,
        "execution_count": 5000,
    }

    impact = await mock_analyzer.estimate_replacement_impact(
        "node_1",
        candidate,
        historical_metrics
    )

    assert isinstance(impact, ImpactEstimate)
    assert -100.0 <= impact.latency_impact <= 100.0
    assert -100.0 <= impact.cost_impact <= 100.0
    assert -100.0 <= impact.reliability_impact <= 100.0
    assert 0.0 <= impact.confidence <= 1.0
    assert len(impact.assumptions) > 0


@pytest.mark.asyncio
async def test_estimate_impact_with_high_confidence(
    mock_analyzer,
    node_metrics_high_traffic
):
    """Test that high compatibility and data lead to high confidence."""
    candidate = NodeReplacementCandidate(
        replacement_node_type="BedrockNode",
        replacement_node_name="Bedrock_LLM",
        compatibility_score=0.95,  # High compatibility
        risk_factors=[]  # No risk factors
    )

    historical_metrics = {
        "avg_duration": 1.5,
        "success_rate": 0.95,
        "execution_count": 10000,  # Lots of data
    }

    impact = await mock_analyzer.estimate_replacement_impact(
        "node_1",
        candidate,
        historical_metrics
    )

    # High compatibility + lots of data + no risks = high confidence
    assert impact.confidence > 0.7


# ============================================================================
# Test Risk Identification
# ============================================================================

def test_identify_risk_factors_high_traffic_node(
    analyzer,
    openai_node_spec,
    node_metrics_high_traffic
):
    """Test risk identification for high-traffic node."""
    risks = analyzer._identify_risk_factors(
        openai_node_spec,
        "BedrockNode",
        node_metrics_high_traffic
    )

    assert len(risks) > 0

    # Should identify high traffic as a risk
    high_traffic_risk = any("traffic" in r.lower() for r in risks)
    assert high_traffic_risk


def test_identify_risk_factors_reliable_node(
    analyzer,
    openai_node_spec,
    node_metrics_high_traffic
):
    """Test risk identification for highly reliable node."""
    # Modify metrics to be highly reliable
    reliable_metrics = NodeMetrics(
        node_id="node_1",
        node_name="Node",
        executions=1000,
        successes=980,
        failures=20,
        success_rate=0.98,  # Very reliable
        error_rate=0.02,
        avg_duration=1.0,
        p95_duration=1.5
    )

    risks = analyzer._identify_risk_factors(
        openai_node_spec,
        "BedrockNode",
        reliable_metrics
    )

    # Should identify high reliability as a risk (don't want to break it)
    reliability_risk = any("reliable" in r.lower() for r in risks)
    assert reliability_risk


def test_identify_risk_factors_different_node_type(
    analyzer,
    openai_node_spec,
    node_metrics_high_traffic
):
    """Test risk identification when changing node type."""
    risks = analyzer._identify_risk_factors(
        openai_node_spec,
        "CompletelyDifferentNode",
        node_metrics_high_traffic
    )

    # Should identify node type change as a risk
    type_change_risk = any(
        "changing node type" in r.lower() or "type" in r.lower()
        for r in risks
    )
    assert type_change_risk


# ============================================================================
# Test Expected Improvement Estimation
# ============================================================================

def test_estimate_improvement_no_metrics(analyzer, openai_node_spec):
    """Test improvement estimation with no metrics returns default."""
    improvement = analyzer._estimate_improvement(
        openai_node_spec,
        "BedrockNode",
        None
    )

    assert isinstance(improvement, ExpectedImprovement)
    # With no metrics, should return defaults (zero improvements)
    assert improvement.success_rate_delta == 0.0
    assert improvement.latency_delta == 0.0


def test_estimate_improvement_with_high_error_rate(
    analyzer,
    openai_node_spec,
    node_metrics_low_reliability
):
    """Test improvement estimation for node with high error rate."""
    improvement = analyzer._estimate_improvement(
        openai_node_spec,
        "BedrockNode",
        node_metrics_low_reliability
    )

    # Should suggest success rate improvement
    assert improvement.success_rate_delta > 0.0


# ============================================================================
# Test Mock Mode
# ============================================================================

@pytest.mark.asyncio
async def test_mock_mode_generates_candidates(
    mock_analyzer,
    openai_node_spec,
    graph_introspector
):
    """Test that mock mode generates realistic candidates."""
    candidates = await mock_analyzer.find_replacement_candidates(
        openai_node_spec,
        graph_introspector
    )

    assert len(candidates) > 0

    for candidate in candidates:
        assert candidate.compatibility_score > 0.0
        assert len(candidate.compatibility_notes) > 0
        assert candidate.expected_improvement is not None


@pytest.mark.asyncio
async def test_mock_mode_compatibility_report(
    mock_analyzer,
    openai_node_spec,
    bedrock_node_spec
):
    """Test that mock mode generates compatibility report."""
    report = await mock_analyzer.validate_replacement_compatibility(
        openai_node_spec,
        bedrock_node_spec
    )

    assert report.is_compatible
    assert report.compatibility_score > 0.0
    assert len(report.warnings) > 0  # Should warn about mock mode


@pytest.mark.asyncio
async def test_mock_mode_impact_estimate(mock_analyzer):
    """Test that mock mode generates impact estimate."""
    candidate = NodeReplacementCandidate(
        replacement_node_type="BedrockNode",
        replacement_node_name="Bedrock_LLM",
        compatibility_score=0.85
    )

    impact = await mock_analyzer.estimate_replacement_impact(
        "node_1",
        candidate,
        {}
    )

    assert isinstance(impact, ImpactEstimate)
    assert impact.confidence > 0.0
    assert len(impact.assumptions) > 0
    # Should mention mock mode in assumptions
    assert any("mock" in a.lower() for a in impact.assumptions)
