"""
Example: Using different reasoning strategies with agents.

This example demonstrates how to use pluggable reasoning strategies to structure
agent thinking patterns. Strategies include:
- NoOpStrategy: Simple agents without structured reasoning
- ReActStrategy: Reasoning + Acting pattern for iterative problem solving
- ChainOfThoughtStrategy: Step-by-step reasoning
- Custom strategies: Build your own reasoning patterns

Run:
    python examples/e009_reasoning_strategies.py
    # or
    python -m examples.e009_reasoning_strategies
"""
import math

from spark.agents import Agent, AgentConfig, ReActStrategy, ChainOfThoughtStrategy, NoOpStrategy
from spark.models.openai import OpenAIModel
from spark.tools.decorator import tool
from spark.nodes.types import NodeMessage
from spark.utils import arun


SAFE_GLOBALS = math.__dict__.copy()
SAFE_GLOBALS['__builtins__'] = {}


@tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression.
    functions inside math module such as sin, log, sqrt, etc., are available without 'math.' prefix.

    Args:
        expression: A Python mathematical expression (including functions from the math module) to evaluate

    Returns:
        The result of the calculation
    """
    try:
        result = eval(expression, SAFE_GLOBALS, {})
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def get_weather(city: str) -> str:
    """Get weather information for a city.

    Args:
        city: Name of the city

    Returns:
        Weather information (simulated)
    """
    # Simulated weather data
    weather_data = {
        "San Francisco": "Sunny, 72°F",
        "New York": "Cloudy, 65°F",
        "London": "Rainy, 58°F",
        "Tokyo": "Clear, 75°F",
    }
    return weather_data.get(city, f"Weather data not available for {city}")


# Example 1: Simple agent with NoOpStrategy (default)
async def example_no_strategy():
    """Example of a simple agent without structured reasoning."""
    print("\n" + "=" * 60)
    print("Example 1: NoOpStrategy (Default - Simple Agent)")
    print("=" * 60)

    # NoOpStrategy is used by default when no strategy is specified
    config = AgentConfig(
        model=OpenAIModel(model_id='gpt-5-mini'),
        name="SimpleAgent",
        system_prompt="You are a helpful assistant.",
        tools=[calculate],
        # reasoning_strategy=None  # Default is NoOpStrategy
    )

    agent = Agent(config=config)

    print(f"Strategy: {type(agent.reasoning_strategy).__name__}")
    print("Use case: Simple question-answering, straightforward tasks")
    answer = await agent.run("what is square root of 199")
    print(f"Sample response: {answer.content}")
    print('tool traces:', agent.state['tool_traces'])
    print("History tracking: None")
    print()


# Example 2: Agent with ReActStrategy
async def example_react_strategy():
    """Example of an agent using ReAct (Reasoning + Acting) pattern."""
    print("\n" + "=" * 60)
    print("Example 2: ReActStrategy (Reasoning + Acting)")
    print("=" * 60)

    config = AgentConfig(
        model=OpenAIModel(model_id='gpt-5-mini'),
        system_prompt="""You are an agent that uses the ReAct pattern.
For each step, provide:
- thought: Your reasoning about what to do
- action: The tool to use (or 'finish' when done)
- action_input: Input for the tool
- final_answer: The final answer (when action is 'finish')

Example format:
{
    "thought": "I need to find the weather for New York",
    "action": "get_weather",
    "action_input": "New York"
}

When you have the final answer:
{
    "thought": "I now have all the information",
    "action": "finish",
    "final_answer": "The weather in New York is..."
}
""",
        tools=[get_weather, calculate],
        output_mode='json',  # ReAct works best with structured output
        reasoning_strategy=ReActStrategy(verbose=True),  # Enable progress tracking
    )

    agent = Agent(config=config)

    print(f"Strategy: {type(agent.reasoning_strategy).__name__}")
    print("Use case: Complex multi-step problems requiring tool use")
    print("History tracking: Thought -> Action -> Observation chain")
    print("Verbose: Prints progress as agent reasons")
    answer = await agent.run('what is the value of Tokyo temperature squared')
    print('Answer:', answer.content)
    print('Tool traces', agent.get_tool_traces())
    print()

    # The agent will maintain history in state['history']
    # Each step contains: thought, action, action_input, observation
    print("Agent state includes structured history:")
    print("  - thought: Agent's reasoning")
    print("  - action: Tool name")
    print("  - action_input: Tool parameters")
    print("  - observation: Tool result")
    print()


# Example 3: Agent with ChainOfThoughtStrategy
def example_cot_strategy():
    """Example of an agent using Chain-of-Thought reasoning."""
    print("\n" + "=" * 60)
    print("Example 3: ChainOfThoughtStrategy (Step-by-step reasoning)")
    print("=" * 60)

    config = AgentConfig(
        model=OpenAIModel(model_id='gpt-5-mini'),
        name="CoTAgent",
        system_prompt="""You are an agent that thinks step-by-step.
Provide your reasoning as a series of steps, then give your final answer.

Output format:
{
    "steps": [
        "First, I need to...",
        "Then, I should...",
        "Finally, I can..."
    ],
    "answer": "The final answer is..."
}
""",
        output_mode='json',
        reasoning_strategy=ChainOfThoughtStrategy(),
    )

    agent = Agent(config=config)

    print(f"Strategy: {type(agent.reasoning_strategy).__name__}")
    print("Use case: Problems requiring clear reasoning steps")
    print("History tracking: Reasoning steps and answer")
    print()


# Example 4: Custom reasoning strategy
def example_custom_strategy():
    """Example of creating a custom reasoning strategy."""
    print("\n" + "=" * 60)
    print("Example 4: Custom Reasoning Strategy")
    print("=" * 60)

    from spark.agents.strategies import ReasoningStrategy

    class DebugStrategy(ReasoningStrategy):
        """Custom strategy that logs all outputs for debugging."""

        def __init__(self):
            self.step_count = 0

        async def process_step(self, parsed_output, tool_result_blocks, state, context=None):
            """Log each step for debugging."""
            self.step_count += 1
            if 'debug_log' not in state:
                state['debug_log'] = []

            state['debug_log'].append({
                'step': self.step_count,
                'output': parsed_output,
                'tool_results': len(tool_result_blocks)
            })

            print(f"[DEBUG] Step {self.step_count}: {parsed_output}")

        def should_continue(self, parsed_output):
            """Continue if output indicates more work."""
            # Simple logic: stop if output has 'done' field
            if isinstance(parsed_output, dict):
                return not parsed_output.get('done', False)
            return False

        def get_history(self, state):
            """Return debug log as history."""
            return state.get('debug_log', [])

    config = AgentConfig(
        model=OpenAIModel(model_id='gpt-5-mini'),
        name="DebugAgent",
        reasoning_strategy=DebugStrategy(),
    )

    agent = Agent(config=config)

    print(f"Strategy: {type(agent.reasoning_strategy).__name__}")
    print("Use case: Debugging, custom reasoning patterns")
    print("Features: Custom state management, logging, continuation logic")
    print()


# Example 5: Switching strategies dynamically
def example_strategy_comparison():
    """Compare different strategies for the same task."""
    print("\n" + "=" * 60)
    print("Example 5: Strategy Comparison")
    print("=" * 60)

    print("\nSame agent, different strategies:")
    print()

    strategies = [
        ("NoOp", NoOpStrategy()),
        ("ReAct", ReActStrategy(verbose=False)),
        ("CoT", ChainOfThoughtStrategy()),
    ]

    for name, strategy in strategies:
        config = AgentConfig(
            model=OpenAIModel(model_id='gpt-5-mini'),
            name=f"Agent-{name}",
            reasoning_strategy=strategy,
        )
        agent = Agent(config=config)

        print(f"  • {name:10s} -> {type(agent.reasoning_strategy).__name__}")

    print()
    print("Benefits of strategy pattern:")
    print("  ✓ Pluggable reasoning patterns")
    print("  ✓ Easy to switch between strategies")
    print("  ✓ Extend with custom strategies")
    print("  ✓ No changes to agent code")
    print()


# Example 6: When to use each strategy
def example_strategy_guidelines():
    """Guidelines for choosing the right strategy."""
    print("\n" + "=" * 60)
    print("Example 6: Strategy Selection Guide")
    print("=" * 60)

    guidelines = [
        {
            'strategy': 'NoOpStrategy',
            'use_when': [
                'Simple question-answering',
                'No tool calling required',
                'Straightforward single-step tasks',
            ],
            'output_mode': 'text or json',
        },
        {
            'strategy': 'ReActStrategy',
            'use_when': [
                'Multi-step problem solving',
                'Requires tool calling',
                'Need to see reasoning process',
                'Complex tasks with iterations',
            ],
            'output_mode': 'json (structured output)',
        },
        {
            'strategy': 'ChainOfThoughtStrategy',
            'use_when': [
                'Mathematical reasoning',
                'Logic puzzles',
                'Need step-by-step explanation',
                'Educational contexts',
            ],
            'output_mode': 'json (structured steps)',
        },
        {
            'strategy': 'Custom Strategy',
            'use_when': [
                'Specific domain requirements',
                'Custom reasoning patterns',
                'Special logging/debugging needs',
                'Research and experimentation',
            ],
            'output_mode': 'any',
        },
    ]

    for guide in guidelines:
        print(f"\n{guide['strategy']}:")
        print(f"  Output mode: {guide['output_mode']}")
        print(f"  Use when:")
        for use_case in guide['use_when']:
            print(f"    • {use_case}")

    print()


async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("SPARK AGENT REASONING STRATEGIES")
    print("=" * 60)
    print()
    print("This example demonstrates different reasoning strategies")
    print("that can be plugged into Spark agents to structure their")
    print("thinking and problem-solving patterns.")
    print()

    # Run examples
    await example_no_strategy()
    await example_react_strategy()
    example_cot_strategy()
    example_custom_strategy()
    example_strategy_comparison()
    example_strategy_guidelines()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print()
    print("Key takeaways:")
    print("  1. Strategies are pluggable - easy to switch")
    print("  2. Each strategy suits different use cases")
    print("  3. ReAct best for multi-step tool-using tasks")
    print("  4. CoT best for step-by-step reasoning")
    print("  5. NoOp best for simple agents")
    print("  6. Custom strategies for special needs")
    print()
    print("Next steps:")
    print("  • Try different strategies with your agents")
    print("  • Create custom strategies for your domain")
    print("  • Combine strategies with templates for rich prompts")
    print()


if __name__ == "__main__":
    arun(main())
