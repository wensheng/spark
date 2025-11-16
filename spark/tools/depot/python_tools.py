import ast
from typing import Any
import importlib

from spark.tools.types import BaseTool, ToolSpec

ALLOWED_BUILTIN_MODULES = [
    'math',
    'random',
    'datetime',
    'string',
    're',
    'json',
    'itertools',
    'functools',
    'operator',
    'collections',
    "random",
    "re",
    "stat",
    "statistics",
    "time",
    "unicodedata",
]
ALLOWED_THIRD_PARTY_PACKAGES = [
    # Add any third-party packages that are safe to use here
]

# global registry of python tools
PYTHON_TOOLS = {}


def get_python_tool(name: str):
    """Get a registered Python tool by name.

    Args:
        name: Name of the tool.

    Returns:
        The registered Python tool.

    Raises:
        KeyError: If no tool with the given name is registered.
    """
    if name not in PYTHON_TOOLS:
        raise KeyError(f"Python tool '{name}' is not registered.")
    return PYTHON_TOOLS[name]


class UnsafePythonTool(BaseTool):
    """
    A tool that executes Python code in a restricted environment using RestrictedPython.

    The code can only have one function definition.
    The code can have imports (no import ... from), but only from a predefined whitelist of safe modules.
    The code must have both argument types and return type annotations.

    """

    def __init__(self, code: str) -> None:
        super().__init__()
        self._tool_type = "python"
        self._code = code
        self._load_code()

    def _load_code(self) -> None:
        """Parse and validate the Python code."""
        tree = ast.parse(self._code)

        # Validate imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name not in ALLOWED_BUILTIN_MODULES and alias.name not in ALLOWED_THIRD_PARTY_PACKAGES:
                        raise ValueError(f"Import of module '{alias.name}' is not allowed.")
                    # Just validate the module can be imported
                    importlib.import_module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                raise ValueError(f"Import from '{node.module}' is not allowed.")

        # Validate that there is only one function definition
        func_defs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        if len(func_defs) != 1:
            raise ValueError("The code must contain exactly one function definition.")
        if not func_defs[0].name.isidentifier():
            raise ValueError(f"Function name '{func_defs[0].name}' is not a valid identifier.")
        if func_defs[0].name in PYTHON_TOOLS:
            raise ValueError(f"Function name '{func_defs[0].name}' is already registered as a tool.")

        # Create a dedicated namespace for this tool
        # This ensures imports and the function are in the same namespace
        tool_namespace = {}

        # Execute the code in the tool's namespace
        # Using tool_namespace as both globals and locals ensures the function
        # can access the imported modules
        exec(self._code, tool_namespace, tool_namespace)

        # Extract and register the function
        self._func_name = func_defs[0].name
        PYTHON_TOOLS[self._func_name] = tool_namespace[self._func_name]

    @property
    def tool_name(self) -> str:
        return self._func_name

    @property
    def tool_type(self) -> str:
        return self._tool_type

    @property
    def tool_spec(self) -> ToolSpec:
        return {
            "name": self._func_name,
            "description": "A Python tool executed in a restricted environment.",
            "parameters": {},
            "response_schema": {},
        }

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the tool with the given arguments."""
        return PYTHON_TOOLS[self._func_name](*args, **kwargs)
