import asyncio
import copy
import pytest
import pickle
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable
from unittest.mock import MagicMock, AsyncMock, patch

from spark.nodes.base import (
    SparkError,
    BaseNode,
    EdgeCondition,
    Edge,
    Chain,
    wrap_sync_method,
)
from spark.nodes.types import ExecutionMetadata, ExecutionContext, NodeState, default_node_state, _safe_copy, NodeMessage

# Mark all tests in this module as async
#pytestmark = pytest.mark.asyncio


class TestExecutionMetadata:
    """Test ExecutionMetadata class."""
    
    def test_default_initialization(self):
        """Test default initialization values."""
        metadata = ExecutionMetadata()
        assert metadata.attempt == 1
        assert metadata.started_at is None
        assert metadata.finished_at is None
        assert metadata.duration is None
    
    def test_mark_started(self):
        """Test mark_started method."""
        metadata = ExecutionMetadata()
        metadata.mark_started(3)
        assert metadata.attempt == 3
        assert metadata.started_at is not None
        assert metadata.finished_at is None
        assert metadata.duration is None
    
    def test_mark_finished(self):
        """Test mark_finished method."""
        metadata = ExecutionMetadata()
        metadata.mark_started(1)
        time.sleep(0.01)  # Small delay to ensure duration > 0
        metadata.mark_finished()
        assert metadata.finished_at is not None
        assert metadata.duration is not None
        assert metadata.duration > 0
    
    def test_duration_calculation(self):
        """Test duration property calculation."""
        metadata = ExecutionMetadata()
        assert metadata.duration is None
        
        metadata.mark_started(1)
        assert metadata.duration is None
        
        time.sleep(0.01)
        metadata.mark_finished()
        assert metadata.duration is not None
        assert metadata.duration > 0
    
    def test_as_dict(self):
        """Test as_dict method."""
        metadata = ExecutionMetadata()
        metadata.mark_started(2)
        time.sleep(0.01)
        metadata.mark_finished()
        
        result = metadata.as_dict()
        assert result["attempt"] == 2
        assert result["started_at"] is not None
        assert result["finished_at"] is not None
        assert result["duration"] is not None
        assert result["duration"] > 0


class TestExecutionContext:
    """Test ExecutionContext class."""
    
    def test_default_initialization(self):
        """Test default initialization."""
        context = ExecutionContext()
        assert context.inputs.content is None
        assert context.state == default_node_state()
        assert isinstance(context.metadata, ExecutionMetadata)
    
    def test_initialization_with_values(self):
        """Test initialization with provided values."""
        inputs = {"key": "value"}
        message = NodeMessage(content=inputs)
        state = default_node_state()
        state["state_key"] = "state_value"
        outputs = {"output_key": "output_value"}
        
        context = ExecutionContext(
            inputs=message,
            state=state,
        )
        assert context.inputs == message
        assert context.state == state
    
    def test_snapshot(self):
        """Test snapshot method returns deep copy of state."""
        original_state = default_node_state()
        original_state.update({"key": "value", "nested": {"inner": "data"}})
        context = ExecutionContext(state=original_state)
        
        snapshot = context.snapshot()
        assert snapshot == original_state
        assert snapshot is not original_state  # Different object
        assert snapshot["nested"] is not original_state["nested"]  # Deep copy
    
    def test_fork(self):
        """Test fork method creates independent copy."""
        original_inputs = {"input": "data"}
        original_state = {"state": "value"}
        
        context = ExecutionContext(
            inputs=original_inputs,
            state=original_state,
        )
        
        forked = context.fork()
        
        # Should be copies, not references
        assert forked.inputs == original_inputs
        assert forked.inputs is not original_inputs
        assert forked.state == original_state
        assert forked.state is not original_state
        
        # Metadata should be independent
        assert forked.metadata is not context.metadata
        assert forked.metadata.attempt == context.metadata.attempt


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_safe_copy_simple_object(self):
        """Test _safe_copy with simple objects."""
        original = {"key": "value", "number": 42}
        copied = _safe_copy(original)
        assert copied == original
        assert copied is not original
    
    def test_safe_copy_nested_object(self):
        """Test _safe_copy with nested objects."""
        original = {"outer": {"inner": "value", "list": [1, 2, 3]}}
        copied = _safe_copy(original)
        assert copied == original
        assert copied is not original
        assert copied["outer"] is not original["outer"]
        assert copied["outer"]["list"] is not original["outer"]["list"]
    
    def test_safe_copy_immutable(self):
        """Test _safe_copy with immutable objects."""
        original = "string"
        copied = _safe_copy(original)
        assert copied == original
        assert copied is original  # Strings are immutable
    
    def test_safe_copy_with_exception(self):
        """Test _safe_copy fallback when deepcopy fails."""
        class Uncopyable:
            def __deepcopy__(self, memo):
                raise Exception("Cannot deep copy")
            def __copy__(self):
                raise Exception("Cannot copy")
        
        original = Uncopyable()
        copied = _safe_copy(original)
        assert copied is original  # Should return original object
    
    def test_wrap_sync_method_sync_function(self):
        """Test wrap_sync_method with synchronous function."""
        def sync_func(x):
            return x * 2
        
        wrapped = wrap_sync_method(sync_func)
        assert asyncio.iscoroutinefunction(wrapped)
        
        # Test that it works
        result = asyncio.run(wrapped(5))
        assert result == 10
    
    def test_wrap_sync_method_async_function(self):
        """Test wrap_sync_method with async function (should return as-is)."""
        async def async_func(x):
            return x * 2
        
        wrapped = wrap_sync_method(async_func)
        assert wrapped is async_func  # Should return original function
    
    def test_wrap_sync_method_preserves_metadata(self):
        """Test that wrapped function preserves metadata."""
        def sync_func(x):
            return x * 2
        
        sync_func.__name__ = "test_func"
        sync_func.__doc__ = "Test function"
        
        wrapped = wrap_sync_method(sync_func)
        assert wrapped.__name__ == "test_func"
        assert wrapped.__doc__ == "Test function"


class TestNode:
    """Test Node base class."""
    
    class TstNode(BaseNode):
        """Test implementation of Node."""
        async def process(self, context: ExecutionContext | None = None) -> Any:
            if context is None:
                return {"result": "no_context"}
            return {"result": "with_context", "inputs": context.inputs}

    class TstNodeNoArgs(BaseNode):
        """Test Node that doesn't use context argument."""
        async def process(self) -> Any:
            return {"result": "no_args"}
    
    def test_node_initialization_default(self):
        """Test Node initialization with defaults."""
        node = self.TstNode()
        assert node._state['processing'] is False
        assert len(node._state['pending_inputs']) == 0
        assert node.outputs.content is None
        assert node.edges == []
    
    def test_node_repr(self):
        """Test Node string representation."""
        node = self.TstNode()
        repr_str = repr(node)
        assert "Node(" in repr_str
        assert "edges=" in repr_str
    
    def test_prepare_context(self):
        """Test _prepare_context method."""
        node = self.TstNode()
        inputs = NodeMessage(content="input1: value1, input2: 42", metadata={})
        
        context = node._prepare_context(inputs)
        assert context.inputs == inputs
        assert context.state == node._state
        assert isinstance(context.metadata, ExecutionMetadata)
    
    def test_prepare_context_invalid_inputs(self):
        """Test _prepare_context with invalid inputs."""
        node = self.TstNode()
        with pytest.raises(TypeError):
            node._prepare_context("not_a_mapping")  # type: ignore
    
    def test_get_next_nodes_empty(self):
        """Test get_next_nodes with no edges."""
        node = self.TstNode()
        next_nodes = node.get_next_nodes()
        assert next_nodes == []
    
    def test_get_next_nodes_with_edges(self):
        """Test get_next_nodes with edges."""
        node1 = self.TstNode()
        node2 = self.TstNode()
        node3 = self.TstNode()
        
        # Create edges with different priorities
        edge1 = Edge(from_node=node1, to_node=node2, priority=1)
        edge2 = Edge(from_node=node1, to_node=node3, priority=2)
        node1.edges = [edge1, edge2]
        
        next_nodes = node1.get_next_nodes()
        # Should be sorted by priority (highest first)
        assert next_nodes == [node3, node2]
    
    def test_pop_ready_input_empty(self):
        """Test pop_ready_input with no pending inputs."""
        node = self.TstNode()
        result = node.pop_ready_input()
        assert result is None
    
    def test_pop_ready_input_with_pending(self):
        """Test pop_ready_input with pending inputs."""
        node = self.TstNode()
        node._state['pending_inputs'].append({"data": "value1"})
        node._state['pending_inputs'].append({"data": "value2"})

        result1 = node.pop_ready_input()
        result2 = node.pop_ready_input()
        result3 = node.pop_ready_input()
        
        assert result1 == {"data": "value1"}
        assert result2 == {"data": "value2"}
        assert result3 is None
    
    @pytest.mark.asyncio
    async def test_receive_from_parent(self):
        """Test receive_from_parent method."""
        node1 = self.TstNode()
        node2 = self.TstNode()
        
        node1.outputs = {"payload": "data"}
        result = await node2.receive_from_parent(node1)
        assert result is True
        assert node2._state['pending_inputs'][0] == {"payload": "data"}
    
    @pytest.mark.asyncio
    async def test_receive_from_parent_none_payload(self):
        """Test receive_from_parent with None payload."""
        node1 = self.TstNode()
        node2 = self.TstNode()
        
        result = await node2.receive_from_parent(node1)
        assert result is True
        assert node2._state['pending_inputs'][0].content is None
    
    @pytest.mark.asyncio
    async def test_do_method(self):
        """Test do method."""
        node = self.TstNode()
        inputs = NodeMessage(content="input: value", metadata={})
        
        result = await node.do(inputs)
        assert result.content == {"result": "with_context", "inputs": inputs}
        assert node.outputs == result
    
    @pytest.mark.asyncio
    async def test_do_method_no_inputs(self):
        """Test do method with no inputs."""
        node = self.TstNode()
        result = await node.do()
        assert result.content == {"result": "with_context", "inputs": NodeMessage(content='', metadata={})}
    
    def test_on_method_with_equals(self):
        """Test on method with equals conditions."""
        node = self.TstNode()
        node.outputs = NodeMessage(content={"status": "success", "code": 200}, metadata={})
        
        edge = node.on(status="success", code=200)
        
        # Test the condition function
        assert edge.condition.check(node) is True
        
        # Test with different outputs
        node.outputs = NodeMessage(content={"status": "error", "code": 500}, metadata={})
        assert edge.condition.check(node) is False
    
    def test_on_method_with_custom_condition(self):
        """Test that on method rejects callable conditions."""
        node = self.TstNode()

        def custom_condition(n):
            return n.outputs and n.outputs.get("value", 0) > 10

        # Callables should now raise TypeError
        with pytest.raises(TypeError, match="Lambda/callable conditions are not supported"):
            node.on(condition=custom_condition)
    
    def test_goto_method(self):
        """Test goto method."""
        node1 = self.TstNode()
        node2 = self.TstNode()

        node1.goto(node2)

        assert len(node1.edges) == 1
        edge = node1.edges[0]
        assert edge.from_node == node1
        assert edge.to_node == node2
        # No condition specified means no expr or equals
        assert edge.condition.expr is None
        assert edge.condition.equals is None

    def test_goto_method_with_condition(self):
        """Test goto method with expr condition."""
        node1 = self.TstNode()
        node2 = self.TstNode()
        condition = EdgeCondition(expr="$.outputs.score > 0.5")

        node1.goto(node2, condition)

        assert len(node1.edges) == 1
        edge = node1.edges[0]
        assert edge.from_node == node1
        assert edge.to_node == node2
        assert edge.condition == condition


class TestEdgeCondition:
    """Test EdgeCondition class."""

    def test_default_initialization(self):
        """Test default initialization."""
        condition = EdgeCondition()
        assert condition.expr is None
        assert condition.equals is None

    def test_initialization_with_expr(self):
        """Test initialization with expression."""
        condition = EdgeCondition(expr="$.outputs.score > 0.5")
        assert condition.expr == "$.outputs.score > 0.5"
        assert condition.equals is None

    def test_initialization_with_equals(self):
        """Test initialization with equals dict."""
        condition = EdgeCondition(equals={'status': 'ok'})
        assert condition.expr is None
        assert condition.equals == {'status': 'ok'}

    def test_check_none_condition(self):
        """Test check with None condition (always True)."""
        condition = EdgeCondition()
        node = TestNode.TstNode()
        assert condition.check(node) is True

    def test_check_equals_condition_simple(self):
        """Test check with equals condition."""
        condition = EdgeCondition(equals={'status': 'ok'})
        node = TestNode.TstNode()

        # Test with matching outputs
        node.outputs = NodeMessage(content={'status': 'ok'})
        assert condition.check(node) is True

        # Test with non-matching outputs
        node.outputs = NodeMessage(content={'status': 'error'})
        assert condition.check(node) is False

    def test_check_expr_condition(self):
        """Test check with expression condition."""
        condition = EdgeCondition(expr="$.outputs.value > 10")
        node = TestNode.TstNode()

        # Test with value greater than 10
        node.outputs = NodeMessage(content={'value': 15})
        assert condition.check(node) is True

        # Test with value less than 10
        node.outputs = NodeMessage(content={'value': 5})
        assert condition.check(node) is False


class TestEdge:
    """Test Edge class."""
    
    def test_default_initialization(self):
        """Test default initialization."""
        from_node = TestNode.TstNode()
        edge = Edge(from_node=from_node)
        
        assert edge.from_node == from_node
        assert edge.to_node is None
        assert edge.id is not None
        assert edge.description == ""
        assert isinstance(edge.condition, EdgeCondition)
        assert edge.priority == 0
    
    def test_initialization_with_all_params(self):
        """Test initialization with all parameters."""
        from_node = TestNode.TstNode()
        to_node = TestNode.TstNode()
        condition = EdgeCondition(lambda n: True)
        
        edge = Edge(
            from_node=from_node,
            to_node=to_node,
            description="Test edge",
            condition=condition,
            priority=5
        )
        
        assert edge.from_node == from_node
        assert edge.to_node == to_node
        assert edge.description == "Test edge"
        assert edge.condition == condition
        assert edge.priority == 5
    
    def test_rshift_with_node(self):
        """Test >> operator with BaseNode."""
        from_node = TestNode.TstNode()
        to_node = TestNode.TstNode()
        edge = Edge(from_node=from_node)
        
        result = edge >> to_node
        
        assert edge.to_node == to_node
        assert edge in from_node.edges
    
    def test_rshift_with_edge(self):
        """Test >> operator with Edge."""
        from_node1 = TestNode.TstNode()
        from_node2 = TestNode.TstNode()
        to_node = TestNode.TstNode()
        
        edge1 = Edge(from_node=from_node1)
        edge2 = Edge(from_node=from_node2, to_node=to_node)
        
        chain = edge1 >> edge2
        
        assert edge1.to_node == from_node2
        assert edge1 in from_node1.edges
        assert edge2 in from_node2.edges
        assert chain.nodes == [from_node1, from_node2, to_node]
    
    def test_rshift_with_chain(self):
        """Test >> operator with Chain."""
        from_node = TestNode.TstNode()
        node1 = TestNode.TstNode()
        node2 = TestNode.TstNode()
        chain = Chain([node1, node2])
        edge = Edge(from_node=from_node)
        
        result = edge >> chain
        
        assert result == chain
        assert edge.to_node == node1
        assert edge in from_node.edges
        assert chain.nodes[0] == from_node  # from_node prepended to chain
    
    def test_rshift_already_has_to_node(self):
        """Test >> operator when edge already has to_node."""
        from_node = TestNode.TstNode()
        to_node1 = TestNode.TstNode()
        to_node2 = TestNode.TstNode()
        
        edge = Edge(from_node=from_node, to_node=to_node1)
        
        with pytest.raises(SparkError):
            edge >> to_node2


class TestChain:
    """Test Chain class."""
    
    def test_initialization_with_valid_nodes(self):
        """Test initialization with valid nodes."""
        node1 = TestNode.TstNode()
        node2 = TestNode.TstNode()
        node3 = TestNode.TstNode()
        
        chain = Chain([node1, node2, node3])
        assert chain.nodes == [node1, node2, node3]
    
    def test_initialization_with_empty_list(self):
        """Test initialization with empty list."""
        with pytest.raises(SparkError):
            Chain([])
    
    def test_initialization_with_non_node(self):
        """Test initialization with non-BaseNode objects."""
        with pytest.raises(SparkError):
            Chain(["not_a_node", "also_not_a_node"])  # type: ignore
    
    def test_rshift_operator(self):
        """Test >> operator to add next node."""
        node1 = TestNode.TstNode()
        node2 = TestNode.TstNode()
        node3 = TestNode.TstNode()
        
        chain = Chain([node1, node2])
        result = chain >> node3
        
        assert result == chain
        assert chain.nodes == [node1, node2, node3]


class TestSparkError:
    """Test SparkError exception."""
    
    def test_spark_error_inheritance(self):
        """Test that SparkError inherits from Exception."""
        error = SparkError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"
    
    def test_spark_error_creation(self):
        """Test SparkError creation with message."""
        message = "Something went wrong"
        error = SparkError(message)
        assert str(error) == message
