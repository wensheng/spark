"""
Test enhanced EdgeCondition expression evaluation.

Tests all supported operators:
- Comparison: ==, !=, >, <, >=, <=
- Logical: and, or, not
- Membership: in
- Nested paths
"""

import pytest
from spark.nodes.base import BaseNode, EdgeCondition
from spark.nodes.types import NodeMessage


class MockNode(BaseNode):
    """Mock node for testing edge conditions."""

    async def process(self, context):
        pass


@pytest.fixture
def node():
    """Create a mock node with sample outputs."""
    n = MockNode()
    n.outputs = NodeMessage(content={
        'score': 0.85,
        'status': 'ready',
        'count': 15,
        'category': 'A',
        'failed': False,
        'tags': ['important', 'urgent'],
        'nested': {
            'level1': {
                'level2': 'deep_value'
            },
            'value': 42
        }
    })
    return n


class TestComparisonOperators:
    """Test comparison operators: ==, !=, >, <, >=, <="""

    def test_equality(self, node):
        cond = EdgeCondition(expr="$.outputs.status == 'ready'")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.status == 'pending'")
        assert cond.check(node) is False

    def test_inequality(self, node):
        cond = EdgeCondition(expr="$.outputs.status != 'pending'")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.status != 'ready'")
        assert cond.check(node) is False

    def test_greater_than(self, node):
        cond = EdgeCondition(expr="$.outputs.score > 0.5")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.score > 0.9")
        assert cond.check(node) is False

    def test_less_than(self, node):
        cond = EdgeCondition(expr="$.outputs.score < 0.9")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.score < 0.5")
        assert cond.check(node) is False

    def test_greater_than_or_equal(self, node):
        cond = EdgeCondition(expr="$.outputs.count >= 15")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.count >= 10")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.count >= 20")
        assert cond.check(node) is False

    def test_less_than_or_equal(self, node):
        cond = EdgeCondition(expr="$.outputs.count <= 15")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.count <= 20")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.count <= 10")
        assert cond.check(node) is False


class TestLogicalOperators:
    """Test logical operators: and, or, not"""

    def test_and_operator(self, node):
        cond = EdgeCondition(expr="$.outputs.score > 0.5 and $.outputs.count >= 10")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.score > 0.5 and $.outputs.count >= 20")
        assert cond.check(node) is False

        cond = EdgeCondition(expr="$.outputs.score > 0.9 and $.outputs.count >= 10")
        assert cond.check(node) is False

    def test_or_operator(self, node):
        cond = EdgeCondition(expr="$.outputs.score > 0.9 or $.outputs.count >= 10")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.score > 0.5 or $.outputs.count >= 20")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.score > 0.9 or $.outputs.count >= 20")
        assert cond.check(node) is False

    def test_not_operator(self, node):
        cond = EdgeCondition(expr="not $.outputs.failed")
        assert cond.check(node) is True

        node.outputs.content['failed'] = True
        assert cond.check(node) is False

    def test_complex_logical_expression(self, node):
        # Multiple and/or combinations
        cond = EdgeCondition(expr="$.outputs.score > 0.8 and $.outputs.status == 'ready' and $.outputs.count >= 10")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.score > 0.9 or $.outputs.status == 'ready' or $.outputs.count >= 20")
        assert cond.check(node) is True


class TestMembershipOperator:
    """Test membership operator: in"""

    def test_in_list(self, node):
        cond = EdgeCondition(expr="$.outputs.category in ['A', 'B', 'C']")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.category in ['X', 'Y', 'Z']")
        assert cond.check(node) is False

    def test_in_numeric_list(self, node):
        cond = EdgeCondition(expr="$.outputs.count in [10, 15, 20]")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.count in [5, 10, 20]")
        assert cond.check(node) is False


class TestNestedPaths:
    """Test nested object access"""

    def test_nested_two_levels(self, node):
        cond = EdgeCondition(expr="$.outputs.nested.value == 42")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.nested.value > 40")
        assert cond.check(node) is True

    def test_nested_three_levels(self, node):
        cond = EdgeCondition(expr="$.outputs.nested.level1.level2 == 'deep_value'")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.nested.level1.level2 != 'other'")
        assert cond.check(node) is True

    def test_nested_nonexistent_path(self, node):
        cond = EdgeCondition(expr="$.outputs.nested.nonexistent == 'value'")
        assert cond.check(node) is False


class TestDataTypes:
    """Test various data types in comparisons"""

    def test_string_comparison(self, node):
        cond = EdgeCondition(expr="$.outputs.status == 'ready'")
        assert cond.check(node) is True

    def test_numeric_comparison(self, node):
        cond = EdgeCondition(expr="$.outputs.score == 0.85")
        assert cond.check(node) is True

        cond = EdgeCondition(expr="$.outputs.count == 15")
        assert cond.check(node) is True

    def test_boolean_comparison(self, node):
        cond = EdgeCondition(expr="$.outputs.failed == False")
        assert cond.check(node) is True

        node.outputs.content['failed'] = True
        cond = EdgeCondition(expr="$.outputs.failed == True")
        assert cond.check(node) is True


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_missing_key(self, node):
        cond = EdgeCondition(expr="$.outputs.nonexistent == 'value'")
        assert cond.check(node) is False

    def test_invalid_comparison(self, node):
        # Comparing incompatible types should return False
        cond = EdgeCondition(expr="$.outputs.status > 10")
        # String > int comparison might fail, should handle gracefully
        result = cond.check(node)
        # Should not raise exception
        assert isinstance(result, bool)

    def test_malformed_expression(self, node):
        cond = EdgeCondition(expr="invalid expression")
        assert cond.check(node) is False

    def test_empty_outputs(self):
        n = MockNode()
        n.outputs = NodeMessage(content={})
        cond = EdgeCondition(expr="$.outputs.key == 'value'")
        assert cond.check(n) is False

    def test_none_outputs(self):
        n = MockNode()
        n.outputs = NodeMessage(content=None)
        cond = EdgeCondition(expr="$.outputs.key == 'value'")
        assert cond.check(n) is False


class TestBackwardCompatibility:
    """Test that old syntax still works"""

    def test_simple_equality_old_syntax(self, node):
        # The original simple equality should still work
        cond = EdgeCondition(expr="$.outputs.status == 'ready'")
        assert cond.check(node) is True

    def test_equals_dict_still_works(self, node):
        # The equals dict shortcut should still work
        cond = EdgeCondition(equals={'status': 'ready'})
        assert cond.check(node) is True

        cond = EdgeCondition(equals={'status': 'pending'})
        assert cond.check(node) is False


class TestEqualsLogic:
    """Test that equals dict uses AND logic (all must match)"""

    def test_equals_single_match(self, node):
        """Single key/value should match"""
        cond = EdgeCondition(equals={'status': 'ready'})
        assert cond.check(node) is True

        cond = EdgeCondition(equals={'status': 'pending'})
        assert cond.check(node) is False

    def test_equals_all_must_match(self, node):
        """ALL key/value pairs must match (AND logic)"""
        # Both keys match - should return True
        cond = EdgeCondition(equals={'status': 'ready', 'count': 15})
        assert cond.check(node) is True

        # One key matches, one doesn't - should return False
        cond = EdgeCondition(equals={'status': 'ready', 'count': 999})
        assert cond.check(node) is False

        # One key matches, one doesn't - should return False
        cond = EdgeCondition(equals={'status': 'pending', 'count': 15})
        assert cond.check(node) is False

        # Neither key matches - should return False
        cond = EdgeCondition(equals={'status': 'pending', 'count': 999})
        assert cond.check(node) is False

    def test_equals_multiple_keys_all_match(self, node):
        """Multiple keys all matching should return True"""
        cond = EdgeCondition(equals={
            'status': 'ready',
            'count': 15,
            'category': 'A',
            'failed': False
        })
        assert cond.check(node) is True

    def test_equals_multiple_keys_one_mismatch(self, node):
        """If even one key doesn't match, should return False"""
        # Three match, one doesn't
        cond = EdgeCondition(equals={
            'status': 'ready',      # matches
            'count': 15,            # matches
            'category': 'A',        # matches
            'failed': True          # DOESN'T match (node has False)
        })
        assert cond.check(node) is False

    def test_equals_nonexistent_key(self, node):
        """Keys that don't exist should not match"""
        cond = EdgeCondition(equals={'nonexistent_key': 'value'})
        assert cond.check(node) is False

        # Mix of existing and non-existing keys
        cond = EdgeCondition(equals={
            'status': 'ready',          # exists and matches
            'nonexistent_key': 'value'  # doesn't exist
        })
        assert cond.check(node) is False


class TestRealWorldScenarios:
    """Test real-world conditional routing scenarios"""

    def test_score_threshold_routing(self, node):
        """Route to different nodes based on score thresholds"""
        # High quality route
        high_quality = EdgeCondition(expr="$.outputs.score >= 0.8")
        assert high_quality.check(node) is True

        # Medium quality route
        medium_quality = EdgeCondition(expr="$.outputs.score >= 0.5 and $.outputs.score < 0.8")
        assert medium_quality.check(node) is False  # score is 0.85

        # Low quality route
        low_quality = EdgeCondition(expr="$.outputs.score < 0.5")
        assert low_quality.check(node) is False

    def test_multi_condition_approval(self, node):
        """Approve only if multiple conditions are met"""
        approval = EdgeCondition(
            expr="$.outputs.score > 0.7 and $.outputs.status == 'ready' and $.outputs.count >= 10"
        )
        assert approval.check(node) is True

        # Change one condition
        node.outputs.content['status'] = 'pending'
        assert approval.check(node) is False

    def test_category_routing(self, node):
        """Route based on category membership"""
        priority_categories = EdgeCondition(expr="$.outputs.category in ['A', 'B']")
        assert priority_categories.check(node) is True

        regular_categories = EdgeCondition(expr="$.outputs.category in ['C', 'D', 'E']")
        assert regular_categories.check(node) is False

    def test_error_handling_route(self, node):
        """Route to error handler if failed"""
        error_route = EdgeCondition(expr="$.outputs.failed == True")
        assert error_route.check(node) is False

        success_route = EdgeCondition(expr="not $.outputs.failed")
        assert success_route.check(node) is True
