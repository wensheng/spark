"""
Reasoning strategies for agents.

This module provides different reasoning patterns that agents can use to structure
their thinking and tool-calling behavior. Strategies are pluggable and allow agents
to follow different patterns like ReAct, Plan-and-Solve, Chain-of-Thought, etc.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class ReasoningStrategy(ABC):
    """Base class for reasoning strategies.

    A reasoning strategy defines how an agent structures its thinking process
    and maintains history during multi-step reasoning with tool calls.
    """

    @abstractmethod
    async def process_step(
        self,
        parsed_output: Any,
        tool_result_blocks: list[dict[str, Any]],
        state: dict[str, Any],
        context: Optional[Any] = None
    ) -> None:
        """Process a reasoning step and update state.

        Args:
            parsed_output: The structured output from the model (e.g., ReAct step)
            tool_result_blocks: List of tool result ContentBlocks
            state: Agent state dictionary to update
            context: Optional execution context
        """
        pass

    @abstractmethod
    def should_continue(self, parsed_output: Any) -> bool:
        """Determine if reasoning should continue based on the output.

        Args:
            parsed_output: The structured output from the model

        Returns:
            True if reasoning should continue, False if complete
        """
        pass

    @abstractmethod
    def get_history(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Get the reasoning history from state.

        Args:
            state: Agent state dictionary

        Returns:
            List of reasoning steps/history
        """
        pass

    def initialize_state(self, state: dict[str, Any]) -> None:
        """Initialize strategy-specific state fields.

        Args:
            state: Agent state dictionary to initialize
        """
        # Default: ensure history exists
        if 'history' not in state:
            state['history'] = []


class NoOpStrategy(ReasoningStrategy):
    """No-operation strategy that performs no special reasoning structure.

    This is the default strategy for simple agents that don't need
    structured reasoning patterns.
    """

    async def process_step(
        self,
        parsed_output: Any,
        tool_result_blocks: list[dict[str, Any]],
        state: dict[str, Any],
        context: Optional[Any] = None
    ) -> None:
        """No-op: does nothing."""
        pass

    def should_continue(self, parsed_output: Any) -> bool:
        """Always returns False (no special continuation logic)."""
        # For NoOp, we rely on the standard tool_use stop_reason
        # This method is only called for JSON mode with embedded actions
        return False

    def get_history(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Returns empty history."""
        return []

    def initialize_state(self, state: dict[str, Any]) -> None:
        """No initialization needed."""
        pass


class ReActStrategy(ReasoningStrategy):
    """ReAct (Reasoning + Acting) strategy.

    Implements the ReAct pattern where the agent alternates between:
    1. Thought: Reasoning about what to do
    2. Action: Executing a tool
    3. Observation: Observing the tool result
    4. Repeat until final answer

    The structured output should have fields:
    - thought: The agent's reasoning
    - action: Tool name to call (or null for final answer)
    - action_input: Input for the tool
    - final_answer: The final answer (when action is null)
    """

    def __init__(self, verbose: bool = True):
        """Initialize ReAct strategy.

        Args:
            verbose: Whether to print reasoning steps
        """
        self.verbose = verbose

    async def process_step(
        self,
        parsed_output: Any,
        tool_result_blocks: list[dict[str, Any]],
        state: dict[str, Any],
        context: Optional[Any] = None
    ) -> None:
        """Process a ReAct step and add to history.

        Args:
            parsed_output: Dictionary with thought, action, action_input fields
            tool_result_blocks: List of tool result ContentBlocks
            state: Agent state dictionary to update
            context: Optional execution context
        """
        if not isinstance(parsed_output, dict):
            logger.debug("Parsed output is not a dict, skipping ReAct history: %s", type(parsed_output))
            return

        # Extract ReAct fields
        thought = parsed_output.get('thought', '')
        action = parsed_output.get('action')
        action_input = parsed_output.get('action_input')

        # Only process if we have an action (not final answer)
        if not action or action == 'null' or action is None:
            logger.debug("No action in parsed output, skipping ReAct step")
            return

        if action_input is None:
            logger.debug("No action_input in parsed output, skipping ReAct step")
            return

        # Extract observation from tool results
        observation = self._extract_observation(tool_result_blocks)

        # Build history step
        history_step = {
            'thought': thought,
            'action': action,
            'action_input': action_input,
            'observation': observation
        }

        # Add to history
        if 'history' not in state:
            state['history'] = []
        state['history'].append(history_step)

        # Print progress if verbose
        if self.verbose:
            step_num = len(state['history'])
            action_input_preview = str(action_input)[:40]
            print(f"📝 Step {step_num}: {action}({action_input_preview}...)")

        logger.debug(f"Added ReAct step {len(state['history'])} to history")

    def _extract_observation(self, tool_result_blocks: list[dict[str, Any]]) -> str:
        """Extract observation text from tool result blocks.

        Args:
            tool_result_blocks: List of ContentBlocks with toolResult

        Returns:
            Observation text from first tool result, or default message
        """
        if not tool_result_blocks:
            return 'No observation recorded'

        # Get first tool result
        first_result = tool_result_blocks[0]
        if 'toolResult' not in first_result:
            return 'No observation recorded'

        result_content = first_result['toolResult'].get('content', [])
        if not result_content or not isinstance(result_content, list):
            return 'No observation recorded'

        # Get text from first content block
        if result_content and isinstance(result_content[0], dict):
            return result_content[0].get('text', 'No observation recorded')

        return 'No observation recorded'

    def should_continue(self, parsed_output: Any) -> bool:
        """Check if ReAct reasoning should continue.

        Returns True if there's an action to execute (not a final answer).

        Args:
            parsed_output: Dictionary with ReAct fields

        Returns:
            True if reasoning should continue, False if complete
        """
        if not isinstance(parsed_output, dict):
            return False

        action = parsed_output.get('action')
        has_final_answer = parsed_output.get('final_answer') is not None

        # Continue if we have an action and no final answer
        if action and action != 'null' and action is not None and not has_final_answer:
            return True

        return False

    def get_history(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Get ReAct reasoning history.

        Args:
            state: Agent state dictionary

        Returns:
            List of ReAct steps with thought/action/observation
        """
        return state.get('history', [])

    def initialize_state(self, state: dict[str, Any]) -> None:
        """Initialize ReAct history in state.

        Args:
            state: Agent state dictionary to initialize
        """
        if 'history' not in state:
            state['history'] = []


class ChainOfThoughtStrategy(ReasoningStrategy):
    """Chain-of-Thought (CoT) strategy.

    Encourages step-by-step reasoning without necessarily calling tools.
    Useful for problems that benefit from breaking down the thinking process.

    Expected output structure:
    - steps: List of reasoning steps
    - answer: Final answer
    """

    async def process_step(
        self,
        parsed_output: Any,
        tool_result_blocks: list[dict[str, Any]],
        state: dict[str, Any],
        context: Optional[Any] = None
    ) -> None:
        """Process a CoT step and add to history.

        Args:
            parsed_output: Dictionary with steps and answer fields
            tool_result_blocks: List of tool result ContentBlocks (usually empty for CoT)
            state: Agent state dictionary to update
            context: Optional execution context
        """
        if not isinstance(parsed_output, dict):
            return

        # Extract CoT steps
        steps = parsed_output.get('steps', [])
        answer = parsed_output.get('answer')

        if not steps:
            return

        # Add to history
        if 'history' not in state:
            state['history'] = []

        history_step = {
            'steps': steps,
            'answer': answer
        }
        state['history'].append(history_step)

        logger.debug(f"Added CoT step with {len(steps)} reasoning steps")

    def should_continue(self, parsed_output: Any) -> bool:
        """CoT typically completes in one shot.

        Args:
            parsed_output: Dictionary with CoT fields

        Returns:
            False (CoT is typically single-shot)
        """
        # Chain-of-thought is typically single-shot
        # If there's no answer yet, we might continue
        if isinstance(parsed_output, dict):
            return parsed_output.get('answer') is None
        return False

    def get_history(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Get CoT reasoning history.

        Args:
            state: Agent state dictionary

        Returns:
            List of CoT reasoning steps
        """
        return state.get('history', [])
