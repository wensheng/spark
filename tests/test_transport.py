"""Tests for transport protocol boundaries."""

import importlib
import pickle
import struct
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from spark import ActorAddress
from spark.core.identity import ActorId, ActorIncarnation, Envelope, SyndicateId
from spark.transport.codec import CBOR2DependencyError, CBOR2EnvelopeCodec, CodecError, PickleEnvelopeCodec, _load_cbor2
from spark.transport.websocket import WebSocketDependencyError, _load_websockets


class TestPickleEnvelopeCodec:
    def test_round_trip_preserves_envelope(self) -> None:
        codec = PickleEnvelopeCodec()
        target = ActorId(SyndicateId())
        sender = ActorId(target.syndicate_id)
        envelope = Envelope(
            target=target,
            payload={"message": "hello"},
            sender=sender,
            headers={"route": "remote"},
        )

        decoded = codec.decode(codec.encode(envelope))

        assert decoded == envelope

    def test_decode_rejects_short_frame(self) -> None:
        codec = PickleEnvelopeCodec()

        with pytest.raises(CodecError, match="too short"):
            codec.decode(b"SPRK")

    def test_decode_rejects_invalid_magic(self) -> None:
        codec = PickleEnvelopeCodec()
        header = struct.Struct("!4sH").pack(b"NOPE", codec.protocol_version)

        with pytest.raises(CodecError, match="invalid magic"):
            codec.decode(header + pickle.dumps(Envelope(target=ActorId(SyndicateId()), payload="hello")))

    def test_decode_rejects_unsupported_protocol_version(self) -> None:
        codec = PickleEnvelopeCodec()
        header = struct.Struct("!4sH").pack(b"SPRK", codec.protocol_version + 1)

        with pytest.raises(CodecError, match="unsupported transport protocol version"):
            codec.decode(header + pickle.dumps(Envelope(target=ActorId(SyndicateId()), payload="hello")))

    def test_decode_requires_envelope_payload(self) -> None:
        codec = PickleEnvelopeCodec()
        header = struct.Struct("!4sH").pack(b"SPRK", codec.protocol_version)

        with pytest.raises(CodecError, match="did not contain an Envelope"):
            codec.decode(header + pickle.dumps({"payload": "hello"}))


class TestCBOR2EnvelopeCodec:
    def test_round_trip_preserves_envelope_with_cbor_payload(self) -> None:
        pytest.importorskip("cbor2")
        codec = CBOR2EnvelopeCodec()
        target = ActorId(SyndicateId())
        sender = ActorId(target.syndicate_id)
        target_incarnation = ActorIncarnation(target, generation=2)
        deadline = datetime(2026, 5, 9, 12, 30, 45, tzinfo=UTC)
        envelope = Envelope(
            target=target,
            payload={
                "message": "hello",
                "count": 3,
                "active": True,
                "raw": b"bytes",
                "items": [None, 1.5, "ok"],
                "pair": ("left", 2),
                "address": ActorAddress(sender),
            },
            target_incarnation=target_incarnation,
            sender=sender,
            headers={"route": "remote", "nested": {"key": "value"}},
            deadline=deadline,
            correlation_id="corr",
            trace_id="trace",
        )

        decoded = codec.decode(codec.encode(envelope))

        assert decoded == envelope

    def test_rejects_unsupported_payload_objects(self) -> None:
        pytest.importorskip("cbor2")
        codec = CBOR2EnvelopeCodec()

        class Unsupported:
            pass

        envelope = Envelope(target=ActorId(SyndicateId()), payload=Unsupported())

        with pytest.raises(CodecError, match="payload is not CBOR-serializable"):
            codec.encode(envelope)

    def test_decode_rejects_invalid_magic(self) -> None:
        pytest.importorskip("cbor2")
        codec = CBOR2EnvelopeCodec()
        payload = PickleEnvelopeCodec().encode(Envelope(target=ActorId(SyndicateId()), payload="hello"))

        with pytest.raises(CodecError, match="CBOR transport frame has invalid magic"):
            codec.decode(payload)

    def test_decode_rejects_unsupported_protocol_version(self) -> None:
        cbor2 = pytest.importorskip("cbor2")
        codec = CBOR2EnvelopeCodec()
        header = struct.Struct("!4sH").pack(b"SPCB", codec.protocol_version + 1)

        with pytest.raises(CodecError, match="unsupported CBOR transport protocol version"):
            codec.decode(header + cbor2.dumps({"type": "spark.envelope"}))

    def test_decode_requires_envelope_payload(self) -> None:
        cbor2 = pytest.importorskip("cbor2")
        codec = CBOR2EnvelopeCodec()
        header = struct.Struct("!4sH").pack(b"SPCB", codec.protocol_version)

        with pytest.raises(CodecError, match="did not contain an Envelope"):
            codec.decode(header + cbor2.dumps({"type": "not-an-envelope"}))


class TestCBOR2Packaging:
    def test_missing_cbor2_dependency_has_install_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import spark.transport.codec as transport_codec

        real_import_module = importlib.import_module

        def fake_import_module(name: str, package: str | None = None):
            if name == "cbor2":
                raise ImportError("missing cbor2")
            return real_import_module(name, package)

        monkeypatch.setattr(transport_codec, "_CBOR2_API", None)
        monkeypatch.setattr(transport_codec.importlib, "import_module", fake_import_module)

        with pytest.raises(CBOR2DependencyError, match=r"spark-actor\[cbor2\]"):
            _load_cbor2()

    def test_cbor2_extra_is_declared(self) -> None:
        pyproject = Path(__file__).parents[1] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())

        assert data["project"]["optional-dependencies"]["cbor2"] == ["cbor2>=5.9,<6"]


class TestWebSocketPackaging:
    def test_missing_websockets_dependency_has_install_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import spark.transport.websocket as websocket_transport

        real_import_module = importlib.import_module

        def fake_import_module(name: str, package: str | None = None):
            if name.startswith("websockets"):
                raise ImportError("missing websockets")
            return real_import_module(name, package)

        monkeypatch.setattr(websocket_transport, "_WEBSOCKETS_API", None)
        monkeypatch.setattr(websocket_transport.importlib, "import_module", fake_import_module)

        with pytest.raises(WebSocketDependencyError, match=r"spark-actor\[websocket\]"):
            _load_websockets()

    def test_websocket_extra_and_relay_script_are_declared(self) -> None:
        pyproject = Path(__file__).parents[1] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())

        assert data["project"]["optional-dependencies"]["websocket"] == ["websockets>=16,<17"]
        assert data["project"]["scripts"]["spark-ws-relay"] == "spark.transport.websocket:main"
