"""Mission state schema helpers."""

from __future__ import annotations

from typing import Any, Callable, ClassVar, Dict

from pydantic import BaseModel, ConfigDict


MigrationFn = Callable[[dict[str, Any]], dict[str, Any]]


class MissionStateModel(BaseModel):
    """Base class for declaring structured mission state."""

    model_config = ConfigDict(extra='allow')
    schema_name: ClassVar[str] = "mission_state"
    schema_version: ClassVar[str] = "1.0"
    _schema_migrations: ClassVar[Dict[str, Dict[str, MigrationFn]]] = {}

    @classmethod
    def schema_metadata(cls) -> dict[str, str]:
        """Return metadata describing the schema."""
        return {
            'name': getattr(cls, 'schema_name', cls.__name__),
            'version': getattr(cls, 'schema_version', '1.0'),
            'module': f"{cls.__module__}:{cls.__name__}",
        }

    @classmethod
    def register_migration(cls, from_version: str, to_version: str, func: MigrationFn) -> None:
        """Register a migration function that upgrades state to the next version."""

        transitions = cls._schema_migrations.setdefault(from_version, {})
        if to_version in transitions:
            raise ValueError(
                f"Migration from {from_version} -> {to_version} already registered for {cls.__name__}"
            )
        transitions[to_version] = func

    @classmethod
    def migrate_state(
        cls,
        state: dict[str, Any],
        *,
        current_version: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Apply registered migrations until reaching the schema's declared version."""

        target_version = getattr(cls, 'schema_version', '1.0')
        version = current_version or state.get('__schema_version__') or target_version
        if version == target_version:
            return dict(state), target_version

        migrated = dict(state)
        visited: set[str] = set()
        while version != target_version:
            transitions = cls._schema_migrations.get(version)
            if not transitions:
                raise RuntimeError(
                    f"No migration path registered from version {version} to {target_version} for {cls.__name__}"
                )
            if len(transitions) != 1:
                raise RuntimeError(
                    f"Ambiguous migrations from {version} for {cls.__name__}: {list(transitions.keys())}"
                )
            next_version, func = next(iter(transitions.items()))
            migrated = func(dict(migrated))
            if next_version in visited:
                raise RuntimeError(f"Migration cycle detected for {cls.__name__} at {next_version}")
            visited.add(next_version)
            version = next_version

        return migrated, version
