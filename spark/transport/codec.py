"""Versioned transport codecs."""

from __future__ import annotations

import importlib
import pickle
import struct
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast

from ..actor.address import ActorAddress
from ..core.identity import ActorId, ActorIncarnation, Envelope, FrozenHeaders, SyndicateId

_MAGIC = b"SPRK"
_CBOR_MAGIC = b"SPCB"
_PROTOCOL_VERSION = 1
_HEADER = struct.Struct("!4sH")
_CBOR_ENVELOPE_TYPE = "spark.envelope"
_CBOR_ACTOR_ADDRESS_TYPE = "spark.actor_address"
_CBOR_ACTOR_ID_TYPE = "spark.actor_id"
_CBOR_SYSTEM_ID_TYPE = "spark.syndicate_id"
_CBOR_TUPLE_TYPE = "spark.tuple"
_CBOR_TYPE_KEY = "__spark_cbor_type__"
_CBOR_VALUE_KEY = "value"
_CBOR_INSTALL_MESSAGE = "cbor2 transport codec requires the optional 'cbor2' dependency; install spark-actor[cbor2]"


class CodecError(ValueError):
    """Raised when a transport frame cannot be decoded."""


class CBOR2DependencyError(ImportError):
    """Raised when CBOR support is used without the optional dependency."""


class EnvelopeCodec(Protocol):
    """Codec for serializing envelopes at a transport boundary."""

    def encode(self, envelope: Envelope) -> bytes:
        """Encode an envelope into bytes."""
        ...

    def decode(self, payload: bytes) -> Envelope:
        """Decode bytes into an envelope."""
        ...


class PickleEnvelopeCodec:
    """Trusted-boundary pickle codec with a Spark protocol header."""

    protocol_version = _PROTOCOL_VERSION

    def encode(self, envelope: Envelope) -> bytes:
        """Encode an envelope with protocol version metadata."""
        body = pickle.dumps(envelope, protocol=pickle.HIGHEST_PROTOCOL)
        return _HEADER.pack(_MAGIC, self.protocol_version) + body

    def decode(self, payload: bytes) -> Envelope:
        """Decode and validate one encoded envelope."""
        if len(payload) < _HEADER.size:
            raise CodecError("transport frame is too short")
        magic, version = _HEADER.unpack(payload[: _HEADER.size])
        if magic != _MAGIC:
            raise CodecError("transport frame has invalid magic")
        if version != self.protocol_version:
            raise CodecError(f"unsupported transport protocol version: {version}")
        try:
            envelope = pickle.loads(payload[_HEADER.size :])
        except (pickle.PickleError, AttributeError, EOFError, ImportError, IndexError, TypeError) as exc:
            raise CodecError(f"transport frame has invalid pickle payload: {exc}") from exc
        if not isinstance(envelope, Envelope):
            raise CodecError("transport frame did not contain an Envelope")
        return envelope


@dataclass(frozen=True, slots=True)
class _CBOR2Api:
    dumps: Callable[..., bytes]
    loads: Callable[..., Any]
    encode_error: type[BaseException]
    decode_error: type[BaseException]


_CBOR2_API: _CBOR2Api | None = None


def _load_cbor2() -> _CBOR2Api:
    global _CBOR2_API
    if _CBOR2_API is not None:
        return _CBOR2_API
    try:
        cbor2_module = cast(Any, importlib.import_module("cbor2"))
    except ImportError as exc:
        raise CBOR2DependencyError(_CBOR_INSTALL_MESSAGE) from exc
    _CBOR2_API = _CBOR2Api(
        dumps=cast(Callable[..., bytes], cbor2_module.dumps),
        loads=cast(Callable[..., Any], cbor2_module.loads),
        encode_error=cast(type[BaseException], cbor2_module.CBOREncodeError),
        decode_error=cast(type[BaseException], cbor2_module.CBORDecodeError),
    )
    return _CBOR2_API


class CBOR2EnvelopeCodec:
    """CBOR codec for envelopes containing CBOR-native payloads."""

    protocol_version = _PROTOCOL_VERSION

    def encode(self, envelope: Envelope) -> bytes:
        """Encode an envelope using CBOR with Spark protocol metadata."""
        api = _load_cbor2()
        body = _envelope_to_cbor(envelope)
        try:
            payload = api.dumps(body)
        except (api.encode_error, TypeError, ValueError) as exc:
            raise CodecError(f"payload is not CBOR-serializable: {exc}") from exc
        return _HEADER.pack(_CBOR_MAGIC, self.protocol_version) + payload

    def decode(self, payload: bytes) -> Envelope:
        """Decode and validate one CBOR envelope payload."""
        if len(payload) < _HEADER.size:
            raise CodecError("CBOR transport frame is too short")
        magic, version = _HEADER.unpack(payload[: _HEADER.size])
        if magic != _CBOR_MAGIC:
            raise CodecError("CBOR transport frame has invalid magic")
        if version != self.protocol_version:
            raise CodecError(f"unsupported CBOR transport protocol version: {version}")
        api = _load_cbor2()
        try:
            body = api.loads(payload[_HEADER.size :])
        except (api.decode_error, TypeError, ValueError) as exc:
            raise CodecError(f"CBOR transport frame has invalid payload: {exc}") from exc
        return _envelope_from_cbor(body)


def _envelope_to_cbor(envelope: Envelope) -> dict[str, Any]:
    return {
        "type": _CBOR_ENVELOPE_TYPE,
        "target": _actor_id_to_cbor(envelope.target),
        "payload": _to_cbor_value(envelope.payload, "payload"),
        "target_incarnation": (
            None if envelope.target_incarnation is None else _actor_incarnation_to_cbor(envelope.target_incarnation)
        ),
        "message_id": envelope.message_id,
        "headers": _mapping_to_cbor(envelope.headers, "headers"),
        "sender": None if envelope.sender is None else _actor_id_to_cbor(envelope.sender),
        "deadline": None if envelope.deadline is None else envelope.deadline.isoformat(),
        "correlation_id": envelope.correlation_id,
        "trace_id": envelope.trace_id,
    }


def _envelope_from_cbor(value: Any) -> Envelope:
    if not isinstance(value, Mapping):
        raise CodecError("CBOR transport frame did not contain an Envelope")
    if value.get("type") != _CBOR_ENVELOPE_TYPE:
        raise CodecError("CBOR transport frame did not contain an Envelope")
    try:
        deadline = _deadline_from_cbor(value.get("deadline"))
        return Envelope(
            target=_actor_id_from_cbor(value["target"]),
            payload=_from_cbor_value(value["payload"], "payload"),
            target_incarnation=(
                None
                if value.get("target_incarnation") is None
                else _actor_incarnation_from_cbor(value["target_incarnation"])
            ),
            message_id=_require_str(value.get("message_id"), "message_id"),
            headers=FrozenHeaders(_mapping_from_cbor(value.get("headers"), "headers")),
            sender=None if value.get("sender") is None else _actor_id_from_cbor(value["sender"]),
            deadline=deadline,
            correlation_id=_optional_str(value.get("correlation_id"), "correlation_id"),
            trace_id=_optional_str(value.get("trace_id"), "trace_id"),
        )
    except KeyError as exc:
        raise CodecError(f"CBOR transport frame is missing envelope field: {exc.args[0]}") from exc
    except ValueError as exc:
        raise CodecError(f"CBOR transport frame has invalid envelope data: {exc}") from exc


def _to_cbor_value(value: Any, path: str) -> Any:
    if value is None or isinstance(value, bool | int | float | str | bytes):
        return value
    if isinstance(value, ActorAddress):
        return {_CBOR_TYPE_KEY: _CBOR_ACTOR_ADDRESS_TYPE, _CBOR_VALUE_KEY: _actor_id_to_cbor(value.actor_id)}
    if isinstance(value, ActorId):
        return {_CBOR_TYPE_KEY: _CBOR_ACTOR_ID_TYPE, _CBOR_VALUE_KEY: _actor_id_to_cbor(value)}
    if isinstance(value, SyndicateId):
        return {_CBOR_TYPE_KEY: _CBOR_SYSTEM_ID_TYPE, "uuid": value.uuid}
    if isinstance(value, tuple):
        return {_CBOR_TYPE_KEY: _CBOR_TUPLE_TYPE, "items": [_to_cbor_value(item, f"{path}[]") for item in value]}
    if isinstance(value, list):
        return [_to_cbor_value(item, f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        return _mapping_to_cbor(value, path)
    raise CodecError(f"payload is not CBOR-serializable: unsupported value at {path}: {type(value).__name__}")


def _from_cbor_value(value: Any, path: str) -> Any:
    if value is None or isinstance(value, bool | int | float | str | bytes):
        return value
    if isinstance(value, list):
        return [_from_cbor_value(item, f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        marker = value.get(_CBOR_TYPE_KEY)
        if marker == _CBOR_ACTOR_ADDRESS_TYPE:
            return ActorAddress(_actor_id_from_cbor(value.get(_CBOR_VALUE_KEY)))
        if marker == _CBOR_ACTOR_ID_TYPE:
            return _actor_id_from_cbor(value.get(_CBOR_VALUE_KEY))
        if marker == _CBOR_SYSTEM_ID_TYPE:
            return SyndicateId(uuid=_require_str(value.get("uuid"), f"{path}.uuid"))
        if marker == _CBOR_TUPLE_TYPE:
            items = value.get("items")
            if not isinstance(items, Sequence) or isinstance(items, str | bytes | bytearray):
                raise CodecError(f"CBOR tuple marker at {path} requires an items list")
            return tuple(_from_cbor_value(item, f"{path}[]") for item in items)
        return _mapping_from_cbor(value, path)
    raise CodecError(f"CBOR payload has unsupported value at {path}: {type(value).__name__}")


def _mapping_to_cbor(mapping: Mapping[Any, Any], path: str) -> dict[str, Any]:
    encoded: dict[str, Any] = {}
    for key, value in mapping.items():
        if not isinstance(key, str):
            raise CodecError(f"payload is not CBOR-serializable: non-string key at {path}: {key!r}")
        encoded[key] = _to_cbor_value(value, f"{path}.{key}")
    return encoded


def _mapping_from_cbor(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CodecError(f"CBOR payload expected a mapping at {path}")
    decoded: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise CodecError(f"CBOR payload has non-string key at {path}: {key!r}")
        decoded[key] = _from_cbor_value(item, f"{path}.{key}")
    return decoded


def _actor_id_to_cbor(actor_id: ActorId) -> dict[str, str]:
    return {
        "system_uuid": actor_id.syndicate_id.uuid,
        "actor_id": actor_id.actor_id,
    }


def _actor_id_from_cbor(value: Any) -> ActorId:
    if not isinstance(value, Mapping):
        raise CodecError("CBOR actor id must be a mapping")
    return ActorId(
        SyndicateId(uuid=_require_str(value.get("system_uuid"), "system_uuid")),
        actor_id=_require_str(value.get("actor_id"), "actor_id"),
    )


def _actor_incarnation_to_cbor(incarnation: ActorIncarnation) -> dict[str, Any]:
    return {
        "actor_id": _actor_id_to_cbor(incarnation.actor_id),
        "generation": incarnation.generation,
    }


def _actor_incarnation_from_cbor(value: Any) -> ActorIncarnation:
    if not isinstance(value, Mapping):
        raise CodecError("CBOR actor incarnation must be a mapping")
    generation = value.get("generation")
    if not isinstance(generation, int) or generation < 0:
        raise CodecError("CBOR actor incarnation generation must be a non-negative integer")
    return ActorIncarnation(
        actor_id=_actor_id_from_cbor(value.get("actor_id")),
        generation=generation,
    )


def _deadline_from_cbor(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CodecError("CBOR deadline must be an ISO datetime string")
    deadline = datetime.fromisoformat(value)
    if deadline.tzinfo is None:
        raise CodecError("CBOR deadline must be timezone-aware")
    return deadline


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CodecError(f"CBOR field {field} must be a non-empty string")
    return value


def _optional_str(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, field)
