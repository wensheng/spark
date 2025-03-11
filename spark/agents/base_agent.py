"""
Base agent class
"""
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

from ..messages.message import Message


@dataclass
class BaseAgent(ABC):
    """Base class for all agents in the framework."""
    name: str = field(default="Agent")
    chat_history: list[Message] = field(default_factory=list)

    @abstractmethod
    async def process(self, message: Message) -> Message:
        """Process a message."""
        raise NotImplementedError

    def add_message(self, message: Message) -> None:
        """Add a message to the conversation history."""
        self.chat_history.append(message)

    def get_history(self) -> list[dict[str, Any]]:
        """Get the conversation history."""
        return [asdict(item) for item in self.chat_history]

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self.chat_history = []
