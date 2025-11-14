"""
Core components of the Spark framework.
"""

from spark.nodes.types import ExecutionContext, NodeState, default_node_state
from spark.nodes.base import BaseNode, EdgeCondition
from spark.nodes.nodes import Node
from spark.nodes.channels import ChannelMessage
from spark.nodes.rpc import RpcNode, MethodNotFoundError, InvalidParamsError

__all__ = [
    "BaseNode",
    "ChannelMessage",
    "EdgeCondition",
    "ExecutionContext",
    "InvalidParamsError",
    "MethodNotFoundError",
    "Node",
    "NodeState",
    "RpcNode",
    "default_node_state",
]
