"""Mission workspace abstractions."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Iterable
import shutil

@dataclass(slots=True)
class WorkspacePolicy:
    """Lifecycle policy describing cleanup expectations."""

    cleanup_on_success: bool = False
    cleanup_on_failure: bool = False


@dataclass(slots=True)
class WorkspaceMount:
    """Describes a directory made available to a mission."""

    name: str
    path: Path
    read_only: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WorkspaceSecrets:
    """Secret bundles that may be injected into tools/agents."""

    values: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkspaceError(RuntimeError):
    """Raised when workspace operations fail."""


class Workspace:
    """Mission workspace describing mounts, caches, and secrets."""

    def __init__(
        self,
        *,
        root: str | Path,
        mounts: Iterable[WorkspaceMount] | None = None,
        secrets: WorkspaceSecrets | None = None,
        env: dict[str, str] | None = None,
        policy: WorkspacePolicy | None = None,
    ) -> None:
        self.root = Path(root)
        self.mounts = list(mounts or [])
        self.secrets = secrets or WorkspaceSecrets()
        self.env = dict(env or {})
        self.policy = policy or WorkspacePolicy()

    def describe(self) -> dict[str, Any]:
        return {
            'root': str(self.root),
            'mounts': [self._describe_mount(m) for m in self.mounts],
            'secrets': list(self.secrets.values.keys()),
            'env': dict(self.env),
            'policy': asdict(self.policy),
        }

    def add_mount(self, mount: WorkspaceMount) -> None:
        self.mounts.append(mount)

    def set_secret(self, key: str, value: str) -> None:
        self.secrets.values[key] = value

    def environment(self) -> dict[str, str]:
        combined = dict(os.environ)
        combined.update(self.env)
        for key, value in self.secrets.values.items():
            combined.setdefault(key, value)
        return combined

    async def ensure_directories(self) -> None:
        await asyncio.to_thread(self.root.mkdir, parents=True, exist_ok=True)
        for mount in self.mounts:
            await asyncio.to_thread(mount.path.mkdir, parents=True, exist_ok=True)

    async def cleanup(self) -> None:
        if not self.root.exists():
            return
        await asyncio.to_thread(shutil.rmtree, self.root, ignore_errors=True)

    def _describe_mount(self, mount: WorkspaceMount) -> dict[str, Any]:
        return {
            'name': mount.name,
            'path': str(mount.path),
            'read_only': mount.read_only,
            'metadata': dict(mount.metadata),
        }


class WorkspaceManager:
    """Creates and manages named workspaces for missions."""

    def __init__(self, factory: Callable[..., Workspace] | None = None) -> None:
        self._factory = factory or Workspace

    def create(
        self,
        *,
        root: str | Path,
        mounts: Iterable[WorkspaceMount] | None = None,
        secrets: WorkspaceSecrets | None = None,
        env: dict[str, str] | None = None,
        policy: WorkspacePolicy | None = None,
    ) -> Workspace:
        workspace = self._factory(root=root, mounts=mounts, secrets=secrets, env=env, policy=policy)
        return workspace
