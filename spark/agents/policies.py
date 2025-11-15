"""Agent-level budget and human policy helpers."""

from __future__ import annotations

import time
from typing import Any, Optional

from pydantic import BaseModel, Field

from spark.agents.cost_tracker import CallCost


class AgentBudgetExceededError(RuntimeError):
    """Raised when an agent exhausts its configured budget."""


class AgentBudgetConfig(BaseModel):
    """Configuration for agent runtime budgets."""

    max_total_cost: float | None = Field(default=None, description="Maximum cumulative cost in USD.")
    max_total_tokens: int | None = Field(default=None, description="Maximum total tokens (input + output).")
    max_input_tokens: int | None = Field(default=None, description="Maximum input tokens.")
    max_output_tokens: int | None = Field(default=None, description="Maximum output tokens.")
    max_llm_calls: int | None = Field(default=None, description="Maximum LLM API calls.")
    max_runtime_seconds: float | None = Field(default=None, description="Maximum runtime in seconds per run.")


class AgentBudgetManager:
    """Tracks runtime budgets for an agent run."""

    def __init__(self, config: AgentBudgetConfig) -> None:
        self.config = config
        self._start_time: float | None = None
        self._llm_calls = 0
        self._total_cost = 0.0
        self._input_tokens = 0
        self._output_tokens = 0

    def start_run(self) -> None:
        if self._start_time is None:
            self._start_time = time.perf_counter()

    def register_llm_call(self) -> None:
        self._llm_calls += 1
        if self.config.max_llm_calls is not None and self._llm_calls > self.config.max_llm_calls:
            raise AgentBudgetExceededError(
                f"LLM call budget exceeded ({self._llm_calls} > {self.config.max_llm_calls})"
            )

    def handle_cost_event(self, call: CallCost, namespace: str | None = None) -> None:
        self._input_tokens += call.input_tokens
        self._output_tokens += call.output_tokens
        self._total_cost += call.total_cost
        total_tokens = self._input_tokens + self._output_tokens

        if self.config.max_total_cost is not None and self._total_cost > self.config.max_total_cost:
            raise AgentBudgetExceededError(
                f"Cost budget exceeded (${self._total_cost:.4f} > ${self.config.max_total_cost:.4f})"
            )
        if self.config.max_total_tokens is not None and total_tokens > self.config.max_total_tokens:
            raise AgentBudgetExceededError(
                f"Token budget exceeded ({total_tokens} > {self.config.max_total_tokens})"
            )
        if self.config.max_input_tokens is not None and self._input_tokens > self.config.max_input_tokens:
            raise AgentBudgetExceededError(
                f"Input token budget exceeded ({self._input_tokens} > {self.config.max_input_tokens})"
            )
        if self.config.max_output_tokens is not None and self._output_tokens > self.config.max_output_tokens:
            raise AgentBudgetExceededError(
                f"Output token budget exceeded ({self._output_tokens} > {self.config.max_output_tokens})"
            )

    def check_runtime(self) -> None:
        if self.config.max_runtime_seconds is None or self._start_time is None:
            return
        runtime = time.perf_counter() - self._start_time
        if runtime > self.config.max_runtime_seconds:
            raise AgentBudgetExceededError(
                f"Runtime budget exceeded ({runtime:.2f}s > {self.config.max_runtime_seconds}s)"
            )


class HumanApprovalRequired(RuntimeError):
    """Raised when a policy requires human confirmation."""


class AgentStoppedError(RuntimeError):
    """Raised when a stop signal pauses the agent."""


class HumanInteractionPolicy(BaseModel):
    """Policy controls for human-in-the-loop guardrails."""

    require_tool_approval: bool = Field(default=False, description="Require approval before tool execution.")
    auto_approved_tools: list[str] = Field(default_factory=list, description="Tools that bypass approval.")
    stop_token: str | None = Field(default=None, description="Global token used to pause the agent.")
    pause_on_stop_signal: bool = Field(default=True, description="Pause execution when stop token is triggered.")
    metadata: dict[str, str] = Field(default_factory=dict, description="Arbitrary metadata about the policy.")


class HumanPolicyManager:
    """Lightweight runtime manager for human interaction policies."""

    _stop_signals: dict[str, dict[str, Any]] = {}

    def __init__(self, policy: HumanInteractionPolicy | None = None) -> None:
        self.policy = policy or HumanInteractionPolicy()

    @classmethod
    def issue_stop_signal(cls, token: str, reason: str | None = None) -> None:
        cls._stop_signals[token] = {'reason': reason or 'operator_stop', 'timestamp': time.time()}

    @classmethod
    def clear_stop_signal(cls, token: str) -> None:
        cls._stop_signals.pop(token, None)

    def ensure_not_stopped(self) -> None:
        token = self.policy.stop_token
        if not token or not self.policy.pause_on_stop_signal:
            return
        if token in self._stop_signals:
            reason = self._stop_signals[token]['reason']
            raise AgentStoppedError(f"Agent paused: {reason}")

    def ensure_tool_allowed(self, tool_name: str) -> None:
        if not self.policy.require_tool_approval:
            return
        if tool_name in self.policy.auto_approved_tools:
            return
        raise HumanApprovalRequired(f"Tool '{tool_name}' requires human approval before execution.")

