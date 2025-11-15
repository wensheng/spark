"""
Reasoning strategies for agents.

This module provides different reasoning patterns that agents can use to structure
their thinking and tool-calling behavior. Strategies are pluggable and allow agents
to follow different patterns like ReAct, Plan-and-Solve, Chain-of-Thought, etc.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import logging
import time

logger = logging.getLogger(__name__)


class StrategyPlanStatus(str, Enum):
    """Status values for strategy-managed plan steps."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class StrategyPlanStep:
    """Single plan step tracked by a reasoning strategy."""

    id: str
    description: str
    status: StrategyPlanStatus = StrategyPlanStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'description': self.description,
            'status': self.status.value,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'StrategyPlanStep':
        return cls(
            id=payload.get('id', ''),
            description=payload.get('description', ''),
            status=StrategyPlanStatus(payload.get('status', StrategyPlanStatus.PENDING.value)),
        )


@dataclass
class StrategyPlan:
    """A lightweight mission plan owned by a reasoning strategy."""

    name: str = "mission-plan"
    steps: list[StrategyPlanStep] = field(default_factory=list)

    def get_active_step(self) -> Optional[StrategyPlanStep]:
        for step in self.steps:
            if step.status == StrategyPlanStatus.IN_PROGRESS:
                return step
        return None

    def get_next_pending(self) -> Optional[StrategyPlanStep]:
        for step in self.steps:
            if step.status == StrategyPlanStatus.PENDING:
                return step
        return None

    def start(self) -> None:
        """Ensure the plan has an active step."""
        if self.get_active_step() is None:
            next_step = self.get_next_pending()
            if next_step:
                next_step.status = StrategyPlanStatus.IN_PROGRESS

    def mark_current_complete(self) -> Optional[StrategyPlanStep]:
        """Mark the current step complete and move to the next pending one."""
        active = self.get_active_step()
        if active:
            active.status = StrategyPlanStatus.COMPLETED
            next_step = self.get_next_pending()
            if next_step:
                next_step.status = StrategyPlanStatus.IN_PROGRESS
            return active
        return None

    def to_payload(self) -> dict[str, Any]:
        return {'name': self.name, 'steps': [step.to_dict() for step in self.steps]}

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> Optional['StrategyPlan']:
        if not payload:
            return None
        steps = [StrategyPlanStep.from_dict(step) for step in payload.get('steps', [])]
        return cls(name=payload.get('name', 'mission-plan'), steps=steps)

    def summarize(self) -> dict[str, Any]:
        total = len(self.steps)
        completed = len([s for s in self.steps if s.status == StrategyPlanStatus.COMPLETED])
        return {
            'name': self.name,
            'total_steps': total,
            'completed': completed,
            'remaining': total - completed,
        }


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

    plan_state_key = 'strategy_plan'
    plan_events_key = 'strategy_plan_events'

    def supports_planning(self) -> bool:
        """Return True if the strategy produces a structured plan."""
        return False

    async def generate_plan(self, context: Any | None = None) -> Optional[StrategyPlan]:
        """Generate a plan for the current mission (override in subclasses)."""
        return None

    async def update_plan(self, result: Any, state: dict[str, Any]) -> None:
        """Update plan progress after a reasoning step."""
        return None

    async def evaluate_progress(self, state: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Return a progress summary for telemetry."""
        plan = self._get_plan_from_state(state)
        return plan.summarize() if plan else None

    def _get_plan_from_state(self, state: dict[str, Any]) -> Optional[StrategyPlan]:
        payload = state.get(self.plan_state_key)
        return StrategyPlan.from_payload(payload) if payload else None

    def _save_plan_to_state(self, plan: StrategyPlan, state: dict[str, Any]) -> None:
        state[self.plan_state_key] = plan.to_payload()
    def save_plan_to_state(self, plan: StrategyPlan, state: dict[str, Any]) -> None:
        self._save_plan_to_state(plan, state)

    def _record_plan_event(self, state: dict[str, Any], event: str) -> None:
        events = state.setdefault(self.plan_events_key, [])
        events.append({'event': event, 'timestamp': time.time()})

    def has_plan(self, state: dict[str, Any]) -> bool:
        return self._get_plan_from_state(state) is not None

    def get_plan_payload(self, state: dict[str, Any]) -> Optional[dict[str, Any]]:
        plan = self._get_plan_from_state(state)
        return plan.to_payload() if plan else None


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


class PlanAndSolveStrategy(ReasoningStrategy):
    """Simple plan-first strategy that tracks declared steps."""

    def __init__(
        self,
        plan_steps: Optional[list[str]] = None,
        name: str = "plan-and-solve",
        auto_start: bool = True,
    ) -> None:
        self.plan_steps = plan_steps or [
            "Understand the request",
            "Draft an approach",
            "Validate and summarize findings",
        ]
        self.plan_name = name
        self.auto_start = auto_start

    def supports_planning(self) -> bool:
        return True

    async def generate_plan(self, context: Any | None = None) -> StrategyPlan:
        steps = [
            StrategyPlanStep(
                id=f"step-{idx + 1}",
                description=description,
                status=StrategyPlanStatus.PENDING,
            )
            for idx, description in enumerate(self.plan_steps)
        ]
        plan = StrategyPlan(name=self.plan_name, steps=steps)
        if self.auto_start:
            plan.start()
        return plan

    async def process_step(
        self,
        parsed_output: Any,
        tool_result_blocks: list[dict[str, Any]],
        state: dict[str, Any],
        context: Optional[Any] = None,
    ) -> None:
        """Plan strategy keeps lightweight history for templates."""
        history = state.setdefault('history', [])
        history.append(
            {
                'observation': tool_result_blocks[0] if tool_result_blocks else {},
                'parsed_output': parsed_output,
            }
        )

    async def update_plan(self, result: Any, state: dict[str, Any]) -> None:
        plan = self._get_plan_from_state(state)
        if not plan:
            return
        completed = plan.mark_current_complete()
        if completed:
            self._record_plan_event(state, f"completed:{completed.id}")
        else:
            plan.start()
        self._save_plan_to_state(plan, state)

    def should_continue(self, parsed_output: Any) -> bool:
        """Plan strategy relies on stop_reason rather than custom looping."""
        return False

    def get_history(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        plan = self._get_plan_from_state(state)
        if plan:
            return [step.to_dict() for step in plan.steps]
        return state.get('history', [])
