"""
Storage backends for Spark telemetry.

This package provides various backend implementations for persisting
telemetry data:
- NoOpBackend: Disabled telemetry (no storage)
- MemoryBackend: In-memory storage (testing)
- SQLiteBackend: Local SQLite database
- PostgreSQLBackend: Remote PostgreSQL database
"""

from spark.telemetry.backends.base import BaseTelemetryBackend, NoOpBackend

__all__ = [
    'BaseTelemetryBackend',
    'NoOpBackend',
]
