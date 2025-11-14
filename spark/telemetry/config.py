"""
Configuration for Spark telemetry system.

This module provides configuration options for controlling telemetry
behavior, including backend selection, sampling, retention, and export.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class TelemetryConfig:
    """Configuration for telemetry collection and export.

    Attributes:
        enabled: Whether telemetry is enabled (default: False)
        backend: Backend type ('sqlite', 'postgresql', 'memory', 'noop')
        backend_config: Backend-specific configuration
        sampling_rate: Fraction of traces to sample (0.0-1.0, default: 1.0)
        export_interval: Interval in seconds for batch export (default: 10.0)
        buffer_size: Maximum number of spans to buffer before flushing (default: 1000)
        max_events_per_span: Maximum events to store per span (default: 100)
        retention_days: Days to retain telemetry data (default: 30)
        resource_attributes: Resource-level attributes (e.g., service name, version)
        enable_metrics: Whether to collect metrics (default: True)
        enable_events: Whether to collect events (default: True)
        enable_traces: Whether to collect traces (default: True)
        propagate_context: Whether to propagate telemetry context (default: True)
        auto_instrument_nodes: Auto-instrument all nodes (default: True)
        auto_instrument_graphs: Auto-instrument all graphs (default: True)
        custom_attributes: Custom attributes to add to all telemetry (default: {})
    """
    enabled: bool = False
    backend: str = 'memory'
    backend_config: Dict[str, Any] = field(default_factory=dict)
    sampling_rate: float = 1.0
    export_interval: float = 10.0
    buffer_size: int = 1000
    max_events_per_span: int = 100
    retention_days: int = 30
    resource_attributes: Dict[str, str] = field(default_factory=dict)
    enable_metrics: bool = True
    enable_events: bool = True
    enable_traces: bool = True
    propagate_context: bool = True
    auto_instrument_nodes: bool = True
    auto_instrument_graphs: bool = True
    custom_attributes: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate configuration."""
        if not 0.0 <= self.sampling_rate <= 1.0:
            raise ValueError(f"sampling_rate must be between 0.0 and 1.0, got {self.sampling_rate}")

        if self.buffer_size < 1:
            raise ValueError(f"buffer_size must be at least 1, got {self.buffer_size}")

        if self.export_interval < 0:
            raise ValueError(f"export_interval must be non-negative, got {self.export_interval}")

        if self.retention_days < 1:
            raise ValueError(f"retention_days must be at least 1, got {self.retention_days}")

        valid_backends = {'sqlite', 'postgresql', 'memory', 'noop'}
        if self.backend not in valid_backends:
            raise ValueError(f"backend must be one of {valid_backends}, got {self.backend}")

    @classmethod
    def create_sqlite(
        cls,
        db_path: str = "spark_telemetry.db",
        **kwargs
    ) -> 'TelemetryConfig':
        """Create configuration for SQLite backend.

        Args:
            db_path: Path to SQLite database file
            **kwargs: Additional configuration options

        Returns:
            TelemetryConfig configured for SQLite
        """
        backend_config = {'db_path': db_path}
        return cls(
            enabled=True,
            backend='sqlite',
            backend_config=backend_config,
            **kwargs
        )

    @classmethod
    def create_postgresql(
        cls,
        host: str = "localhost",
        port: int = 5432,
        database: str = "spark_telemetry",
        user: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs
    ) -> 'TelemetryConfig':
        """Create configuration for PostgreSQL backend.

        Args:
            host: PostgreSQL host
            port: PostgreSQL port
            database: Database name
            user: Username
            password: Password
            **kwargs: Additional configuration options

        Returns:
            TelemetryConfig configured for PostgreSQL
        """
        backend_config = {
            'host': host,
            'port': port,
            'database': database,
            'user': user,
            'password': password,
        }
        return cls(
            enabled=True,
            backend='postgresql',
            backend_config=backend_config,
            **kwargs
        )

    @classmethod
    def create_memory(cls, **kwargs) -> 'TelemetryConfig':
        """Create configuration for in-memory backend (testing).

        Args:
            **kwargs: Additional configuration options

        Returns:
            TelemetryConfig configured for in-memory storage
        """
        return cls(
            enabled=True,
            backend='memory',
            **kwargs
        )

    @classmethod
    def create_noop(cls) -> 'TelemetryConfig':
        """Create configuration with telemetry disabled.

        Returns:
            TelemetryConfig with telemetry disabled
        """
        return cls(enabled=False, backend='noop')

    def should_sample(self, trace_id: str) -> bool:
        """Determine if a trace should be sampled.

        Uses deterministic sampling based on trace_id hash to ensure
        consistent sampling across distributed systems.

        Args:
            trace_id: Trace identifier

        Returns:
            True if trace should be sampled
        """
        if self.sampling_rate >= 1.0:
            return True
        if self.sampling_rate <= 0.0:
            return False

        # Deterministic sampling using hash
        trace_hash = hash(trace_id)
        threshold = int(self.sampling_rate * 2**32)
        return (trace_hash & 0xFFFFFFFF) < threshold

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'enabled': self.enabled,
            'backend': self.backend,
            'backend_config': self.backend_config,
            'sampling_rate': self.sampling_rate,
            'export_interval': self.export_interval,
            'buffer_size': self.buffer_size,
            'max_events_per_span': self.max_events_per_span,
            'retention_days': self.retention_days,
            'resource_attributes': self.resource_attributes,
            'enable_metrics': self.enable_metrics,
            'enable_events': self.enable_events,
            'enable_traces': self.enable_traces,
            'propagate_context': self.propagate_context,
            'auto_instrument_nodes': self.auto_instrument_nodes,
            'auto_instrument_graphs': self.auto_instrument_graphs,
            'custom_attributes': self.custom_attributes,
        }
