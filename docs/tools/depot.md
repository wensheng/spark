---
title: Tool Depot
parent: Tools
nav_order: 3
---
# Tool Depot
---

The tool depot provides production-ready tools for common operations. These tools are immediately usable but come with important security considerations that must be understood before deployment.

**Available tools**:
- **UnsafePythonTool**: Execute arbitrary Python code
- **ShellTool**: Execute shell commands

**WARNING**: Both tools in the depot involve code execution and should only be used in secure, sandboxed environments with proper access controls.

## UnsafePythonTool

### Overview

The `UnsafePythonTool` allows dynamic execution of Python code. This is useful for building agents that can write and execute code to solve problems, perform calculations, or manipulate data.

### Location

```python
from spark.tools.depot import UnsafePythonTool
```

### Basic Usage

```python
from spark.tools.depot import UnsafePythonTool
from spark.agents import Agent, AgentConfig

# Create tool instance
python_tool = UnsafePythonTool()

# Use with agent
config = AgentConfig(
    model=model,
    tools=[python_tool],
    system_prompt="You can execute Python code to solve problems."
)
agent = Agent(config=config)

# Agent can now execute Python code
result = await agent.run("Calculate the sum of squares from 1 to 100")
```

### API Reference

#### Class: UnsafePythonTool

**Signature**:
```python
class UnsafePythonTool(BaseTool):
    def __init__(
        self,
        timeout: float = 30.0,
        max_output_length: int = 10000,
        allowed_imports: Optional[list[str]] = None,
        restricted_builtins: bool = True
    ):
        """Initialize Python execution tool.

        Args:
            timeout: Maximum execution time in seconds (default: 30.0)
            max_output_length: Maximum length of captured output (default: 10000)
            allowed_imports: List of allowed import modules (None = all allowed)
            restricted_builtins: Whether to restrict dangerous builtins (default: True)
        """
```

**Attributes**:
- `tool_name`: `"execute_python"`
- `tool_type`: `"python"`

**Methods**:

##### execute_python()

Execute Python code and return the result.

**Signature**:
```python
async def execute_python(
    code: str,
    globals_dict: Optional[dict] = None,
    locals_dict: Optional[dict] = None
) -> dict
```

**Parameters**:
- `code`: Python code to execute
- `globals_dict`: Optional global namespace (default: clean namespace)
- `locals_dict`: Optional local namespace (default: clean namespace)

**Returns**:
Dictionary containing:
```python
{
    "success": bool,           # Whether execution succeeded
    "result": Any,             # Result of execution (if success=True)
    "output": str,             # Captured stdout/stderr
    "error": Optional[str],    # Error message (if success=False)
    "execution_time": float    # Execution time in seconds
}
```

**Raises**:
- `TimeoutError`: If execution exceeds timeout
- `SecurityError`: If restricted operations are attempted

**Example**:
```python
tool = UnsafePythonTool()

# Execute simple calculation
result = await tool.execute_python("""
x = 10
y = 20
result = x + y
print(f"Sum is {result}")
result
""")

print(f"Success: {result['success']}")
print(f"Result: {result['result']}")  # 30
print(f"Output: {result['output']}")  # "Sum is 30\n"
print(f"Time: {result['execution_time']:.3f}s")
```

### Configuration Options

#### Timeout Control

Set execution timeout to prevent runaway code:

```python
# Short timeout for simple operations
tool = UnsafePythonTool(timeout=5.0)

# Longer timeout for complex operations
tool = UnsafePythonTool(timeout=120.0)
```

#### Output Length Limiting

Limit captured output to prevent memory issues:

```python
# Default: 10KB of output
tool = UnsafePythonTool(max_output_length=10000)

# Larger output buffer
tool = UnsafePythonTool(max_output_length=100000)
```

#### Import Restrictions

Restrict which modules can be imported:

```python
# Allow only specific modules
tool = UnsafePythonTool(
    allowed_imports=['math', 'json', 'datetime', 're']
)

# Attempting to import other modules will fail
code = "import os; os.system('ls')"  # Will raise SecurityError
```

#### Builtin Restrictions

Restrict dangerous builtins:

```python
# Enable restrictions (default)
tool = UnsafePythonTool(restricted_builtins=True)
# Blocks: eval, exec, compile, __import__, open, input

# Disable restrictions (use with caution)
tool = UnsafePythonTool(restricted_builtins=False)
```

### Security Considerations

**CRITICAL SECURITY WARNINGS**:

1. **Arbitrary Code Execution**: This tool can execute any Python code provided to it
2. **System Access**: Code can access files, network, and system resources
3. **Data Exfiltration**: Code can read and transmit sensitive data
4. **Resource Consumption**: Code can consume unlimited CPU, memory, or disk
5. **Privilege Escalation**: Code runs with the same privileges as the Python process

### Safe Usage Patterns

#### Sandboxed Environment

**REQUIRED**: Always run in a sandboxed environment:

```python
# Use Docker container with limited resources
# docker run --rm -it \
#   --memory="512m" \
#   --cpus="1.0" \
#   --network=none \
#   --read-only \
#   --tmpfs /tmp \
#   python-sandbox

from spark.tools.depot import UnsafePythonTool

tool = UnsafePythonTool(
    timeout=10.0,
    allowed_imports=['math', 'json', 'datetime'],
    restricted_builtins=True
)
```

#### User Isolation

Isolate users and their code execution:

```python
from spark.tools.depot import UnsafePythonTool
import hashlib

def create_user_tool(user_id: str) -> UnsafePythonTool:
    """Create isolated Python tool for user."""

    # Create user-specific namespace
    user_namespace = {
        'user_id': user_id,
        'user_data': load_user_data(user_id)
    }

    tool = UnsafePythonTool(
        timeout=30.0,
        allowed_imports=['math', 'json', 're'],
        restricted_builtins=True
    )

    # Wrap execute method to inject namespace
    original_execute = tool.execute_python

    async def wrapped_execute(code: str) -> dict:
        return await original_execute(
            code,
            globals_dict=user_namespace.copy()
        )

    tool.execute_python = wrapped_execute
    return tool
```

#### Code Validation

Validate code before execution:

```python
from spark.tools.depot import UnsafePythonTool
import ast

class ValidatedPythonTool(UnsafePythonTool):
    """Python tool with code validation."""

    FORBIDDEN_NAMES = {
        'eval', 'exec', 'compile', '__import__',
        'open', 'input', 'file', 'execfile'
    }

    def validate_code(self, code: str) -> tuple[bool, str]:
        """Validate code AST for forbidden operations."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

        for node in ast.walk(tree):
            # Check for forbidden names
            if isinstance(node, ast.Name):
                if node.id in self.FORBIDDEN_NAMES:
                    return False, f"Forbidden name: {node.id}"

            # Check for attribute access to dangerous modules
            if isinstance(node, ast.Attribute):
                if node.attr in {'system', 'popen', 'spawn'}:
                    return False, f"Forbidden attribute: {node.attr}"

        return True, ""

    async def execute_python(self, code: str, **kwargs) -> dict:
        """Execute with validation."""
        is_valid, error = self.validate_code(code)
        if not is_valid:
            return {
                "success": False,
                "result": None,
                "output": "",
                "error": f"Validation failed: {error}",
                "execution_time": 0.0
            }

        return await super().execute_python(code, **kwargs)

# Use validated tool
tool = ValidatedPythonTool(timeout=10.0)
```

#### Audit Logging

Log all code execution for security audits:

```python
from spark.tools.depot import UnsafePythonTool
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AuditedPythonTool(UnsafePythonTool):
    """Python tool with audit logging."""

    def __init__(self, user_id: str, **kwargs):
        super().__init__(**kwargs)
        self.user_id = user_id

    async def execute_python(self, code: str, **kwargs) -> dict:
        """Execute with audit logging."""
        execution_id = generate_id()

        # Log execution start
        logger.info(
            "Python execution started",
            extra={
                "execution_id": execution_id,
                "user_id": self.user_id,
                "timestamp": datetime.now().isoformat(),
                "code_hash": hashlib.sha256(code.encode()).hexdigest()
            }
        )

        # Execute
        result = await super().execute_python(code, **kwargs)

        # Log execution result
        logger.info(
            "Python execution completed",
            extra={
                "execution_id": execution_id,
                "user_id": self.user_id,
                "success": result["success"],
                "execution_time": result["execution_time"],
                "had_output": len(result["output"]) > 0,
                "error": result.get("error")
            }
        )

        return result
```

### Use Cases

**Appropriate use cases**:
- Mathematical calculations and data analysis
- Data transformation and processing
- Algorithm prototyping and testing
- Interactive Python tutorials
- Code generation evaluation

**Inappropriate use cases**:
- Production environments without sandboxing
- User-facing applications without validation
- Systems with access to sensitive data
- Environments with relaxed security requirements

## ShellTool

### Overview

The `ShellTool` allows execution of shell commands. This is useful for system administration tasks, file operations, and integration with command-line tools.

### Location

```python
from spark.tools.depot import ShellTool
```

### Basic Usage

```python
from spark.tools.depot import ShellTool
from spark.agents import Agent, AgentConfig

# Create tool instance
shell_tool = ShellTool()

# Use with agent
config = AgentConfig(
    model=model,
    tools=[shell_tool],
    system_prompt="You can execute shell commands to manage the system."
)
agent = Agent(config=config)

# Agent can now execute shell commands
result = await agent.run("List all Python files in the current directory")
```

### API Reference

#### Class: ShellTool

**Signature**:
```python
class ShellTool(BaseTool):
    def __init__(
        self,
        timeout: float = 60.0,
        max_output_length: int = 50000,
        allowed_commands: Optional[list[str]] = None,
        working_directory: Optional[str] = None,
        environment: Optional[dict] = None
    ):
        """Initialize shell execution tool.

        Args:
            timeout: Maximum execution time in seconds (default: 60.0)
            max_output_length: Maximum length of captured output (default: 50000)
            allowed_commands: List of allowed command names (None = all allowed)
            working_directory: Working directory for command execution
            environment: Environment variables for command execution
        """
```

**Attributes**:
- `tool_name`: `"execute_shell"`
- `tool_type`: `"shell"`

**Methods**:

##### execute_shell()

Execute a shell command and return the result.

**Signature**:
```python
async def execute_shell(
    command: str,
    check_success: bool = False
) -> dict
```

**Parameters**:
- `command`: Shell command to execute
- `check_success`: If True, raise error on non-zero exit code (default: False)

**Returns**:
Dictionary containing:
```python
{
    "success": bool,           # Whether command executed successfully
    "stdout": str,             # Standard output
    "stderr": str,             # Standard error
    "exit_code": int,          # Process exit code
    "execution_time": float,   # Execution time in seconds
    "error": Optional[str]     # Error message (if applicable)
}
```

**Raises**:
- `TimeoutError`: If execution exceeds timeout
- `SecurityError`: If command is not allowed
- `CalledProcessError`: If check_success=True and exit code is non-zero

**Example**:
```python
tool = ShellTool()

# Execute command
result = await tool.execute_shell("ls -la /tmp")

print(f"Success: {result['success']}")
print(f"Exit code: {result['exit_code']}")
print(f"Output:\n{result['stdout']}")
print(f"Time: {result['execution_time']:.3f}s")
```

### Configuration Options

#### Command Restrictions

Restrict which commands can be executed:

```python
# Allow only specific commands
tool = ShellTool(
    allowed_commands=['ls', 'cat', 'grep', 'find', 'wc']
)

# Attempting to run other commands will fail
await tool.execute_shell("rm -rf /")  # Raises SecurityError
```

#### Working Directory

Set the working directory for command execution:

```python
# Execute in specific directory
tool = ShellTool(working_directory="/var/data")

# Commands run in /var/data
result = await tool.execute_shell("ls")  # Lists /var/data
```

#### Environment Variables

Provide custom environment variables:

```python
# Custom environment
tool = ShellTool(
    environment={
        'PATH': '/usr/local/bin:/usr/bin:/bin',
        'LC_ALL': 'en_US.UTF-8',
        'CUSTOM_VAR': 'value'
    }
)
```

### Security Considerations

**CRITICAL SECURITY WARNINGS**:

1. **Command Injection**: Vulnerable to shell injection attacks
2. **System Access**: Commands can access files, processes, and system resources
3. **Data Destruction**: Commands like `rm -rf` can delete data
4. **Network Access**: Commands can make network connections
5. **Privilege Escalation**: Commands run with process privileges

### Safe Usage Patterns

#### Command Whitelisting

**REQUIRED**: Always use command whitelisting:

```python
# Whitelist safe commands only
tool = ShellTool(
    allowed_commands=[
        'ls', 'cat', 'grep', 'find', 'wc', 'head', 'tail',
        'sort', 'uniq', 'cut', 'awk', 'sed'
    ],
    timeout=30.0
)
```

#### Input Validation

Validate and sanitize all inputs:

```python
import shlex
from spark.tools.depot import ShellTool

class ValidatedShellTool(ShellTool):
    """Shell tool with input validation."""

    FORBIDDEN_CHARS = {';', '|', '&', '$(', '`', '>', '<', '\n'}

    def validate_command(self, command: str) -> tuple[bool, str]:
        """Validate command for injection attempts."""

        # Check for forbidden characters
        for char in self.FORBIDDEN_CHARS:
            if char in command:
                return False, f"Forbidden character: {char}"

        # Parse command safely
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return False, f"Invalid command syntax: {e}"

        # Check if base command is allowed
        if self.allowed_commands and parts[0] not in self.allowed_commands:
            return False, f"Command not allowed: {parts[0]}"

        return True, ""

    async def execute_shell(self, command: str, **kwargs) -> dict:
        """Execute with validation."""
        is_valid, error = self.validate_command(command)
        if not is_valid:
            return {
                "success": False,
                "stdout": "",
                "stderr": error,
                "exit_code": -1,
                "execution_time": 0.0,
                "error": f"Validation failed: {error}"
            }

        return await super().execute_shell(command, **kwargs)

# Use validated tool
tool = ValidatedShellTool(
    allowed_commands=['ls', 'cat', 'grep'],
    timeout=10.0
)
```

#### Read-Only Operations

Limit to read-only commands:

```python
# Read-only command whitelist
READONLY_COMMANDS = [
    'ls', 'cat', 'head', 'tail', 'grep', 'find',
    'wc', 'sort', 'uniq', 'diff', 'file', 'stat'
]

tool = ShellTool(
    allowed_commands=READONLY_COMMANDS,
    working_directory="/data/readonly",
    timeout=30.0
)
```

#### Audit Logging

Log all command execution:

```python
from spark.tools.depot import ShellTool
import logging

logger = logging.getLogger(__name__)

class AuditedShellTool(ShellTool):
    """Shell tool with audit logging."""

    def __init__(self, user_id: str, **kwargs):
        super().__init__(**kwargs)
        self.user_id = user_id

    async def execute_shell(self, command: str, **kwargs) -> dict:
        """Execute with audit logging."""
        execution_id = generate_id()

        # Log command execution
        logger.warning(
            "Shell command executed",
            extra={
                "execution_id": execution_id,
                "user_id": self.user_id,
                "command": command,
                "working_dir": self.working_directory,
                "timestamp": datetime.now().isoformat()
            }
        )

        # Execute
        result = await super().execute_shell(command, **kwargs)

        # Log result
        logger.info(
            "Shell command completed",
            extra={
                "execution_id": execution_id,
                "exit_code": result["exit_code"],
                "execution_time": result["execution_time"],
                "had_stderr": len(result["stderr"]) > 0
            }
        )

        return result
```

### Use Cases

**Appropriate use cases**:
- File system queries (listing, searching)
- Log file analysis
- System monitoring and metrics
- Data processing with Unix tools
- Build and deployment scripts (in CI/CD)

**Inappropriate use cases**:
- User-facing applications without validation
- Systems requiring high security
- Environments with sensitive data
- Production systems without sandboxing

## Combining Depot Tools

### Multi-Tool Agent

Create agents with both Python and shell capabilities:

```python
from spark.tools.depot import UnsafePythonTool, ShellTool
from spark.agents import Agent, AgentConfig

# Create restricted tools
python_tool = UnsafePythonTool(
    timeout=30.0,
    allowed_imports=['math', 'json', 'datetime', 're'],
    restricted_builtins=True
)

shell_tool = ShellTool(
    allowed_commands=['ls', 'cat', 'grep', 'wc', 'head', 'tail'],
    timeout=30.0
)

# Create agent with both tools
config = AgentConfig(
    model=model,
    tools=[python_tool, shell_tool],
    system_prompt="""You can use Python code and shell commands to solve problems.
    Use Python for calculations and data processing.
    Use shell commands for file operations and system queries.
    """
)

agent = Agent(config=config)

# Agent can now use both tools
result = await agent.run(
    "Count the number of Python files and calculate their average size"
)
```

## Deployment Recommendations

### Development Environment

```python
# Development: More permissive for productivity
python_tool = UnsafePythonTool(
    timeout=60.0,
    max_output_length=100000,
    restricted_builtins=False  # Allow more freedom
)

shell_tool = ShellTool(
    timeout=60.0,
    allowed_commands=None  # Allow all commands
)
```

### Production Environment

```python
# Production: Strict restrictions for security
python_tool = UnsafePythonTool(
    timeout=10.0,
    max_output_length=10000,
    allowed_imports=['math', 'json', 'datetime', 're', 'collections'],
    restricted_builtins=True
)

shell_tool = ShellTool(
    timeout=10.0,
    allowed_commands=['ls', 'cat', 'grep', 'wc'],
    working_directory="/data/readonly"
)
```

### Sandboxed Environment

```bash
# Docker container with security restrictions
docker run --rm -it \
  --memory="512m" \
  --cpus="1.0" \
  --network=none \
  --read-only \
  --tmpfs /tmp \
  --security-opt=no-new-privileges \
  --cap-drop=ALL \
  spark-agent-sandbox
```

## Summary

The tool depot provides powerful but dangerous tools:

**UnsafePythonTool**:
- Execute arbitrary Python code
- Configure timeouts, output limits, import restrictions
- **MUST** use in sandboxed environment
- Validate all code before execution
- Audit all executions

**ShellTool**:
- Execute shell commands
- Configure command whitelist, working directory
- **MUST** validate inputs for injection
- Use read-only commands when possible
- Audit all command executions

**Security checklist**:
- [ ] Running in sandboxed/containerized environment
- [ ] Command/import whitelisting enabled
- [ ] Input validation implemented
- [ ] Audit logging configured
- [ ] Timeout limits set appropriately
- [ ] Access control enforced
- [ ] Regular security reviews conducted

Next steps:
- See [Tool Fundamentals](fundamentals.md) for creating safe tools
- See [Tool Development](development.md) for advanced patterns
- See [Tool Registry](registry.md) for managing tools
- Review your security requirements before using depot tools
