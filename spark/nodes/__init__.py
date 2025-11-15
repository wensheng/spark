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
from spark.nodes.nodes import Node
from spark.nodes.channels import ChannelMessage
from spark.nodes.rpc import RpcNode, MethodNotFoundError, InvalidParamsError
from spark.nodes.rpc_client import RemoteRpcProxyNode

__all__ = [
    "BaseNode",
    "ChannelMessage",
    "ConditionLibrary",
    "EdgeCondition",
    "ExecutionContext",
    "InvalidParamsError",
    "MethodNotFoundError",
    "Node",
    "NodeState",
    "RpcNode",
    "RemoteRpcProxyNode",
    "default_node_state",
    "when_failure",
    "when_human_approved",
    "when_success",
    "when_threshold",
]
