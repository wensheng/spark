"""Tests for import utilities."""

import pytest
from spark.utils.import_utils import (
    import_from_ref,
    import_class_from_ref,
    get_ref_for_callable,
    get_ref_for_class,
    safe_import_from_ref,
    validate_reference,
    ImportError as SparkImportError
)


def test_import_from_ref_success():
    """Test successful function import."""
    func = import_from_ref("os.path:join")
    assert callable(func)
    result = func("a", "b")
    assert result.endswith("b")
    assert "a" in result


def test_import_from_ref_invalid_format():
    """Test invalid reference format."""
    with pytest.raises(SparkImportError, match="Invalid reference format"):
        import_from_ref("invalid_format")


def test_import_from_ref_missing_module():
    """Test importing from non-existent module."""
    with pytest.raises(SparkImportError, match="Cannot import module"):
        import_from_ref("nonexistent_module_12345:func")


def test_import_from_ref_missing_function():
    """Test importing non-existent function."""
    with pytest.raises(SparkImportError, match="has no attribute"):
        import_from_ref("os.path:nonexistent_func_12345")


def test_import_from_ref_not_callable():
    """Test importing non-callable attribute."""
    with pytest.raises(SparkImportError, match="is not callable"):
        import_from_ref("os:name")  # os.name is a string, not callable


def test_import_class_from_ref_success():
    """Test successful class import."""
    cls = import_class_from_ref("pathlib:Path")
    assert isinstance(cls, type)
    instance = cls(".")
    assert instance.exists()


def test_import_class_from_ref_invalid_format():
    """Test invalid reference format for class."""
    with pytest.raises(SparkImportError, match="Invalid reference format"):
        import_class_from_ref("invalid_format")


def test_import_class_from_ref_missing_module():
    """Test importing class from non-existent module."""
    with pytest.raises(SparkImportError, match="Cannot import module"):
        import_class_from_ref("nonexistent_module_12345:MyClass")


def test_import_class_from_ref_missing_class():
    """Test importing non-existent class."""
    with pytest.raises(SparkImportError, match="has no attribute"):
        import_class_from_ref("pathlib:NonexistentClass12345")


def test_import_class_from_ref_not_a_class():
    """Test importing non-class attribute."""
    with pytest.raises(SparkImportError, match="is not a class"):
        import_class_from_ref("os.path:join")  # join is a function, not class


def test_get_ref_for_callable_success():
    """Test getting reference from callable."""
    import os.path
    ref = get_ref_for_callable(os.path.join)
    assert ":" in ref
    assert ref.endswith(":join")
    # Should be able to re-import
    func = import_from_ref(ref)
    assert func == os.path.join


def test_get_ref_for_callable_lambda():
    """Test that lambda raises ValueError."""
    lam = lambda x: x + 1
    with pytest.raises(ValueError, match="lambda"):
        get_ref_for_callable(lam)


def test_get_ref_for_callable_not_callable():
    """Test that non-callable raises ValueError."""
    with pytest.raises(ValueError, match="not callable"):
        get_ref_for_callable("not a function")


def test_get_ref_for_class_success():
    """Test getting reference from class."""
    from pathlib import Path
    ref = get_ref_for_class(Path)
    assert ref == "pathlib:Path"
    # Should be able to re-import
    cls = import_class_from_ref(ref)
    assert cls == Path


def test_get_ref_for_class_not_a_class():
    """Test that non-class raises ValueError."""
    with pytest.raises(ValueError, match="not a class"):
        get_ref_for_class("not a class")


def test_safe_import_from_ref_success():
    """Test safe import with valid reference."""
    func = safe_import_from_ref("os.path:join")
    assert callable(func)


def test_safe_import_from_ref_failure():
    """Test safe import with invalid reference returns fallback."""
    result = safe_import_from_ref("invalid:ref", fallback="FALLBACK")
    assert result == "FALLBACK"


def test_safe_import_from_ref_failure_none():
    """Test safe import with invalid reference returns None by default."""
    result = safe_import_from_ref("invalid:ref")
    assert result is None


def test_validate_reference_valid():
    """Test validating a valid reference."""
    valid, error = validate_reference("os.path:join")
    assert valid is True
    assert error is None


def test_validate_reference_invalid():
    """Test validating an invalid reference."""
    valid, error = validate_reference("invalid:ref")
    assert valid is False
    assert error is not None
    assert "Cannot import module" in error


def test_round_trip_function():
    """Test that we can go function -> ref -> function."""
    import os.path

    # Get reference
    ref = get_ref_for_callable(os.path.join)

    # Re-import
    func = import_from_ref(ref)

    # Should be the same function
    assert func == os.path.join


def test_round_trip_class():
    """Test that we can go class -> ref -> class."""
    from pathlib import Path

    # Get reference
    ref = get_ref_for_class(Path)

    # Re-import
    cls = import_class_from_ref(ref)

    # Should be the same class
    assert cls == Path


def test_nested_module_import():
    """Test importing from nested modules."""
    # Test deeply nested module
    func = import_from_ref("os.path:join")
    assert callable(func)


def test_builtin_function():
    """Test that builtins work."""
    func = import_from_ref("builtins:print")
    assert callable(func)
    assert func == print


def test_builtin_class():
    """Test that builtin classes work."""
    cls = import_class_from_ref("builtins:dict")
    assert cls == dict
