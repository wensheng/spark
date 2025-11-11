"""Integration tests for graph state with nodes and graphs."""

import pytest
import asyncio
from spark.nodes import Node, EdgeCondition
from spark.graphs import Graph, Task, TaskType
from spark.nodes.types import NodeMessage


class CounterNode(Node):
    """Node that increments a counter in graph state."""

    async def process(self, context):
        if context.graph_state is None:
            return {'error': 'No graph state'}

        counter = await context.graph_state.get('counter', 0)
        await context.graph_state.set('counter', counter + 1)
        return {'counter': counter + 1}


class ResultCollectorNode(Node):
    """Node that appends results to a list in graph state."""

    async def process(self, context):
        if context.graph_state is None:
            return {'error': 'No graph state'}

        result = context.inputs.content.get('result', 'unknown')
        results = await context.graph_state.get('results', [])
        results.append(result)
        await context.graph_state.set('results', results)
        return {'collected': len(results)}


class ConditionalNode(Node):
    """Node that makes decisions based on graph state."""

    async def process(self, context):
        if context.graph_state is None:
            return {'should_continue': False}

        counter = await context.graph_state.get('counter', 0)
        return {'should_continue': counter < 3}


class TestGraphStateIntegration:
    """Integration tests for graph state with actual nodes and graphs."""

    @pytest.mark.asyncio
    async def test_basic_state_access_in_node(self):
        """Test that nodes can access graph state."""
        node = CounterNode()
        graph = Graph(start=node)

        result = await graph.run()

        assert result.content['counter'] == 1
        assert await graph.get_state('counter') == 1

    @pytest.mark.asyncio
    async def test_state_with_initial_values(self):
        """Test graph initialized with initial state."""
        node = CounterNode()
        graph = Graph(start=node, initial_state={'counter': 10})

        result = await graph.run()

        assert result.content['counter'] == 11
        assert await graph.get_state('counter') == 11

    @pytest.mark.asyncio
    async def test_state_persists_across_nodes(self):
        """Test that state persists as execution flows through nodes."""
        node1 = CounterNode()
        node2 = CounterNode()
        node3 = CounterNode()

        node1.goto(node2)
        node2.goto(node3)

        graph = Graph(start=node1)
        result = await graph.run()

        # Counter should be 3 after 3 increments
        assert result.content['counter'] == 3
        assert await graph.get_state('counter') == 3

    @pytest.mark.asyncio
    async def test_state_with_loops(self):
        """Test state in a graph with loops."""
        counter_node = CounterNode()
        condition_node = ConditionalNode()

        counter_node.goto(condition_node)
        condition_node.on(should_continue=True) >> counter_node

        graph = Graph(start=counter_node, initial_state={'counter': 0})
        result = await graph.run()

        # Loop should run until counter reaches 3
        assert await graph.get_state('counter') == 3

    @pytest.mark.asyncio
    async def test_result_collection_across_nodes(self):
        """Test collecting results from multiple nodes."""
        collector = ResultCollectorNode()

        graph = Graph(start=collector, initial_state={'results': []})

        # Run the graph multiple times
        await graph.run({'result': 'first'})
        await graph.run({'result': 'second'})
        await graph.run({'result': 'third'})

        results = await graph.get_state('results')
        assert results == ['first', 'second', 'third']

    @pytest.mark.asyncio
    async def test_state_reset(self):
        """Test resetting graph state between runs."""
        node = CounterNode()
        graph = Graph(start=node)

        # First run
        await graph.run()
        assert await graph.get_state('counter') == 1

        # Second run without reset
        await graph.run()
        assert await graph.get_state('counter') == 2

        # Reset and run again
        graph.reset_state({'counter': 0})
        await graph.run()
        assert await graph.get_state('counter') == 1

    @pytest.mark.asyncio
    async def test_state_disabled(self):
        """Test that state can be disabled."""
        node = CounterNode()
        graph = Graph(start=node, enable_graph_state=False)

        result = await graph.run()

        # Node should report no graph state
        assert result.content.get('error') == 'No graph state'

    @pytest.mark.asyncio
    async def test_state_snapshot(self):
        """Test getting state snapshot."""
        node1 = CounterNode()
        node2 = CounterNode()

        node1.goto(node2)

        graph = Graph(start=node1, initial_state={'counter': 0, 'name': 'test'})
        await graph.run()

        snapshot = graph.get_state_snapshot()
        assert snapshot['counter'] == 2
        assert snapshot['name'] == 'test'

        # Modifying snapshot shouldn't affect graph state
        snapshot['counter'] = 999
        assert await graph.get_state('counter') == 2

    @pytest.mark.asyncio
    async def test_graph_helper_methods(self):
        """Test Graph's state helper methods."""
        graph = Graph(start=CounterNode())

        # Test set_state
        await graph.set_state('key1', 'value1')
        assert await graph.get_state('key1') == 'value1'

        # Test update_state
        await graph.update_state({'key2': 'value2', 'key3': 'value3'})
        assert await graph.get_state('key2') == 'value2'
        assert await graph.get_state('key3') == 'value3'

    @pytest.mark.asyncio
    async def test_state_with_branching(self):
        """Test state with branching execution."""

        class BranchNode(Node):
            async def process(self, context):
                branch = context.inputs.content.get('branch', 'A')
                await context.graph_state.update({f'visited_{branch}': True})
                return {'branch': branch}

        start_node = BranchNode()
        branch_a = BranchNode()
        branch_b = BranchNode()

        start_node.on(branch='A') >> branch_a
        start_node.on(branch='B') >> branch_b

        graph = Graph(start=start_node)

        # Test branch A
        await graph.run({'branch': 'A'})
        assert await graph.get_state('visited_A')

        # Reset and test branch B
        graph.reset_state()
        await graph.run({'branch': 'B'})
        assert await graph.get_state('visited_B')

    @pytest.mark.asyncio
    async def test_state_with_transaction(self):
        """Test using transaction for atomic updates."""

        class TransactionNode(Node):
            async def process(self, context):
                async with context.graph_state.transaction() as state:
                    state['x'] = state.get('x', 0) + 1
                    state['y'] = state.get('y', 0) + 1
                return {'updated': True}

        node = TransactionNode()
        graph = Graph(start=node, initial_state={'x': 0, 'y': 0})

        await graph.run()

        assert await graph.get_state('x') == 1
        assert await graph.get_state('y') == 1

    @pytest.mark.asyncio
    async def test_concurrent_state_access_long_running(self):
        """Test concurrent state access in LONG_RUNNING mode."""

        class ConcurrentCounterNode(Node):
            async def process(self, context):
                # Simulate some work
                await asyncio.sleep(0.01)

                counter = await context.graph_state.get('counter', 0)
                await context.graph_state.set('counter', counter + 1)

                # Check if we should stop
                if counter >= 5:
                    self.stop()

                return {'counter': counter + 1}

        node1 = ConcurrentCounterNode()
        node2 = ConcurrentCounterNode()
        node3 = ConcurrentCounterNode()

        # Set up circular flow
        node1.goto(node2)
        node2.goto(node3)
        node3.goto(node1)

        graph = Graph(start=node1, initial_state={'counter': 0})

        task = Task(
            inputs=NodeMessage(content='', metadata={}),
            type=TaskType.LONG_RUNNING
        )

        await graph.run(task)

        # Counter should be at least 5 (could be more due to concurrency)
        final_counter = await graph.get_state('counter')
        assert final_counter >= 5

    @pytest.mark.asyncio
    async def test_state_with_complex_data(self):
        """Test state with complex nested data structures."""

        class DataNode(Node):
            async def process(self, context):
                config = await context.graph_state.get('config', {})
                config.setdefault('settings', {})
                config['settings']['processed'] = True

                await context.graph_state.set('config', config)
                return {'done': True}

        node = DataNode()
        graph = Graph(
            start=node,
            initial_state={
                'config': {
                    'name': 'test',
                    'settings': {'timeout': 30}
                }
            }
        )

        await graph.run()

        config = await graph.get_state('config')
        assert config['name'] == 'test'
        assert config['settings']['timeout'] == 30
        assert config['settings']['processed'] is True

    @pytest.mark.asyncio
    async def test_edge_condition_using_graph_state(self):
        """Test edge conditions that read from graph state."""

        class IncrementNode(Node):
            async def process(self, context):
                counter = await context.graph_state.get('counter', 0)
                await context.graph_state.set('counter', counter + 1)
                return {'counter': counter + 1}

        class CheckNode(Node):
            async def process(self, context):
                counter = await context.graph_state.get('counter', 0)
                return {'should_continue': counter < 3, 'counter': counter}

        increment = IncrementNode()
        check = CheckNode()

        increment.goto(check)
        check.on(should_continue=True) >> increment

        graph = Graph(start=increment, initial_state={'counter': 0})
        await graph.run()

        # Should loop until counter reaches 3
        assert await graph.get_state('counter') == 3
