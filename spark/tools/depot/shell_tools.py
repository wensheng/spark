"""
Shell tools for executing shell commands.
"""

import os
import platform

# import shutil
import subprocess
from typing import Any

from spark.tools.types import BaseTool, ToolSpec

# no window flag on Windows
CREATE_NO_WINDOW = 0x08000000


def get_shell_from_env():
    """Tries to guess the shell from environment variables."""

    # Check for Windows
    if platform.system() == "Windows":
        # if os.environ.get("PSModulePath"):
        #     return "powershell.exe"
        if os.environ.get("COMSPEC"):
            return os.environ.get("COMSPEC")
        else:
            return "Unknown Windows shell"

    # Check for POSIX (Linux/macOS)
    else:
        if os.environ.get("SHELL"):
            return
        else:
            return "Unknown POSIX shell"


class ShellTool(BaseTool):
    """
    A tool that executes commands in a shell

    """

    def __init__(
        self, name: str, description: str, command_template: str, parameters: dict[str, dict[str, Any]] | None = None
    ) -> None:
        """Initialize the shell tool with a command template."""
        super().__init__()
        self._tool_type = "shell"
        self._name = name
        self._description = description
        self._command_template = command_template
        self._parameters = parameters or {}

    @property
    def tool_name(self) -> str:
        return self._name

    @property
    def tool_type(self) -> str:
        return self._tool_type

    @property
    def tool_spec(self) -> ToolSpec:
        # Build input schema from parameters
        input_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

        for param_name, param_info in self._parameters.items():
            input_schema["properties"][param_name] = {
                "type": param_info.get("type", "string"),
                "description": param_info.get("description", ""),
            }
            if param_info.get("required", True):
                input_schema["required"].append(param_name)

        return {
            "name": self._name,
            "description": self._description,
            "parameters": input_schema,
            "response_schema": {},
        }

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the tool with the given arguments."""
        # Extract values in the order they appear in parameters
        format_args = []
        for param_name in self._parameters.keys():
            if param_name not in kwargs:
                raise ValueError(f"Missing required parameter: {param_name}")
            format_args.append(kwargs[param_name])

        # If no parameters defined, fall back to using args
        if not self._parameters and not args:
            raise ValueError("No command provided to execute.")

        if self._parameters:
            command = self._command_template.format(*format_args)
        else:
            command = self._command_template.format(*args)

        if platform.system() == "Windows":
            result = subprocess.run(command, shell=True, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        else:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
