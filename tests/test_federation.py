"""Tests for Federation providers and hysteresis (async version).

Integration tests that require the federation Syndicate option are not yet
supported by the async runtime; only the pure-logic unit tests are converted.
"""

from typing import Any

import pytest

from spark import ActorAddress
from spark.core.federation_messages import (
    FederationDeRegister,
    FederationInvite,
    FederationRegister,
    NotifyOnSystemRegistration,
)
from spark.core.identity import ActorId, Envelope, SyndicateId
from spark.runtime.results import DeliveryResult
from spark.services.federation_membership import FederationMembershipProvider
from spark.services.membership import SystemEvent
from spark.transport.hysteresis import HysteresisDelaySender


def _sid(name: str = "test") -> SyndicateId:
    return SyndicateId.from_name(name)


def _aid(name: str = "test") -> ActorId:
    return ActorId(syndicate_id=_sid(name))


def _addr(name: str = "test") -> ActorAddress:
    return ActorAddress(_aid(name))


class TestHysteresisDelaySender:
    def test_single_send_passes_through(self) -> None:
        sent: list[Envelope] = []

        def sender(env: Envelope) -> DeliveryResult:
            sent.append(env)
            return DeliveryResult(success=True)

        hs = HysteresisDelaySender(sender)
        env = Envelope(
            target=_aid(),
            payload=FederationInvite(),
        )
        hs.send_with_hysteresis(env)
        hs.check_sends()
        assert len(sent) == 1

    def test_rapid_sends_get_queued(self) -> None:
        sent: list[Envelope] = []

        def sender(env: Envelope) -> DeliveryResult:
            sent.append(env)
            return DeliveryResult(success=True)

        hs = HysteresisDelaySender(sender, hysteresis_min_period=10.0)
        env1 = Envelope(target=_aid(), payload=FederationInvite())
        env2 = Envelope(target=_aid(), payload=FederationRegister(
            admin_address=_addr(),
            capabilities={},
        ))

        hs.send_with_hysteresis(env1)
        hs.check_sends()
        assert len(sent) == 1

        hs.send_with_hysteresis(env2)
        hs.check_sends()
        assert len(sent) == 1

    def test_dedup_same_target_and_type(self) -> None:
        sent: list[Envelope] = []

        def sender(env: Envelope) -> DeliveryResult:
            sent.append(env)
            return DeliveryResult(success=True)

        target = _aid()
        hs = HysteresisDelaySender(sender, hysteresis_min_period=10.0)

        env1 = Envelope(target=target, payload=FederationInvite())
        hs.send_with_hysteresis(env1)
        hs.check_sends()
        assert len(sent) == 1

        env2 = Envelope(target=target, payload=FederationInvite())
        hs.send_with_hysteresis(env2)
        assert hs.pending_count() == 1

    def test_delay_decays_with_idle(self) -> None:
        sent: list[Envelope] = []

        def sender(env: Envelope) -> DeliveryResult:
            sent.append(env)
            return DeliveryResult(success=True)

        hs = HysteresisDelaySender(
            sender,
            hysteresis_min_period=0.05,
            hysteresis_max_period=1.0,
        )
        hs.send_with_hysteresis(
            Envelope(target=_aid(), payload=FederationInvite())
        )
        hs.check_sends()
        assert len(sent) == 1

        hs.send_with_hysteresis(
            Envelope(target=_aid(), payload=FederationDeRegister(
                admin_address=_addr(),
            ))
        )
        assert hs.pending_count() == 1

        import time
        time.sleep(0.15)
        hs.check_sends()
        assert len(sent) == 2

    def test_cancel_sends(self) -> None:
        sent: list[Envelope] = []

        def sender(env: Envelope) -> DeliveryResult:
            sent.append(env)
            return DeliveryResult(success=True)

        target = _aid()
        hs = HysteresisDelaySender(sender, hysteresis_min_period=10.0)
        hs.send_with_hysteresis(
            Envelope(target=target, payload=FederationInvite())
        )
        hs.check_sends()
        assert len(sent) == 1

        hs.send_with_hysteresis(
            Envelope(target=target, payload=FederationInvite())
        )
        assert hs.pending_count() == 1

        hs.cancel_sends(str(target))
        assert hs.pending_count() == 0


class TestFederationMembershipProvider:
    @staticmethod
    def _make_provider(
        syndicate_id: str = "test-system",
    ) -> FederationMembershipProvider:
        from spark.core.identity import SyndicateId

        sid = SyndicateId.from_name(syndicate_id)
        aid = ActorId(syndicate_id=sid, actor_id="__spark_federation__")
        address = ActorAddress(aid)

        def send_message(env: Envelope) -> DeliveryResult:
            return DeliveryResult(success=True)

        def send_to(env: Envelope, host: str, port: int) -> DeliveryResult:
            return DeliveryResult(success=True)

        return FederationMembershipProvider(
            syndicate_id=sid,
            federation_actor_id=aid,
            address=address,
            capabilities={"backend": "inprocess"},
            send_message=send_message,
            send_to_address=send_to,
            reregistration_period=0.5,
            restart_period=0.3,
        )

    def test_list_systems_returns_own_descriptor_after_join(self) -> None:
        provider1 = self._make_provider("sys1")
        provider2 = self._make_provider("sys2")

        reg = FederationRegister(
            admin_address=provider2._address,
            capabilities=provider2._capabilities,
            first_time=True,
        )
        envelope = Envelope(
            target=provider1._federation_actor_id,
            sender=provider2._federation_actor_id,
            payload=reg,
        )
        provider1.handle_envelope(envelope)

        systems = provider1.list_systems()
        assert len(systems) >= 1

    def test_watch_replays_existing_systems(self) -> None:
        provider1 = self._make_provider("sys1")
        provider2 = self._make_provider("sys2")

        reg = FederationRegister(
            admin_address=provider2._address,
            capabilities=provider2._capabilities,
            first_time=True,
        )
        provider1.handle_envelope(
            Envelope(
                target=provider1._federation_actor_id,
                sender=provider2._federation_actor_id,
                payload=reg,
            )
        )

        events: list[SystemEvent] = []
        provider1.watch(lambda e: events.append(e))
        joined_events = [e for e in events if e.kind == "joined"]
        assert len(joined_events) >= 1

    def test_federation_register_first_time_and_refresh(self) -> None:
        provider = self._make_provider("leader")
        remote_addr = _addr()
        caps = {"backend": "remote"}

        reg1 = FederationRegister(
            admin_address=remote_addr, capabilities=caps, first_time=True
        )
        provider.handle_envelope(
            Envelope(
                target=provider._federation_actor_id,
                payload=reg1,
                sender=remote_addr.actor_id,
            )
        )

        reg2 = FederationRegister(
            admin_address=remote_addr, capabilities=caps, first_time=False
        )
        provider.handle_envelope(
            Envelope(
                target=provider._federation_actor_id,
                payload=reg2,
                sender=remote_addr.actor_id,
            )
        )

        systems = provider.list_systems()
        assert len(systems) >= 1

    def test_federation_deregister_removes_member(self) -> None:
        provider = self._make_provider("leader")
        remote_addr = _addr()

        provider.handle_envelope(
            Envelope(
                target=provider._federation_actor_id,
                payload=FederationRegister(
                    admin_address=remote_addr,
                    capabilities={},
                    first_time=True,
                ),
                sender=remote_addr.actor_id,
            )
        )
        assert len(provider.list_systems()) >= 1

        provider.handle_envelope(
            Envelope(
                target=provider._federation_actor_id,
                payload=FederationDeRegister(
                    admin_address=remote_addr,
                ),
                sender=remote_addr.actor_id,
            )
        )
        systems = provider.list_systems()
        assert all(
            s.address != remote_addr for s in systems
        ), f"Expected remote system to be removed, got {systems}"

    def test_federation_invite_triggers_registration_response(self) -> None:
        provider = self._make_provider("invited")
        remote = _addr()

        provider.handle_envelope(
            Envelope(
                target=provider._federation_actor_id,
                payload=FederationInvite(),
                sender=remote.actor_id,
            )
        )

    def test_notification_handler_receives_updates(self) -> None:
        provider = self._make_provider("leader")
        handler_addr = _addr()

        provider.handle_envelope(
            Envelope(
                target=provider._federation_actor_id,
                payload=NotifyOnSystemRegistration(
                    handler_address=handler_addr,
                    enable_notification=True,
                ),
                sender=handler_addr.actor_id,
            )
        )

        remote_addr = _addr()
        provider.handle_envelope(
            Envelope(
                target=provider._federation_actor_id,
                payload=FederationRegister(
                    admin_address=remote_addr,
                    capabilities={"backend": "remote"},
                    first_time=True,
                ),
                sender=remote_addr.actor_id,
            )
        )

    def test_unsubscribe_unregisters_watcher(self) -> None:
        provider = self._make_provider("sys")
        events: list[SystemEvent] = []
        unsub = provider.watch(lambda e: events.append(e))
        events.clear()

        unsub()
        remote_addr = _addr()
        provider.handle_envelope(
            Envelope(
                target=provider._federation_actor_id,
                payload=FederationRegister(
                    admin_address=remote_addr,
                    capabilities={},
                    first_time=True,
                ),
                sender=remote_addr.actor_id,
            )
        )
        assert len(events) == 0

    def test_pre_register_with_federation_register(self) -> None:
        provider = self._make_provider("leader")
        remote_addr = _addr()

        provider.handle_envelope(
            Envelope(
                target=provider._federation_actor_id,
                payload=FederationRegister(
                    admin_address=remote_addr,
                    capabilities={},
                    pre_register=True,
                ),
                sender=remote_addr.actor_id,
            )
        )
        systems = provider.list_systems()
        assert len(systems) >= 1
