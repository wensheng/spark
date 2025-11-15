"""Agent module for Spark framework."""

from spark.agents.agent import Agent, AgentError, ToolExecutionError, TemplateRenderError, ModelError, ConfigurationError
from spark.agents.config import AgentConfig
from spark.agents.memory import MemoryManager, MemoryConfig, MemoryPolicyType
from spark.agents.strategies import (
    ReasoningStrategy,
    NoOpStrategy,
    ReActStrategy,
    ChainOfThoughtStrategy,
    PlanAndSolveStrategy,
    StrategyPlan,
    StrategyPlanStep,
)
from spark.agents.types import AgentState, ToolTrace
from spark.agents.cost_tracker import CostTracker, CallCost, CostStats
from spark.agents.policies import (
    AgentBudgetConfig,
    AgentBudgetManager,
    AgentBudgetExceededError,
    HumanInteractionPolicy,
    HumanPolicyManager,
    HumanApprovalRequired,
    AgentStoppedError,
)

__all__ = [
    # Agent classes
    'Agent',
    'AgentError',
    'ToolExecutionError',
    'TemplateRenderError',
    'ModelError',
    'ConfigurationError',
    # Configuration
    'AgentConfig',
    # Memory
    'MemoryManager',
    'MemoryConfig',
    'MemoryPolicyType',
    # Strategies
    'ReasoningStrategy',
    'NoOpStrategy',
    'ReActStrategy',
    'ChainOfThoughtStrategy',
    'PlanAndSolveStrategy',
    'StrategyPlan',
    'StrategyPlanStep',
    # Cost Tracking
    'CostTracker',
    'CallCost',
    'CostStats',
    # Policies
    'AgentBudgetConfig',
    'AgentBudgetManager',
    'AgentBudgetExceededError',
    'HumanInteractionPolicy',
    'HumanPolicyManager',
    'HumanApprovalRequired',
    'AgentStoppedError',
    # Types
    'AgentState',
    'ToolTrace',
]
