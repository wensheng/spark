"""Tests for status protocol: SystemStatus, ActorStatus, and format_status()."""

from io import StringIO

import pytest

from spark import Actor, ActorAddress, Syndicate
from spark.core.identity import ActorId, SyndicateId
from spark.core.message import Message
from spark.core.messages import (
    ActorStatus,
    CommonStatusFields,
    FederationAttendee,
    PendingMessage,
    PendingWakeup,
    StatusRequest,
    SystemStatus,
)
from spark.core.status import format_status


class _EchoActor(Actor):
    async def process(self, message: Message) -> None:
        if message.sender is not None:
            await self.tell(message.content, target=message.sender)


class TestSystemStatusConstruction:
    def test_minimal_system_status(self) -> None:
        sid = SyndicateId()
        ss = SystemStatus(
            syndicate_id=sid,
            admin_address="spark://admin",
            actor_count=0,
            uptime_seconds=0.0,
            backend_type="inprocess",
        )
        assert ss.syndicate_id == sid
        assert ss.actor_count == 0
        assert ss.uptime_seconds == 0.0
        assert ss.backend_type == "inprocess"
        assert ss.common.messages_sent == 0
        assert not ss.in_shutdown
        assert ss.capabilities == {}
        assert ss.federation_attendees == ()

    def test_full_system_status(self) -> None:
        sid = SyndicateId()
        ss = SystemStatus(
            syndicate_id=sid,
            admin_address="spark://admin",
            actor_count=5,
            uptime_seconds=300.0,
            backend_type="inprocess",
            common=CommonStatusFields(
                messages_sent=100,
                send_failures=2,
                messages_received=95,
                child_actors=("spark://a", "spark://b"),
                pending_messages=(
                    PendingMessage("a", "b", "hello"),
                ),
            ),
            capabilities={"backend": "inprocess"},
            federation_leader="10.0.0.1:1900",
            federation_register_time="2024-06-01T12:00:00",
            federation_attendees=(
                FederationAttendee("10.0.0.2:1900", "2024-06-01T12:07:00"),
            ),
            dead_letter_addresses=("spark://dead",),
            notify_addresses=("spark://notify1",),
            global_actors={"worker1": "spark://worker1"},
            in_shutdown=False,
        )
        assert ss.actor_count == 5
        assert ss.uptime_seconds == 300.0
        assert ss.common.child_actors == ("spark://a", "spark://b")
        assert len(ss.common.pending_messages) == 1
        assert ss.federation_leader == "10.0.0.1:1900"
        assert len(ss.federation_attendees) == 1
        assert len(ss.dead_letter_addresses) == 1
        assert ss.global_actors == {"worker1": "spark://worker1"}


class TestActorStatusConstruction:
    def test_minimal_actor_status(self) -> None:
        ast = ActorStatus(
            actor_address="spark://actor1",
            actor_class="MyActor",
            admin_address="spark://admin",
        )
        assert ast.actor_address == "spark://actor1"
        assert ast.actor_class == "MyActor"
        assert ast.admin_address == "spark://admin"
        assert ast.parent_address is None
        assert ast.exiting is None
        assert ast.common.messages_sent == 0

    def test_full_actor_status(self) -> None:
        ast = ActorStatus(
            actor_address="spark://actor1",
            actor_class="MyActor",
            admin_address="spark://admin",
            common=CommonStatusFields(
                messages_sent=10,
                messages_received=8,
                child_actors=("spark://child1",),
                pending_wakeups=(
                    PendingWakeup("spark://actor1", 5.0, "wake"),
                ),
            ),
            parent_address="spark://parent",
            exiting="normal exit",
        )
        assert ast.parent_address == "spark://parent"
        assert ast.exiting == "normal exit"
        assert len(ast.common.child_actors) == 1
        assert len(ast.common.pending_wakeups) == 1


class TestSystemStatusE2E:
    @pytest.mark.asyncio
    async def test_status_request_to_system_returns_system_status(self) -> None:
        async with Syndicate("async-status-system") as system:
            result = await system.ask(StatusRequest(), system.address, timeout=2.0)
            assert isinstance(result, SystemStatus)
            assert result.syndicate_id == system.syndicate_id
            assert result.backend_type == "async-inprocess"
            assert result.uptime_seconds >= 0
            assert result.actor_count >= 0

    @pytest.mark.asyncio
    async def test_status_request_to_actor_returns_actor_status(self) -> None:
        async with Syndicate("async-status-actor") as system:
            actor_addr = await system.create_actor(_EchoActor)
            result = await system.ask(StatusRequest(), actor_addr, timeout=2.0)
            assert isinstance(result, ActorStatus)
            assert result.actor_class == "_EchoActor"
            assert result.actor_address == str(actor_addr)
            assert result.admin_address is not None

    @pytest.mark.asyncio
    async def test_system_status_reflects_actors(self) -> None:
        async with Syndicate("async-status-count") as system:
            await system.create_actor(_EchoActor)
            await system.create_actor(_EchoActor)
            result = await system.ask(StatusRequest(), system.address, timeout=2.0)
            assert isinstance(result, SystemStatus)
            assert result.actor_count == 2

    @pytest.mark.asyncio
    async def test_system_status_shows_actors(self) -> None:
        async with Syndicate("async-status-child") as system:
            await system.create_actor(_EchoActor)
            result = await system.ask(StatusRequest(), system.address, timeout=2.0)
            assert isinstance(result, SystemStatus)
            assert result.actor_count >= 1

    @pytest.mark.asyncio
    async def test_system_status_records_dead_letters(self) -> None:
        async with Syndicate("async-status-dead") as system:
            bad_addr = ActorAddress(ActorId(syndicate_id=system.syndicate_id))
            await system.tell("orphan", bad_addr)

            assert len(system.dead_letters) >= 1
            assert system.dead_letters[0].reason == "target not found"

    @pytest.mark.asyncio
    async def test_system_status_shows_pending_wakeups(self) -> None:
        class _WakeupActor(Actor):
            async def process(self, message: Message) -> None:
                pass

        async with Syndicate("async-status-wakeup") as system:
            addr = await system.create_actor(_WakeupActor)
            system.backend.schedule_after(addr.actor_id, 60.0, "delayed")

            result = await system.ask(StatusRequest(), system.address, timeout=2.0)
            assert isinstance(result, SystemStatus)
            assert len(result.common.pending_wakeups) >= 1


class TestFormatStatus:
    def test_format_system_status(self) -> None:
        sid = SyndicateId()
        ss = SystemStatus(
            syndicate_id=sid,
            admin_address="spark://admin",
            actor_count=2,
            uptime_seconds=60.0,
            backend_type="inprocess",
            common=CommonStatusFields(
                child_actors=("spark://a",),
                messages_sent=10,
                send_failures=0,
                messages_received=8,
                pending_messages=(
                    PendingMessage("x", "y", "test"),
                ),
            ),
            capabilities={"backend": "inprocess"},
            dead_letter_addresses=(),
        )
        buf = StringIO()
        format_status(ss, tofd=buf)
        output = buf.getvalue()
        assert "Status of Syndicate" in output
        assert "spark://admin" in output
        assert "Actors: 2" in output
        assert "Uptime: 60.0s" in output
        assert "Backend: inprocess" in output
        assert "Primary Actors [1]" in output
        assert "Pending Messages [1]" in output
        assert "Messages Sent: 10" in output

    def test_format_system_status_in_shutdown(self) -> None:
        ss = SystemStatus(
            syndicate_id=SyndicateId(),
            admin_address="spark://admin",
            actor_count=0,
            uptime_seconds=0.0,
            backend_type="inprocess",
            in_shutdown=True,
        )
        buf = StringIO()
        format_status(ss, tofd=buf)
        assert "[IN SHUTDOWN]" in buf.getvalue()

    def test_format_actor_status(self) -> None:
        ast = ActorStatus(
            actor_address="spark://actor1",
            actor_class="MyActor",
            admin_address="spark://admin",
            common=CommonStatusFields(
                child_actors=("spark://child1", "spark://child2"),
                messages_sent=5,
                messages_received=3,
            ),
            parent_address="spark://parent",
        )
        buf = StringIO()
        format_status(ast, tofd=buf)
        output = buf.getvalue()
        assert "Status of MyActor Actor" in output
        assert "spark://actor1" in output
        assert "Administrator: spark://admin" in output
        assert "Parent  Actor: spark://parent" in output
        assert "Child Actors [2]" in output

    def test_format_actor_status_exiting(self) -> None:
        ast = ActorStatus(
            actor_address="spark://actor1",
            actor_class="MyActor",
            admin_address="spark://admin",
            exiting="normal exit",
        )
        buf = StringIO()
        format_status(ast, tofd=buf)
        assert "EXITING:normal exit" in buf.getvalue()

    def test_format_unknown_type(self) -> None:
        buf = StringIO()
        format_status("unknown", tofd=buf)  # type: ignore[arg-type]
        assert "Status Query Response: unknown" in buf.getvalue()

    def test_format_with_federation_data(self) -> None:
        ss = SystemStatus(
            syndicate_id=SyndicateId(),
            admin_address="spark://admin",
            actor_count=1,
            uptime_seconds=0.0,
            backend_type="inprocess",
            federation_leader="10.0.0.1:1900",
            federation_register_time="2024-01-01T00:00:00",
            federation_attendees=(
                FederationAttendee("10.0.0.2:1900", "2024-01-01T00:07:00"),
            ),
            notify_addresses=("spark://n1",),
        )
        buf = StringIO()
        format_status(ss, tofd=buf)
        output = buf.getvalue()
        assert "Federation Leader: 10.0.0.1:1900" in output
        assert "Registration valid 2024-01-01T00:00:00" in output
        assert "Federation Attendees [1]" in output
        assert "Federation Notifications [1]" in output
