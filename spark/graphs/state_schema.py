"""Mission state schema helpers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MissionStateModel(BaseModel):
    """Base class for declaring structured mission state."""

    model_config = ConfigDict(extra='allow')
    schema_name: str = "mission_state"
    schema_version: str = "1.0"

    @classmethod
    def schema_metadata(cls) -> dict[str, str]:
        """Return metadata describing the schema."""
        return {
            'name': getattr(cls, 'schema_name', cls.__name__),
            'version': getattr(cls, 'schema_version', '1.0'),
            'module': f"{cls.__module__}:{cls.__name__}",
        }
