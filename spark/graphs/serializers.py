"""State serialization registry for GraphState backends."""

from __future__ import annotations

import json
import pickle
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict


class StateSerializer(ABC):
    """Base serializer used by state backends."""

    name: ClassVar[str] = 'json'
    binary: ClassVar[bool] = False

    @abstractmethod
    def dumps(self, value: Any) -> bytes:
        """Serialize value into bytes."""

    @abstractmethod
    def loads(self, payload: bytes) -> Any:
        """Deserialize bytes back into python objects."""

    def describe(self) -> dict[str, Any]:
        """Return metadata describing this serializer."""

        return {
            'name': self.name,
            'binary': self.binary,
        }


class JsonStateSerializer(StateSerializer):
    """Default JSON serializer with UTF-8 output."""

    name = 'json'
    binary = False

    def dumps(self, value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')

    def loads(self, payload: bytes) -> Any:
        return json.loads(payload.decode('utf-8'))


class PickleStateSerializer(StateSerializer):
    """Binary serializer using pickle (useful for large Python payloads)."""

    name = 'pickle'
    binary = True

    def dumps(self, value: Any) -> bytes:
        return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)

    def loads(self, payload: bytes) -> Any:
        return pickle.loads(payload)


_SERIALIZER_REGISTRY: Dict[str, StateSerializer] = {}


def register_state_serializer(name: str, serializer: StateSerializer) -> None:
    """Register a serializer implementation."""

    _SERIALIZER_REGISTRY[name] = serializer


def get_state_serializer(name: str) -> StateSerializer:
    """Return serializer by name."""

    if name not in _SERIALIZER_REGISTRY:
        raise ValueError(f"Unknown state serializer '{name}'. Registered: {list(_SERIALIZER_REGISTRY)}")
    return _SERIALIZER_REGISTRY[name]


def ensure_state_serializer(serializer: str | StateSerializer | None) -> StateSerializer:
    """Normalize serializer references to concrete instances."""

    if isinstance(serializer, StateSerializer):
        return serializer
    if isinstance(serializer, str):
        return get_state_serializer(serializer)
    # Default to JSON serializer
    return get_state_serializer('json')


register_state_serializer(JsonStateSerializer.name, JsonStateSerializer())
register_state_serializer(PickleStateSerializer.name, PickleStateSerializer())

