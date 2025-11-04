"""
Common Spark Utils
"""

import asyncio
import inspect


class SparkUtilError(Exception):
    """Exception for Spark utility errors."""


def arun(fno):
    """Wrapper for asyncio.run."""
    if not inspect.iscoroutine(fno):
        raise SparkUtilError(f"{fno} must be a coroutine (use async def and call without await)")
    return asyncio.run(fno)
