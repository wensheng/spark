"""Tests for ChangeValidatorNode."""

import pytest
import pytest_asyncio
from spark.rsi.change_validator import ChangeValidatorNode
from spark.rsi.types import (
    ImprovementHypothesis,
    HypothesisType,
    RiskLevel,
    ExpectedImprovement,
    ChangeSpec,
)
from spark.rsi.introspection import GraphIntrospector
from spark.nodes.types import NodeMessage, ExecutionContext
from spark.nodes import Node
from spark.graphs import Graph


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def basic_hypothesis():
    """Create a basic valid hypothesis for testing."""
    return ImprovementHypothesis(
        hypothesis_id="hyp_test_001",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        target_node="TestNode",
        rationale="Improve prompt clarity to reduce errors",
        expected_improvement=ExpectedImprovement(
            success_rate_delta=0.1,
            latency_delta=-0.2
        ),
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="test_node",
                config_path="prompt_template",
                old_value="old prompt",
                new_value="new prompt"
            )
        ],
        risk_level=RiskLevel.LOW,
        risk_factors=["prompt_change"]
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

def test_init_default():
    """Test initialization with default configuration."""
    validator = ChangeValidatorNode()

    assert validator.name == "ChangeValidator"
    assert validator.max_nodes_added == 5
    assert validator.max_nodes_removed == 2
    assert validator.max_prompt_length == 10000
    assert validator.protected_nodes == []
    assert validator.allowed_hypothesis_types == ["prompt_optimization", "parameter_tuning"]
    assert validator.auto_approve_risk_threshold == 0.3


def test_init_custom():
    """Test initialization with custom configuration."""
    validator = ChangeValidatorNode(
        name="CustomValidator",
        max_nodes_added=10,
        max_nodes_removed=5,
        max_prompt_length=5000,
        protected_nodes=["critical_node"],
        allowed_hypothesis_types=["prompt_optimization"],
        auto_approve_risk_threshold=0.2
    )

    assert validator.name == "CustomValidator"
    assert validator.max_nodes_added == 10
    assert validator.max_nodes_removed == 5
    assert validator.max_prompt_length == 5000
    assert validator.protected_nodes == ["critical_node"]
    assert validator.allowed_hypothesis_types == ["prompt_optimization"]
    assert validator.auto_approve_risk_threshold == 0.2


# ============================================================================
# Basic Validation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_validate_valid_hypothesis(basic_hypothesis):
    """Test validation of a valid hypothesis."""
    validator = ChangeValidatorNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': basic_hypothesis})
    )

    result = await validator.process(context)

    # Should be approved
    assert result['approved'] is True
    assert result['validation'].approved is True
    assert result['risk_level'] == 'low'
    assert result['risk_score'] < 0.3


@pytest.mark.asyncio
async def test_validate_missing_hypothesis():
    """Test error handling when hypothesis is missing."""
    validator = ChangeValidatorNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={})  # Missing hypothesis
    )

    result = await validator.process(context)

    assert result['approved'] is False
    assert 'error' in result
    assert result['validation'] is None


# ============================================================================
# Hypothesis Type Validation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_reject_disallowed_hypothesis_type(basic_hypothesis):
    """Test rejection of disallowed hypothesis type."""
    # Change to disallowed type
    basic_hypothesis.hypothesis_type = HypothesisType.NODE_REPLACEMENT

    validator = ChangeValidatorNode(
        allowed_hypothesis_types=["prompt_optimization"]
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': basic_hypothesis})
    )

    result = await validator.process(context)

    # Should be rejected
    assert result['approved'] is False
    assert len(result['validation'].violations) > 0

    # Find the violation
    violations = result['validation'].violations
    type_violation = next((v for v in violations if v.rule == "allowed_hypothesis_types"), None)
    assert type_violation is not None
    assert type_violation.severity == "error"


@pytest.mark.asyncio
async def test_allow_multiple_hypothesis_types(basic_hypothesis):
    """Test allowing multiple hypothesis types."""
    basic_hypothesis.hypothesis_type = HypothesisType.PARAMETER_TUNING

    validator = ChangeValidatorNode(
        allowed_hypothesis_types=["prompt_optimization", "parameter_tuning"]
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': basic_hypothesis})
    )

    result = await validator.process(context)

    # Should be approved
    assert result['approved'] is True


# ============================================================================
# Protected Nodes Tests
# ============================================================================

@pytest.mark.asyncio
async def test_reject_protected_node_modification():
    """Test rejection of hypothesis targeting protected node."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_002",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        target_node="authentication",  # Protected
        rationale="Test",
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="auth_node"
            )
        ]
    )

    validator = ChangeValidatorNode(
        protected_nodes=["authentication", "payment"]
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    # Should be rejected
    assert result['approved'] is False

    violations = result['validation'].violations
    protected_violation = next((v for v in violations if v.rule == "protected_nodes"), None)
    assert protected_violation is not None
    assert protected_violation.severity == "error"


@pytest.mark.asyncio
async def test_reject_protected_node_removal():
    """Test rejection of hypothesis removing protected node."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_003",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        target_node="test_node",
        rationale="Test",
        changes=[
            ChangeSpec(
                type="node_remove",
                target_node_id="critical_node"  # Protected
            )
        ]
    )

    validator = ChangeValidatorNode(
        protected_nodes=["critical_node"]
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    # Should be rejected
    assert result['approved'] is False


# ============================================================================
# Node Addition/Removal Limits Tests
# ============================================================================

@pytest.mark.asyncio
async def test_reject_too_many_nodes_added():
    """Test rejection when too many nodes are added."""
    changes = [
        ChangeSpec(type="node_add", target_node_id=f"new_node_{i}")
        for i in range(6)  # 6 nodes, max is 5
    ]

    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_004",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        rationale="Test",
        changes=changes
    )

    validator = ChangeValidatorNode(max_nodes_added=5)

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    # Should be rejected
    assert result['approved'] is False

    violations = result['validation'].violations
    limit_violation = next((v for v in violations if v.rule == "max_nodes_added"), None)
    assert limit_violation is not None
    assert limit_violation.severity == "error"


@pytest.mark.asyncio
async def test_reject_too_many_nodes_removed():
    """Test rejection when too many nodes are removed."""
    changes = [
        ChangeSpec(type="node_remove", target_node_id=f"old_node_{i}")
        for i in range(3)  # 3 nodes, max is 2
    ]

    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_005",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        rationale="Test",
        changes=changes
    )

    validator = ChangeValidatorNode(max_nodes_removed=2)

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    # Should be rejected
    assert result['approved'] is False

    violations = result['validation'].violations
    limit_violation = next((v for v in violations if v.rule == "max_nodes_removed"), None)
    assert limit_violation is not None


@pytest.mark.asyncio
async def test_accept_within_node_limits():
    """Test acceptance when node changes are within limits."""
    changes = [
        ChangeSpec(type="node_add", target_node_id="new_node_1"),
        ChangeSpec(type="node_add", target_node_id="new_node_2"),
        ChangeSpec(type="node_remove", target_node_id="old_node_1")
    ]

    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_006",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        rationale="Test",
        changes=changes
    )

    validator = ChangeValidatorNode(
        max_nodes_added=5,
        max_nodes_removed=2
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    # Should be approved (no limit violations)
    # May have other violations, but not for node limits
    violations = result['validation'].violations
    limit_violations = [v for v in violations if v.rule in ["max_nodes_added", "max_nodes_removed"]]
    assert len(limit_violations) == 0


# ============================================================================
# Prompt Length Validation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_warn_excessive_prompt_length():
    """Test warning for excessively long prompts."""
    long_prompt = "x" * 15000  # 15k chars, max is 10k

    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_007",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        rationale="Test",
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="test_node",
                config_path="prompt_template",
                new_value=long_prompt
            )
        ]
    )

    validator = ChangeValidatorNode(max_prompt_length=10000)

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    # Should have warning (not error)
    violations = result['validation'].violations
    prompt_violation = next((v for v in violations if v.rule == "max_prompt_length"), None)
    assert prompt_violation is not None
    assert prompt_violation.severity == "warning"


@pytest.mark.asyncio
async def test_accept_reasonable_prompt_length():
    """Test acceptance of reasonable prompt length."""
    reasonable_prompt = "x" * 5000  # 5k chars, well under 10k limit

    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_008",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        rationale="Test",
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="test_node",
                config_path="prompt_template",
                new_value=reasonable_prompt
            )
        ]
    )

    validator = ChangeValidatorNode(max_prompt_length=10000)

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    # Should have no prompt length violations
    violations = result['validation'].violations
    prompt_violations = [v for v in violations if v.rule == "max_prompt_length"]
    assert len(prompt_violations) == 0


# ============================================================================
# Structural Integrity Tests
# ============================================================================

@pytest.mark.asyncio
async def test_structural_validation_with_introspector(introspector):
    """Test structural validation with graph introspector."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_009",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        rationale="Test",
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="nonexistent_node"  # Doesn't exist
            )
        ]
    )

    validator = ChangeValidatorNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': hypothesis,
            'introspector': introspector
        })
    )

    result = await validator.process(context)

    # Should have structural integrity violation
    violations = result['validation'].violations
    struct_violation = next((v for v in violations if v.rule == "node_exists"), None)
    assert struct_violation is not None


@pytest.mark.asyncio
async def test_accept_node_add_for_new_node(introspector):
    """Test that node_add changes for new nodes are accepted."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_010",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        rationale="Test",
        changes=[
            ChangeSpec(
                type="node_add",  # Adding new node
                target_node_id="brand_new_node"  # Doesn't exist yet - OK
            )
        ]
    )

    validator = ChangeValidatorNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': hypothesis,
            'introspector': introspector
        })
    )

    result = await validator.process(context)

    # Should NOT have node_exists violation for node_add
    violations = result['validation'].violations
    struct_violations = [v for v in violations if v.rule == "node_exists"]
    assert len(struct_violations) == 0


# ============================================================================
# Required Fields Tests
# ============================================================================

@pytest.mark.asyncio
async def test_warn_missing_rationale():
    """Test warning when rationale is missing."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_011",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        rationale="",  # Empty
        changes=[
            ChangeSpec(type="node_config_update", target_node_id="test_node")
        ]
    )

    validator = ChangeValidatorNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    # Should have warning
    violations = result['validation'].violations
    rationale_violation = next((v for v in violations if v.rule == "required_fields" and "rationale" in v.message.lower()), None)
    assert rationale_violation is not None
    assert rationale_violation.severity == "warning"


@pytest.mark.asyncio
async def test_reject_no_changes():
    """Test rejection when no changes are specified."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_012",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        rationale="Test",
        changes=[]  # No changes
    )

    validator = ChangeValidatorNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    # Should be rejected
    assert result['approved'] is False

    violations = result['validation'].violations
    changes_violation = next((v for v in violations if v.rule == "required_fields" and "changes" in v.message.lower()), None)
    assert changes_violation is not None
    assert changes_violation.severity == "error"


# ============================================================================
# Risk Scoring Tests
# ============================================================================

@pytest.mark.asyncio
async def test_risk_score_calculation_low():
    """Test risk score calculation for low-risk hypothesis."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_013",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        rationale="Simple change",
        changes=[
            ChangeSpec(type="node_config_update", target_node_id="test_node")
        ],
        risk_factors=[]  # No risk factors
    )

    validator = ChangeValidatorNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    assert result['risk_level'] == 'low'
    assert result['risk_score'] < 0.3


@pytest.mark.asyncio
async def test_risk_score_calculation_medium():
    """Test risk score calculation for medium-risk hypothesis."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_014",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        rationale="Moderate change",
        changes=[
            ChangeSpec(type="node_config_update", target_node_id="test_node")
        ] * 3,  # Multiple changes
        risk_factors=["prompt_change", "affects_multiple_paths", "data_dependency", "performance_critical"]  # More risk factors
    )

    validator = ChangeValidatorNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    assert result['risk_level'] == 'medium'
    assert 0.3 <= result['risk_score'] < 0.7


@pytest.mark.asyncio
async def test_risk_score_calculation_high():
    """Test risk score calculation for high-risk hypothesis."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_015",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        rationale="Complex change",
        changes=[
            ChangeSpec(type="node_remove", target_node_id=f"node_{i}")
            for i in range(5)
        ],
        risk_factors=["structural_change", "data_loss", "breaking_change"]
    )

    validator = ChangeValidatorNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    assert result['risk_level'] in ['high', 'critical']
    assert result['risk_score'] >= 0.7


# ============================================================================
# Recommendations Tests
# ============================================================================

@pytest.mark.asyncio
async def test_recommendations_for_errors():
    """Test recommendations when errors are present."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_016",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.NODE_REPLACEMENT,  # Not allowed
        rationale="Test",
        changes=[]  # No changes - also an error
    )

    validator = ChangeValidatorNode(
        allowed_hypothesis_types=["prompt_optimization"]
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    recommendations = result['validation'].recommendations
    assert len(recommendations) > 0

    # Should recommend fixing errors
    error_rec = next((r for r in recommendations if "error" in r.lower()), None)
    assert error_rec is not None


@pytest.mark.asyncio
async def test_recommendations_for_low_risk():
    """Test recommendations for low-risk hypothesis."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_017",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        rationale="Simple change",
        changes=[
            ChangeSpec(type="node_config_update", target_node_id="test_node")
        ]
    )

    validator = ChangeValidatorNode(auto_approve_risk_threshold=0.3)

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    recommendations = result['validation'].recommendations
    assert len(recommendations) > 0

    # Should mention safe to test
    safe_rec = next((r for r in recommendations if "safe" in r.lower() or "low risk" in r.lower()), None)
    assert safe_rec is not None


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_full_validation_workflow_approved(basic_hypothesis):
    """Test complete validation workflow resulting in approval."""
    validator = ChangeValidatorNode(
        max_nodes_added=5,
        max_nodes_removed=2,
        protected_nodes=[],
        allowed_hypothesis_types=["prompt_optimization", "parameter_tuning"]
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': basic_hypothesis})
    )

    result = await validator.process(context)

    # Verify complete result structure
    assert 'validation' in result
    assert 'approved' in result
    assert 'risk_score' in result
    assert 'risk_level' in result

    # Should be approved
    assert result['approved'] is True
    assert result['validation'].approved is True
    assert len(result['validation'].recommendations) > 0


@pytest.mark.asyncio
async def test_full_validation_workflow_rejected():
    """Test complete validation workflow resulting in rejection."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_test_018",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        target_node="critical_system",
        rationale="Test",
        changes=[
            ChangeSpec(type="node_remove", target_node_id="critical_system")
        ]
    )

    validator = ChangeValidatorNode(
        protected_nodes=["critical_system"]
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': hypothesis})
    )

    result = await validator.process(context)

    # Should be rejected
    assert result['approved'] is False
    assert result['validation'].approved is False
    assert len(result['validation'].violations) > 0

    # Should have error severity violations
    error_violations = [v for v in result['validation'].violations if v.severity == "error"]
    assert len(error_violations) > 0
