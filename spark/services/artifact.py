"""Artifact provider skeleton for dynamic actor loading."""

from __future__ import annotations

import hashlib
import importlib
import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..actor.base import Actor
from ..core.identity import FrozenHeaders


class ArtifactError(ValueError):
    """Raised when an actor artifact cannot be resolved."""


class ArtifactVerificationError(ArtifactError):
    """Raised when artifact integrity or signature verification fails."""


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Reference to an actor class artifact."""

    module: str
    qualified_name: str
    sha256: str | None = None
    signature: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=FrozenHeaders)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", FrozenHeaders(self.metadata))

    @classmethod
    def from_actor_class(
        cls,
        actor_class: type[Actor],
        *,
        sha256: str | None = None,
        signature: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ArtifactRef:
        """Build an artifact reference for an importable actor class."""
        return cls(
            module=actor_class.__module__,
            qualified_name=actor_class.__qualname__,
            sha256=sha256,
            signature=signature,
            metadata=metadata or {},
        )


class SignatureVerifier(Protocol):
    """Verifies an artifact signature for a digest."""

    def verify(self, ref: ArtifactRef, digest: str) -> bool:
        """Return whether ref.signature is valid for digest."""
        ...


class ArtifactProvider(Protocol):
    """Resolves artifact references into actor classes."""

    def resolve(self, ref: ArtifactRef) -> type[Actor]:
        """Resolve a reference to an Actor subclass."""
        ...


class PackageArtifactProvider:
    """Resolve actors from normal Python packages with optional integrity checks."""

    def __init__(self, verifier: SignatureVerifier | None = None) -> None:
        self._verifier = verifier

    def resolve(self, ref: ArtifactRef) -> type[Actor]:
        """Resolve and verify an actor class reference."""
        module = importlib.import_module(ref.module)
        digest = self._module_sha256(module) if ref.sha256 is not None or ref.signature is not None else None
        if ref.sha256 is not None and digest != ref.sha256:
            raise ArtifactVerificationError("artifact sha256 mismatch")
        if ref.signature is not None:
            if digest is None:
                raise ArtifactVerificationError("artifact signature requires a module file digest")
            if self._verifier is None:
                raise ArtifactVerificationError("artifact signature verifier is required")
            if not self._verifier.verify(ref, digest):
                raise ArtifactVerificationError("artifact signature verification failed")

        resolved = self._resolve_qualified_name(module, ref.qualified_name)
        if not isinstance(resolved, type) or not issubclass(resolved, Actor):
            raise ArtifactError(f"artifact {ref.module}:{ref.qualified_name} is not an Actor subclass")
        return resolved

    def _module_sha256(self, module: Any) -> str:
        path_value = inspect.getsourcefile(module)
        if path_value is None:
            raise ArtifactVerificationError("artifact module has no source file for digest verification")
        path = Path(path_value)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _resolve_qualified_name(self, module: Any, qualified_name: str) -> Any:
        value = module
        for part in qualified_name.split("."):
            if part == "<locals>":
                raise ArtifactError("local classes are not importable artifacts")
            try:
                value = getattr(value, part)
            except AttributeError as exc:
                raise ArtifactError(f"artifact symbol not found: {qualified_name}") from exc
        return value
