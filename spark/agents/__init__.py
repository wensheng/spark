"""Agent module for Spark framework."""

from spark.agents.agent import Agent, AgentError, ToolExecutionError, TemplateRenderError, ModelError, ConfigurationError
from spark.agents.config import AgentConfig
from spark.agents.memory import MemoryManager, MemoryConfig, MemoryPolicyType
from spark.agents.strategies import ReasoningStrategy, NoOpStrategy, ReActStrategy, ChainOfThoughtStrategy
from spark.agents.types import AgentState, ToolTrace

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
    # Types
    'AgentState',
    'ToolTrace',
]
