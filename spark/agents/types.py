"""
State of the agent.
"""

from collections import deque
from typing import Any, Optional, TypedDict

from spark.nodes.types import NodeState


class ToolTrace(TypedDict):
    """Record of a single tool execution.

    Attributes:
        tool_name: Name of the tool that was executed
        tool_use_id: Unique identifier for this tool invocation
        input_params: Input parameters passed to the tool
        output: Result returned by the tool
        start_time: Unix timestamp when execution started
        end_time: Unix timestamp when execution completed
        duration_ms: Execution duration in milliseconds
        error: Error message if execution failed, None otherwise
    """

    tool_name: str
    tool_use_id: str
    input_params: dict[str, Any]
    output: Any
    start_time: float
    end_time: float
    duration_ms: float
    error: Optional[str]


class AgentState(NodeState):
    """State of the agent.

    Attributes:
        messages: Conversation history with the model
        tool_traces: History of all tool executions in this agent's session
        last_result: The last result produced by the agent
        last_error: The last error encountered, if any
        last_output: The last structured output from the agent (for JSON mode)
    """

    messages: list[dict[str, Any]]
    tool_traces: list[ToolTrace]
    last_result: Any
    last_error: str | None
    last_output: Any


def default_agent_state(**kwargs) -> AgentState:
    """Create a default agent state."""
    state: AgentState = AgentState(
        context_snapshot=None,
        processing=False,
        pending_inputs=deque(),
        process_count=0,
        messages=[],
        tool_traces=[],
        last_result=None,
        last_error=None,
        last_output=None,
    )
    state.update(kwargs)  # type: ignore
    return state
