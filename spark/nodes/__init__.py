"""
Core components of the Spark framework.
"""

from spark.nodes.types import ExecutionContext, NodeState, default_node_state
from spark.nodes.base import BaseNode, EdgeCondition
from spark.nodes.nodes import Node

__all__ = [
    "BaseNode",
    "EdgeCondition",
    "ExecutionContext",
    "Node",
    "NodeState",
    "default_node_state",
]
