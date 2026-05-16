"""Optional workflow orchestration API built on Spark actors."""

from spark.workflow.base import Workflow
from spark.workflow.graph_state import GraphState
from spark.node.base import BaseNode, Chain, Edge, EdgeCondition, Node, NodeConfig, NodeContext, RouteContext

WorkflowState = GraphState

__all__ = [
    "Workflow",
    "WorkflowState",
    "GraphState",
    "Node",
    "BaseNode",
    "Chain",
    "Edge",
    "EdgeCondition",
    "NodeConfig",
    "NodeContext",
    "RouteContext",
]
