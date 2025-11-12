"""Unit tests for spark.tools.__init__ module."""

import pytest
from typing import Any

from spark.tools import (
    ToolContext,
    tool,
    BaseTool,
    ToolSpec,
)
from spark.tools.types import ToolUse


class TestToolsInit:
    """Test cases for spark.tools.__init__ module exports."""

    def test_tool_context_import(self):
        """Test ToolContext is properly imported."""
        from spark.tools import ToolContext

        # Should be importable
        assert ToolContext is not None

        # Should be the correct class
        tool_use: ToolUse = {
            "input": {},
            "name": "test_tool",
            "toolUseId": "test-id"
        }
        context = ToolContext(tool_use=tool_use, invocation_state={})

        assert isinstance(context, ToolContext)
        assert context.tool_use == tool_use
        assert context.invocation_state == {}

    def test_tool_decorator_import(self):
        """Test tool decorator is properly imported."""
        from spark.tools import tool

        # Should be callable
        assert callable(tool)

        # Should work as decorator
        @tool
        def test_function(param: str) -> str:
            """Test function decorated with @tool."""
            return f"Processed {param}"

        # Should have tool properties
        assert hasattr(test_function, 'tool_name')
        assert hasattr(test_function, 'tool_spec')
        assert test_function.tool_name == "test_function"

        # Should still be callable as original function
        result = test_function("test")
        assert result == "Processed test"

    def test_base_tool_import(self):
        """Test BaseTool is properly imported."""
        from spark.tools import BaseTool

        # Should be importable
        assert BaseTool is not None

        # Should be the correct abstract base class
        assert hasattr(BaseTool, '__abstractmethods__')

        # Should not be instantiable directly
        with pytest.raises(TypeError):
            BaseTool()

        # Test concrete implementation
        class ConcreteTool(BaseTool):
            @property
            def tool_name(self) -> str:
                return "concrete_tool"

            @property
            def tool_spec(self) -> ToolSpec:
                return {
                    "name": "concrete_tool",
                    "description": "A concrete tool",
                    "parameters": {"json": {"type": "object", "properties": {}, "required": []}}
                }

            @property
            def tool_type(self) -> str:
                return "test"

            def __call__(self, *args: Any, **kwargs: Any) -> Any:
                return "tool executed"

        concrete = ConcreteTool()
        assert isinstance(concrete, BaseTool)
        assert concrete.tool_name == "concrete_tool"

    def test_tool_spec_import(self):
        """Test ToolSpec is properly imported."""
        from spark.tools import ToolSpec

        # Should be importable
        assert ToolSpec is not None

        # Should work as type annotation
        def function_with_tool_spec(spec: ToolSpec) -> ToolSpec:
            """Function that uses ToolSpec type."""
            return spec

        test_spec: ToolSpec = {
            "name": "test_tool",
            "description": "Test tool spec",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }

        result = function_with_tool_spec(test_spec)
        assert result == test_spec
        assert result["name"] == "test_tool"

    def test_all_exports(self):
        """Test that __all__ contains the expected exports."""
        from spark.tools import __all__

        expected_exports = ["ToolContext", "tool", "BaseTool", "ToolSpec", "ToolCallExecutor", "ToolExecutionConfig"]
        assert set(__all__) == set(expected_exports)

    def test_exports_are_available_as_attributes(self):
        """Test that all exported items are available as module attributes."""
        import spark.tools as tools_module

        # Check that all items in __all__ are available
        for export_name in tools_module.__all__:
            assert hasattr(tools_module, export_name)

        # Verify the attributes are the expected objects
        assert tools_module.ToolContext is not None
        assert callable(tools_module.tool)
        assert tools_module.BaseTool is not None
        assert tools_module.ToolSpec is not None

    def test_import_from_submodules(self):
        """Test that imports come from the correct submodules."""
        from spark.tools import ToolContext, tool, BaseTool, ToolSpec
        from spark.tools.decorator import ToolContext as DecoratorToolContext, tool as decorator_tool
        from spark.tools.types import BaseTool as TypesBaseTool, ToolSpec as TypesToolSpec

        # Should be the same objects
        assert ToolContext is DecoratorToolContext
        assert tool is decorator_tool
        assert BaseTool is TypesBaseTool
        assert ToolSpec is TypesToolSpec

    def test_backward_compatibility_imports(self):
        """Test that imports work for backward compatibility."""
        # Should be able to import from spark.tools directly
        # without needing to know the internal module structure

        # Import all public API
        from spark.tools import (
            ToolContext,
            tool,
            BaseTool,
            ToolSpec,
        )

        # All should be importable and usable
        assert ToolContext is not None
        assert callable(tool)
        assert BaseTool is not None
        assert ToolSpec is not None

        # Test that they work together as expected
        tool_use: ToolUse = {
            "input": {},
            "name": "compatibility_test",
            "toolUseId": "compat-id"
        }
        context = ToolContext(tool_use=tool_use, invocation_state={})

        @tool
        def compatibility_tool(data: str) -> str:
            """Tool for compatibility testing."""
            return data

        result = compatibility_tool("test")
        assert result == "test"

        # Should have the expected interfaces
        assert isinstance(compatibility_tool, BaseTool)
        assert compatibility_tool.tool_spec["name"] == "compatibility_tool"

    def test_no_private_exports(self):
        """Test that private module items are not in __all__."""
        import spark.tools as tools_module

        # Check that __all__ doesn't contain private items
        for export_name in tools_module.__all__:
            assert not export_name.startswith('_'), f"Private item {export_name} should not be in __all__"

        # Check that common private module attributes are not exported
        private_items = [
            '__name__',
            '__doc__',
            '__package__',
            '__loader__',
            '__spec__',
            '__file__',
            '__path__',
            '__cached__',
            '__builtins__',
        ]

        for private_item in private_items:
            assert private_item not in tools_module.__all__, f"Private item {private_item} should not be in __all__"