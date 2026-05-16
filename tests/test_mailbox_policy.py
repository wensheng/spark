"""Tests for mailbox backpressure policy types."""

import pytest

from spark import MailboxPolicy


class TestMailboxPolicy:
    def test_unbounded_default(self) -> None:
        policy = MailboxPolicy.unbounded()

        assert policy.max_size is None
        assert policy.overflow == "reject"
        assert policy.bounded is False

    def test_bounded_policy(self) -> None:
        policy = MailboxPolicy(max_size=10, overflow="drop_oldest")

        assert policy.max_size == 10
        assert policy.overflow == "drop_oldest"
        assert policy.bounded is True

    def test_rejects_invalid_size(self) -> None:
        with pytest.raises(ValueError, match="max_size"):
            MailboxPolicy(max_size=0)

    def test_rejects_invalid_overflow(self) -> None:
        with pytest.raises(ValueError, match="unsupported mailbox overflow"):
            MailboxPolicy(max_size=1, overflow="explode")  # type: ignore[arg-type]
