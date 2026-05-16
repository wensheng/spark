"""Mailbox backpressure policy types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MailboxOverflow = Literal["reject", "drop_newest", "drop_oldest", "dead_letter", "block"]


@dataclass(frozen=True, slots=True)
class MailboxPolicy:
    """Backpressure policy for an actor's user-message mailbox lane."""

    max_size: int | None = None
    overflow: MailboxOverflow = "reject"

    def __post_init__(self) -> None:
        if self.max_size is not None and self.max_size <= 0:
            raise ValueError("max_size must be positive when set")
        if self.overflow not in {"reject", "drop_newest", "drop_oldest", "dead_letter", "block"}:
            raise ValueError(f"unsupported mailbox overflow policy: {self.overflow!r}")

    @classmethod
    def unbounded(cls) -> MailboxPolicy:
        """Return the default unbounded user mailbox policy."""
        return cls()

    @property
    def bounded(self) -> bool:
        """Return whether the user lane has a finite capacity."""
        return self.max_size is not None
