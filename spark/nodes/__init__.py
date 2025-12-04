"""
Core components of the Spark framework.
"""

from spark.nodes.types import ExecutionContext, NodeState, default_node_state
from spark.nodes.base import BaseNode, EdgeCondition
from spark.nodes.conditions import (
    ConditionLibrary,
    when_failure,
    when_human_approved,
    when_success,
    when_threshold,
)
from spark.nodes.config import NodeConfig
from spark.nodes.nodes import Node
from spark.nodes.channels import ChannelMessage
from spark.nodes.rpc import RpcNode, MethodNotFoundError, InvalidParamsError
from spark.nodes.rpc_client import RemoteRpcProxyNode
from spark.nodes.policies import (
    CircuitBreakerPolicy,
    RateLimiterPolicy,
    RetryPolicy,
    TimeoutPolicy,
)

__all__ = [
    "BaseNode",
    "ChannelMessage",
    "ConditionLibrary",
    "EdgeCondition",
    "ExecutionContext",
    "InvalidParamsError",
    "MethodNotFoundError",
    "Node",
    "NodeConfig",
    "NodeState",
    "RpcNode",
    "RemoteRpcProxyNode",
    "default_node_state",
    "when_failure",
    "when_human_approved",
    "when_success",
    "when_threshold",
    "CircuitBreakerPolicy",
    "RateLimiterPolicy",
    "RetryPolicy",
    "TimeoutPolicy",
]
