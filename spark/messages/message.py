"""
Message class
"""
from enum import StrEnum
from dataclasses import dataclass
from typing import Any


class RoleType(StrEnum):
    """Role types for messages."""
    USER = "user"
    SYSTEM = "system"
    ASSISTANT = "assistant"
    TOOL = "tool"
    AGENT = "agent"
    ACTION = "action"


@dataclass
class Message:
    """Represents a message exchanged between an agent and a user or another agent."""

    role: RoleType
    content: str

    def __str__(self) -> str:
        return f"{self.role}: {self.content}"

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary format."""
        return {
            "role": self.role,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """Create a Message from a dictionary."""
        return cls(
            content=data["content"],
            role=data.get("role", "user"),
        )

    @classmethod
    def user(cls, content: str) -> "Message":
        """Create a user message."""
        return cls(content=content, role=RoleType.USER)

    @classmethod
    def assistant(cls, content: str) -> "Message":
        """Create an assistant message."""
        return cls(content=content, role=RoleType.ASSISTANT)

    @classmethod
    def tool(cls, content: str) -> "Message":
        """Create a tool message."""
        return cls(content=content, role=RoleType.TOOL)
