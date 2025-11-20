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
            return os.environ.get("SHELL")
        else:
            return "Unknown POSIX shell"


class ShellTool(BaseTool):
    """
    A tool that executes commands in a shell
    """

    def __init__(
        self,
        name: str = "shell_tool",
        description: str = "A Tool that executes shell commands",
        command_template: str | None = None,
        parameters: dict[str, dict[str, Any]] | None = None,
        timeout: int | None = None,
    ) -> None:
        """Initialize the shell tool with a command template."""
        super().__init__()
        self._tool_type = "shell"
        self._name = name
        self._description = description
        self._command_template = command_template
        self._parameters = parameters or {}
        self._timeout = timeout

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

        if (
            (not self._command_template and self._parameters)
            or
            (self._command_template and not self._parameters)
        ):  
            raise ValueError("You must provide both command_template and parameters or neither.")
        if not self._command_template and not self._parameters:
            input_schema["properties"]["command"] = {
                "type": "string",
                "description": "The shell command to execute",
            }
            input_schema["required"].append("command")
        else:  
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
            "response_schema": {
                "type": "object",
                "properties": {
                    "stdout": {"type": "string", "description": "Standard output of the command"},
                    "stderr": {"type": "string", "description": "Standard error of the command"},
                    "returncode": {"type": "integer", "description": "Return code of the command"},
                },
            },
        }

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the tool with the given arguments."""
        command = None

        if self._command_template and self._parameters:
            format_args = []
            for param_name in self._parameters.keys():
                if param_name not in kwargs:
                    raise ValueError(f"Missing required parameter: {param_name}")
                format_args.append(kwargs[param_name])
            command = self._command_template.format(*format_args)
        else:
            if "command" in kwargs and isinstance(kwargs["command"], str) and kwargs["command"].strip():
                command = kwargs["command"]
            elif args:
                if len(args) == 1:
                    command = str(args[0])
                else:
                    command = " ".join(str(a) for a in args)
            else:
                raise ValueError("No command provided to execute.")

        if platform.system() == "Windows":
            creationflag = CREATE_NO_WINDOW
        else:
            creationflag = 0
        result = subprocess.run(
            command,
            shell=True,
            encoding="utf-8",
            capture_output=True,
            text=True,
            timeout=self._timeout,
            creationflags=creationflag,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
