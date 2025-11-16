"""Artifact registry schemas."""

from __future__ import annotations

import datetime as _dt
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from spark.graphs.shared_memory import (
    MemoryReference,
    MemoryAccessPolicy,
    AccessVisibility,
)


class ArtifactStatus(str, Enum):
    """Lifecycle states for artifacts."""

    DRAFT = "draft"
    FINAL = "final"
    DELETED = "deleted"


class ArtifactRecord(BaseModel):
    """Metadata describing a mission artifact."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    artifact_type: str = Field(default='generic', description='Type of artifact (diff, report, dataset, etc.)')
    name: str = Field(default='artifact', description='Human-readable label.')
    description: str | None = Field(default=None, description='Optional description or summary.')
    created_at: _dt.datetime = Field(
        default_factory=lambda: _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)
    )
    node_id: str | None = Field(default=None, description='Producer node identifier.')
    task_id: str | None = Field(default=None, description='Scheduler task identifier.')
    campaign_id: str | None = Field(default=None, description='Campaign identifier if applicable.')
    blob_id: str | None = Field(default=None, description='Identifier returned by GraphState.open_blob_writer().')
    external_uri: str | None = Field(default=None, description='Optional link to remote storage.')
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    references: list[MemoryReference] = Field(default_factory=list)
    access_policy: MemoryAccessPolicy = Field(default_factory=MemoryAccessPolicy)
    status: ArtifactStatus = Field(default=ArtifactStatus.DRAFT)

    model_config = dict(use_enum_values=True)
