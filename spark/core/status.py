"""
Pretty-printer for Spark status responses.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .messages import ActorStatus, SystemStatus


def _common_format_status(
    tofd: Any,
    response: SystemStatus | ActorStatus,
    child_tag: str,
    show_address: Callable[[Any], str] = str,
) -> None:
    """Write the common-fields section shared by system and actor status."""
    c = response.common

    tofd.write(f"  |{child_tag} Actors [{len(c.child_actors)}]:\n")
    for a in c.child_actors:
        tofd.write(f"    @ {show_address(a)}\n")

    if c.governor:
        tofd.write(f"  |Rate Governor: {c.governor}\n")

    tofd.write(f"  |Pending Messages [{len(c.pending_messages)}]:\n")
    for pm in c.pending_messages:
        tofd.write(f"    {show_address(pm.from_addr)} --> {show_address(pm.to_addr)}:  {pm.message}\n")

    tofd.write(f"  |Received Messages [{len(c.received_messages)}]:\n")
    for rm in c.received_messages:
        tofd.write(f"    {show_address(rm.to_addr)} <-- {show_address(rm.from_addr)}:  {rm.message}\n")

    tofd.write(f"  |Pending Wakeups [{len(c.pending_wakeups)}]:\n")
    for pw in c.pending_wakeups:
        tofd.write(f"    {show_address(pw.target)}:  {pw.payload}  (in {pw.delay:.1f}s)\n")

    tofd.write(f"  |Messages Sent: {c.messages_sent}\n")
    tofd.write(f"  |Send Failures: {c.send_failures}\n")
    tofd.write(f"  |Messages Received: {c.messages_received}\n")

    if c.pending_addr_counts:
        tofd.write(f"  |Pending Address Resolution [{len(c.pending_addr_counts)}]:\n")
        for a, cnt in sorted(c.pending_addr_counts.items()):
            tofd.write(f"    {a}: {cnt}\n")

    if c.misc:
        keys = sorted(c.misc)
        max_val_len = min(40, max(len(str(c.misc[k])) for k in keys))
        for k in keys:
            tofd.write(f"  |> {str(c.misc[k]):>{max_val_len}s} - {k}\n")


def format_status(
    response: object,
    show_address: Callable[[Any], str] = str,
    tofd: Any = None,
) -> None:
    """Pretty-print a ``SystemStatus`` or ``ActorStatus`` response.

    Args:
        response: The status response to format.
        show_address: Callable to convert an address to a display string.
        tofd: File-like object to write to. Defaults to ``sys.stdout``.
    """
    if tofd is None:
        import sys as _sys

        tofd = _sys.stdout

    if isinstance(response, SystemStatus):
        tag = "  [IN SHUTDOWN]" if response.in_shutdown else ""
        tofd.write(f"Status of Syndicate @ {show_address(response.admin_address)}:{tag}\n")
        tofd.write(f"  |Actors: {response.actor_count}\n")
        tofd.write(f"  |Uptime: {response.uptime_seconds:.1f}s\n")
        tofd.write(f"  |Backend: {response.backend_type}\n")

        if response.capabilities:
            tofd.write(f"  |Capabilities [{len(response.capabilities)}]:\n")
            for k in sorted(response.capabilities):
                tofd.write(f"    {k:>29s}: {response.capabilities[k]}\n")

        if response.federation_leader:
            tofd.write(f"  |Federation Leader: {show_address(response.federation_leader)}\n")
            if response.federation_register_time:
                tofd.write(f"  Registration valid {response.federation_register_time}\n")
        elif response.federation_attendees:
            tofd.write("  Appears to be the Federation Leader\n")

        if response.notify_addresses:
            tofd.write(f"  |Federation Notifications [{len(response.notify_addresses)}]:\n")
            for each in response.notify_addresses:
                tofd.write(f"    {show_address(each)}\n")

        tofd.write(f"  |Federation Attendees [{len(response.federation_attendees)}]:\n")
        for ca in response.federation_attendees:
            tofd.write(f"    @ {show_address(ca.address)}: {ca.valid_until}\n")

        _common_format_status(tofd, response, "Primary", show_address)

        if response.dead_letter_handler:
            tofd.write(f"  |DeadLetter Handler: {show_address(response.dead_letter_handler)}\n")
        tofd.write(f"  |DeadLetter Addresses [{len(response.dead_letter_addresses)}]:\n")
        for a in response.dead_letter_addresses:
            tofd.write(f"    {show_address(a)}\n")

        tofd.write(f"  |Global Actors [{len(response.global_actors)}]:\n")
        for name in sorted(response.global_actors):
            tofd.write(f"    {name}: {show_address(response.global_actors[name])}\n")

    elif isinstance(response, ActorStatus):
        exit_tag = f" EXITING:{response.exiting}" if response.exiting else ""
        tofd.write(f"Status of {response.actor_class} Actor @ {show_address(response.actor_address)}:{exit_tag}\n")
        tofd.write(f"  |Administrator: {show_address(response.admin_address)}\n")
        tofd.write(f"  |Parent  Actor: {show_address(response.parent_address)}\n")
        _common_format_status(tofd, response, "Child", show_address)

    else:
        tofd.write(f"Status Query Response: {response!s}\n")
