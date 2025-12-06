"""
An simple basic node
A node is a processing unit in Spark. Its class should inherit from Node (from spark.nodes import Node).
What a node does is defined in the its `process` method.  A node must have a process method, it can be either sync or async.
The process method takes an optional context argument, and returns either None or a dict.
"""

from spark.utils import arun
from spark.nodes import Node


class SimpleNode(Node):
    def process(self):
        print("Hello from spark node")


if __name__ == "__main__":
    node = SimpleNode()
    arun(node.run())
