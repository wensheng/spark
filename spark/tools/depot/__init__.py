"""Spark Tool Depot: A collection of tools that can be used by Spark agents."""
from spark.tools.depot.python_tools import UnsafePythonTool
from spark.tools.depot.shell_tools import ShellTool

__all__ = ['UnsafePythonTool', 'ShellTool']
