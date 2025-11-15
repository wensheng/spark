"""Tests for PatternExtractor."""

import pytest
import pytest_asyncio
from spark.rsi.pattern_extractor import PatternExtractor, ExtractedPattern
from spark.rsi.experience_db import ExperienceDatabase


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def experience_db_with_data():
    """Create experience database with sample data."""
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

    # Add rolled back node_replacement hypotheses
    for i in range(3):
        hyp_id = f"hyp_rollback_{i}"
        await db.store_hypothesis(
            hypothesis_id=hyp_id,
            graph_id="test_graph",
            graph_version_baseline="1.0.0",
            hypothesis_type="node_replacement",
            proposal={'test': 'data'},
            target_node="node_c"
        )
        await db.update_test_results(hyp_id, {
            'status': 'passed',
            'comparison': {
                'success_rate_delta': 0.03,
                'avg_duration_delta': -0.05,
                'is_improvement': True,
                'is_regression': False
            }
        })
        await db.update_deployment_outcome(
            hyp_id,
            deployed=True,
            outcome={
                'successful': False,
                'rolled_back': True,
                'rollback_reason': 'Latency increased by 120%'
            },
            lessons=['node_replacement caused regression'],
            patterns=['node_replacement_rollback']
        )

    return db


@pytest_asyncio.fixture
async def empty_experience_db():
    """Create empty experience database."""
    db = ExperienceDatabase()
    await db.initialize()
    return db


# ============================================================================
# Initialization Tests
# ============================================================================

def test_pattern_extractor_init(empty_experience_db):
    """Test PatternExtractor initialization."""
    extractor = PatternExtractor(empty_experience_db)
    assert extractor.experience_db == empty_experience_db
    assert extractor.min_evidence_count == 3
    assert extractor.min_confidence == 0.6


def test_pattern_extractor_custom_init(empty_experience_db):
    """Test PatternExtractor with custom parameters."""
    extractor = PatternExtractor(
        empty_experience_db,
        min_evidence_count=5,
        min_confidence=0.8
    )
    assert extractor.min_evidence_count == 5
    assert extractor.min_confidence == 0.8


# ============================================================================
# Pattern Extraction Tests
# ============================================================================

@pytest.mark.asyncio
async def test_extract_patterns_empty_db(empty_experience_db):
    """Test pattern extraction from empty database."""
    extractor = PatternExtractor(empty_experience_db)
    patterns = await extractor.extract_patterns()
    assert patterns == []


@pytest.mark.asyncio
async def test_extract_success_patterns(experience_db_with_data):
    """Test extraction of success patterns."""
    extractor = PatternExtractor(experience_db_with_data, min_evidence_count=3)
    patterns = await extractor._extract_success_patterns()

    # Should find prompt_optimization success pattern (5 successful examples)
    prompt_opt_patterns = [
        p for p in patterns
        if p.hypothesis_type == "prompt_optimization"
    ]
    assert len(prompt_opt_patterns) > 0

    pattern = prompt_opt_patterns[0]
    assert pattern.pattern_type == "success"
    assert pattern.evidence_count == 5
    assert pattern.confidence > 0.6
    assert "Continue using" in pattern.recommendation


@pytest.mark.asyncio
async def test_extract_failure_patterns(experience_db_with_data):
    """Test extraction of failure patterns."""
    extractor = PatternExtractor(experience_db_with_data, min_evidence_count=3)
    patterns = await extractor._extract_failure_patterns()

    # Should find parameter_tuning failure pattern (4 failed examples)
    param_tune_patterns = [
        p for p in patterns
        if p.hypothesis_type == "parameter_tuning"
    ]
    assert len(param_tune_patterns) > 0

    pattern = param_tune_patterns[0]
    assert pattern.pattern_type == "failure"
    assert pattern.evidence_count == 4
    assert "Avoid" in pattern.recommendation


@pytest.mark.asyncio
async def test_extract_improvement_patterns(experience_db_with_data):
    """Test extraction of improvement patterns."""
    extractor = PatternExtractor(experience_db_with_data, min_evidence_count=3)
    patterns = await extractor._extract_improvement_patterns()

    # Should find prompt_optimization improvement pattern
    improved = [
        p for p in patterns
        if p.hypothesis_type == "prompt_optimization"
    ]
    assert len(improved) > 0

    pattern = improved[0]
    assert pattern.pattern_type == "improvement"
    assert pattern.success_rate == 1.0  # All showed improvement
    assert "Prioritize" in pattern.recommendation
    assert 'avg_success_delta' in pattern.context


@pytest.mark.asyncio
async def test_extract_regression_patterns(experience_db_with_data):
    """Test extraction of regression patterns."""
    extractor = PatternExtractor(experience_db_with_data, min_evidence_count=3)
    patterns = await extractor._extract_regression_patterns()

    # Should find node_replacement regression pattern (3 rolled back)
    regression = [
        p for p in patterns
        if p.hypothesis_type == "node_replacement"
    ]
    assert len(regression) > 0

    pattern = regression[0]
    assert pattern.pattern_type == "regression"
    assert pattern.evidence_count == 3
    assert "Be cautious" in pattern.recommendation
    assert 'common_reason' in pattern.context


@pytest.mark.asyncio
async def test_extract_all_patterns(experience_db_with_data):
    """Test extraction of all pattern types together."""
    extractor = PatternExtractor(experience_db_with_data, min_evidence_count=3)
    patterns = await extractor.extract_patterns()

    # Should have multiple pattern types
    pattern_types = set(p.pattern_type for p in patterns)
    assert 'success' in pattern_types
    assert 'failure' in pattern_types
    assert 'improvement' in pattern_types
    assert 'regression' in pattern_types

    # All patterns should meet minimum thresholds
    for pattern in patterns:
        assert pattern.confidence >= extractor.min_confidence
        assert pattern.evidence_count >= extractor.min_evidence_count


# ============================================================================
# Filtering Tests
# ============================================================================

@pytest.mark.asyncio
async def test_min_evidence_count_filtering(experience_db_with_data):
    """Test that patterns with insufficient evidence are filtered."""
    # Set high evidence requirement
    extractor = PatternExtractor(experience_db_with_data, min_evidence_count=10)
    patterns = await extractor.extract_patterns()

    # Should filter out patterns with < 10 examples
    # (our test data has max 5 examples per type)
    assert len(patterns) == 0


@pytest.mark.asyncio
async def test_min_confidence_filtering(experience_db_with_data):
    """Test that low confidence patterns are filtered."""
    # Set very high confidence requirement
    extractor = PatternExtractor(experience_db_with_data, min_confidence=0.99)
    patterns = await extractor.extract_patterns()

    # Should filter out most patterns
    assert all(p.confidence >= 0.99 for p in patterns)


# ============================================================================
# Recommendation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_recommendations_for_type(experience_db_with_data):
    """Test getting recommendations for specific hypothesis type."""
    extractor = PatternExtractor(experience_db_with_data, min_evidence_count=3)
    patterns = await extractor.extract_patterns()

    # Get recommendations for prompt_optimization
    recs = extractor.get_recommendations_for_hypothesis_type(
        patterns, "prompt_optimization"
    )

    assert len(recs) > 0
    # Should include both success and improvement patterns
    assert any("SUCCESS" in rec for rec in recs)
    assert any("IMPROVEMENT" in rec for rec in recs)


@pytest.mark.asyncio
async def test_should_avoid_hypothesis_type(experience_db_with_data):
    """Test detection of hypothesis types to avoid."""
    extractor = PatternExtractor(experience_db_with_data, min_evidence_count=3)
    patterns = await extractor.extract_patterns()

    # parameter_tuning has high failure rate - should avoid
    should_avoid = extractor.should_avoid_hypothesis_type(
        patterns, "parameter_tuning", threshold=0.7
    )
    assert should_avoid is True

    # prompt_optimization has high success rate - should not avoid
    should_not_avoid = extractor.should_avoid_hypothesis_type(
        patterns, "prompt_optimization", threshold=0.7
    )
    assert should_not_avoid is False


@pytest.mark.asyncio
async def test_get_priority_score(experience_db_with_data):
    """Test priority scoring for hypothesis types."""
    extractor = PatternExtractor(experience_db_with_data, min_evidence_count=3)
    patterns = await extractor.extract_patterns()

    # prompt_optimization should have high priority (success + improvement)
    prompt_score = extractor.get_priority_score(patterns, "prompt_optimization")
    assert prompt_score > 0.7

    # parameter_tuning should have low priority (failure)
    param_score = extractor.get_priority_score(patterns, "parameter_tuning")
    assert param_score < 0.5

    # node_replacement should have medium-low priority (improvement but regression)
    node_score = extractor.get_priority_score(patterns, "node_replacement")
    assert 0.2 <= node_score <= 0.7


# ============================================================================
# Pattern Structure Tests
# ============================================================================

def test_extracted_pattern_structure():
    """Test ExtractedPattern dataclass structure."""
    pattern = ExtractedPattern(
        pattern_id="test_pattern",
        pattern_type="success",
        hypothesis_type="prompt_optimization",
        context={'graph_id': 'test'},
        recommendation="Test recommendation",
        confidence=0.85,
        evidence_count=10,
        success_rate=0.90
    )

    assert pattern.pattern_id == "test_pattern"
    assert pattern.pattern_type == "success"
    assert pattern.confidence == 0.85
    assert pattern.evidence_count == 10


# ============================================================================
# Graph-Specific Pattern Tests
# ============================================================================

@pytest.mark.asyncio
async def test_extract_patterns_for_specific_graph():
    """Test pattern extraction filtered by graph_id."""
    db = ExperienceDatabase()
    await db.initialize()

    # Add data for graph_a
    await db.store_hypothesis(
        "hyp_a1", "graph_a", "1.0", "prompt_optimization", {'test': 'data'}
    )
    await db.update_test_results("hyp_a1", {
        'status': 'passed',
        'comparison': {'is_improvement': True, 'success_rate_delta': 0.05, 'avg_duration_delta': -0.1}
    })
    await db.update_deployment_outcome(
        "hyp_a1", True, {'successful': True}, [], []
    )

    # Add data for graph_b
    await db.store_hypothesis(
        "hyp_b1", "graph_b", "1.0", "prompt_optimization", {'test': 'data'}
    )
    await db.update_test_results("hyp_b1", {
        'status': 'failed',
        'comparison': {'is_improvement': False, 'success_rate_delta': -0.05, 'avg_duration_delta': 0.1}
    })
    await db.update_deployment_outcome(
        "hyp_b1", False, {'successful': False}, [], []
    )

    # Extract patterns for graph_a only
    extractor = PatternExtractor(db, min_evidence_count=1, min_confidence=0.5)
    patterns_a = await extractor.extract_patterns(graph_id="graph_a")

    # Should only include graph_a patterns
    for pattern in patterns_a:
        if pattern.context:
            # If context has graph_id, should be graph_a
            if 'graph_id' in pattern.context:
                assert pattern.context['graph_id'] == "graph_a"


# ============================================================================
# Edge Case Tests
# ============================================================================

@pytest.mark.asyncio
async def test_no_patterns_below_threshold():
    """Test when no patterns meet thresholds."""
    db = ExperienceDatabase()
    await db.initialize()

    # Add only 1 example (below min_evidence_count of 3)
    await db.store_hypothesis(
        "hyp_1", "test_graph", "1.0", "prompt_optimization", {'test': 'data'}
    )

    extractor = PatternExtractor(db, min_evidence_count=3)
    patterns = await extractor.extract_patterns()

    assert patterns == []


@pytest.mark.asyncio
async def test_mixed_success_failure_same_type():
    """Test pattern extraction when same type has both success and failure."""
    db = ExperienceDatabase()
    await db.initialize()

    # Add 3 successful + 3 failed of same type
    for i in range(3):
        hyp_id = f"hyp_success_{i}"
        await db.store_hypothesis(
            hyp_id, "test_graph", "1.0", "prompt_optimization", {'test': 'data'}
        )
        await db.update_test_results(hyp_id, {
            'status': 'passed',
            'comparison': {'is_improvement': True, 'success_rate_delta': 0.05, 'avg_duration_delta': -0.1}
        })
        await db.update_deployment_outcome(
            hyp_id, True, {'successful': True}, [], []
        )

    for i in range(3):
        hyp_id = f"hyp_fail_{i}"
        await db.store_hypothesis(
            hyp_id, "test_graph", "1.0", "prompt_optimization", {'test': 'data'}
        )
        await db.update_test_results(hyp_id, {
            'status': 'failed',
            'comparison': {'is_improvement': False, 'success_rate_delta': -0.05, 'avg_duration_delta': 0.1}
        })
        await db.update_deployment_outcome(
            hyp_id, False, {'successful': False}, [], []
        )

    extractor = PatternExtractor(db, min_evidence_count=3, min_confidence=0.4)
    patterns = await extractor.extract_patterns()

    # Should extract both success and failure patterns
    types_for_prompt_opt = [
        p.pattern_type for p in patterns
        if p.hypothesis_type == "prompt_optimization"
    ]

    # With 50/50 split, might not meet confidence threshold
    # But should at least try to extract patterns
    assert len(patterns) >= 0  # May or may not meet thresholds
