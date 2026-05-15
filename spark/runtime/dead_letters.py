"""Dead-letter collection for undeliverable envelopes."""

from ..core.identity import Envelope
from ..core.messages import DeadLetter


class DeadLetterHandler:
    """Stores dead letters for diagnostics and future subscribers."""

    def __init__(self) -> None:
        self._letters: list[DeadLetter] = []

    def handle(self, envelope: Envelope, reason: str) -> None:
        """Record an undeliverable envelope."""
        self._letters.append(DeadLetter(original_envelope=envelope, reason=reason))

    @property
    def letters(self) -> tuple[DeadLetter, ...]:
        """Return recorded dead letters."""
        return tuple(self._letters)
