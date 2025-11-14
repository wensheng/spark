"""Utilities for importing modules and classes from string references.

This module provides utilities for converting between callables/classes and
their string references (module:function format), which is essential for
serialization to JSON specifications.
"""

from __future__ import annotations

import importlib
from typing import Callable, Type, Any, Optional


class ImportError(Exception):
    """Raised when import from reference fails."""
    pass


def import_from_ref(ref: str) -> Callable:
    """Import a function from module:function reference.

    Args:
        ref: String in format "module.path:function_name"

    Returns:
        The imported function

    Raises:
        ImportError: If module or function cannot be imported

    Examples:
        >>> func = import_from_ref("os.path:join")
        >>> result = func("a", "b")
        'a/b'
    """
    if ':' not in ref:
        raise ImportError(
            f"Invalid reference format: {ref!r}. "
            f"Expected 'module:function' or 'module.path:function'"
        )

    module_path, func_name = ref.rsplit(':', 1)

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise ImportError(f"Cannot import module {module_path!r}: {e}") from e
    except Exception as e:
        raise ImportError(f"Error importing module {module_path!r}: {e}") from e

    try:
        func = getattr(module, func_name)
    except AttributeError as e:
        raise ImportError(
            f"Module {module_path!r} has no attribute {func_name!r}"
        ) from e

    if not callable(func):
        raise ImportError(f"{ref!r} is not callable")

    return func


def import_class_from_ref(ref: str) -> Type:
    """Import a class from module:ClassName reference.

    Args:
        ref: String in format "module.path:ClassName"

    Returns:
        The imported class

    Raises:
        ImportError: If module or class cannot be imported

    Examples:
        >>> cls = import_class_from_ref("pathlib:Path")
        >>> instance = cls(".")
    """
    if ':' not in ref:
        raise ImportError(
            f"Invalid reference format: {ref!r}. "
            f"Expected 'module:ClassName' or 'module.path:ClassName'"
        )

    module_path, class_name = ref.rsplit(':', 1)

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise ImportError(f"Cannot import module {module_path!r}: {e}") from e
    except Exception as e:
        raise ImportError(f"Error importing module {module_path!r}: {e}") from e

    try:
        cls = getattr(module, class_name)
    except AttributeError as e:
        raise ImportError(
            f"Module {module_path!r} has no attribute {class_name!r}"
        ) from e

    if not isinstance(cls, type):
        raise ImportError(f"{ref!r} is not a class")

    return cls


def get_ref_for_callable(func: Callable) -> str:
    """Get module:function reference for a callable.

    Args:
        func: A callable function

    Returns:
        String reference in format "module:function"

    Raises:
        ValueError: If callable cannot be referenced (e.g., lambda, local function)

    Examples:
        >>> import os.path
        >>> ref = get_ref_for_callable(os.path.join)
        'posixpath:join'  # or 'ntpath:join' on Windows
    """
    if not callable(func):
        raise ValueError(f"{func!r} is not callable")

    if not hasattr(func, '__module__'):
        raise ValueError(f"Cannot get module for {func!r}")

    if not hasattr(func, '__name__'):
        raise ValueError(f"Cannot get name for {func!r}")

    # Check if it's a lambda
    if func.__name__ == '<lambda>':
        raise ValueError(f"Cannot create reference for lambda function")

    # Check if it's a local function (no proper module)
    if func.__module__ is None or func.__module__ == '__main__':
        raise ValueError(
            f"Cannot create reference for local function {func.__name__!r}. "
            f"Define function in a module that can be imported."
        )

    return f"{func.__module__}:{func.__name__}"


def get_ref_for_class(cls: Type) -> str:
    """Get module:ClassName reference for a class.

    Args:
        cls: A class

    Returns:
        String reference in format "module:ClassName"

    Raises:
        ValueError: If class cannot be referenced

    Examples:
        >>> from pathlib import Path
        >>> ref = get_ref_for_class(Path)
        'pathlib:Path'
    """
    if not isinstance(cls, type):
        raise ValueError(f"{cls!r} is not a class")

    if not hasattr(cls, '__module__'):
        raise ValueError(f"Cannot get module for {cls!r}")

    if not hasattr(cls, '__name__'):
        raise ValueError(f"Cannot get name for {cls!r}")

    if cls.__module__ is None or cls.__module__ == '__main__':
        raise ValueError(
            f"Cannot create reference for local class {cls.__name__!r}. "
            f"Define class in a module that can be imported."
        )

    return f"{cls.__module__}:{cls.__name__}"


def safe_import_from_ref(ref: str, fallback: Optional[Any] = None) -> Any:
    """Safely import from reference, returning fallback on error.

    Args:
        ref: Module reference string
        fallback: Value to return on error (default: None)

    Returns:
        Imported object or fallback

    Examples:
        >>> func = safe_import_from_ref("os.path:join", lambda *a: "/".join(a))
        >>> func("a", "b")
        'a/b'
    """
    try:
        return import_from_ref(ref)
    except ImportError:
        return fallback


def validate_reference(ref: str) -> tuple[bool, Optional[str]]:
    """Validate that a reference string can be imported.

    Args:
        ref: Module reference string

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> valid, error = validate_reference("os.path:join")
        >>> valid
        True
        >>> valid, error = validate_reference("invalid:ref")
        >>> valid
        False
    """
    try:
        import_from_ref(ref)
        return True, None
    except ImportError as e:
        return False, str(e)
