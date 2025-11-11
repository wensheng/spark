"""
Example demonstrating graph state usage.

This example shows how multiple nodes can share and update global state
across the graph execution, useful for:
- Tracking progress across workflow steps
- Aggregating results from multiple nodes
- Coordinating behavior based on shared counters or flags
"""

from spark.nodes import Node
from spark.graphs import Graph
from spark.utils import arun


class InputNode(Node):
    """Node that accepts user input and initializes state."""

    async def process(self, context):
        print("\n=== Counter Loop Demo ===")
        print("This demo will increment a counter until it reaches the limit.\n")

        try:
            limit = int(input("Enter counter limit (default 5): ") or "5")
        except ValueError:
            limit = 5

        # Initialize graph state
        await context.graph_state.set('limit', limit)
        await context.graph_state.set('counter', 0)

        print(f"\nStarting counter with limit: {limit}\n")
        return {'ready': True}


class IncrementNode(Node):
    """Node that increments the counter in graph state."""

    async def process(self, context):
        # Read current counter from graph state
        counter = await context.graph_state.get('counter', 0)

        # Increment
        counter += 1
        await context.graph_state.set('counter', counter)

        print(f"Counter incremented to: {counter}")

        return {'counter': counter}


class CheckLimitNode(Node):
    """Node that checks if counter has reached the limit."""

    async def process(self, context):
        counter = await context.graph_state.get('counter', 0)
        limit = await context.graph_state.get('limit', 5)

        should_continue = counter < limit

        if should_continue:
            print(f"  → Counter {counter} < {limit}, continuing...\n")
        else:
            print(f"  → Counter {counter} reached limit {limit}, stopping!\n")

        return {'should_continue': should_continue}


class ResultNode(Node):
    """Node that displays final results from graph state."""

    async def process(self, context):
        counter = await context.graph_state.get('counter', 0)
        limit = await context.graph_state.get('limit', 0)

        print("=== Final Results ===")
        print(f"Final counter value: {counter}")
        print(f"Configured limit: {limit}")
        print(f"Loop iterations: {counter}")

        return {'final_counter': counter}


async def main():
    """Run the counter loop example."""

    # Create nodes
    input_node = InputNode()
    increment_node = IncrementNode()
    check_node = CheckLimitNode()
    result_node = ResultNode()

    # Define flow with loop
    input_node.goto(increment_node)
    increment_node.goto(check_node)
    check_node.on(should_continue=True) >> increment_node  # Loop back
    check_node.on(should_continue=False) >> result_node  # Exit loop

    # Create graph
    graph = Graph(start=input_node)

    # Run the graph
    result = await graph.run()

    # Access final state
    print("\n=== Graph State Snapshot ===")
    snapshot = graph.get_state_snapshot()
    for key, value in snapshot.items():
        print(f"{key}: {value}")

    print("\n✓ Demo complete!")


async def demo_result_aggregation():
    """Demo: Aggregating results from multiple nodes."""

    print("\n=== Result Aggregation Demo ===\n")

    class ProcessNode(Node):
        """Processes an item and adds result to shared list."""

        def __init__(self, item_name: str, **kwargs):
            super().__init__(**kwargs)
            self.item_name = item_name

        async def process(self, context):
            # Simulate processing
            result = f"Processed: {self.item_name}"
            print(f"  {result}")

            # Add to results list in graph state
            results = await context.graph_state.get('results', [])
            results.append(result)
            await context.graph_state.set('results', results)

            return {'processed': self.item_name}

    class SummaryNode(Node):
        """Summarizes all results."""

        async def process(self, context):
            results = await context.graph_state.get('results', [])
            print(f"\n=== Summary ===")
            print(f"Processed {len(results)} items:")
            for i, result in enumerate(results, 1):
                print(f"  {i}. {result}")
            return {'total': len(results)}

    # Create a chain of processing nodes
    node1 = ProcessNode("Task A")
    node2 = ProcessNode("Task B")
    node3 = ProcessNode("Task C")
    summary = SummaryNode()

    node1.goto(node2)
    node2.goto(node3)
    node3.goto(summary)

    graph = Graph(start=node1, initial_state={'results': []})
    await graph.run()

    print("\n✓ Aggregation demo complete!\n")


async def demo_transaction_usage():
    """Demo: Using transactions for atomic updates."""

    print("\n=== Transaction Demo ===\n")

    class AtomicUpdateNode(Node):
        """Updates multiple related values atomically."""

        async def process(self, context):
            print("Performing atomic update of x and y...")

            # Use transaction for atomic multi-value update
            async with context.graph_state.transaction() as state:
                x = state.get('x', 0)
                y = state.get('y', 0)

                # Both values updated atomically
                state['x'] = x + 1
                state['y'] = y + 1

            print(f"  x = {x + 1}, y = {y + 1}")
            return {'updated': True}

    node = AtomicUpdateNode()
    graph = Graph(start=node, initial_state={'x': 0, 'y': 0})

    # Run multiple times
    for i in range(3):
        print(f"\nIteration {i + 1}:")
        await graph.run()

    snapshot = graph.get_state_snapshot()
    print(f"\nFinal state: x={snapshot['x']}, y={snapshot['y']}")
    print("✓ Transaction demo complete!\n")


if __name__ == "__main__":
    # Run main counter demo
    arun(main())

    # Uncomment to run additional demos:
    # arun(demo_result_aggregation())
    # arun(demo_transaction_usage())
