"""
Chat agent class
"""
from dataclasses import dataclass, field

from ..messages.message import Message
from ..llms.llm import LLM
from .base_agent import BaseAgent


@dataclass
class ChatAgent(BaseAgent):
    """Chat agent class"""
    name: str = field(default="ChatBot")
    llm: LLM | None = None

    async def process(self, message: Message) -> Message:
        """Process a user message and generate a response using the LLM."""
        self.add_message(message)

        if self.llm:
            response_content = await self.llm.chat(self.get_history())
        else:
            response_content = f"Hello! You said: '{message.content}'"

        response = Message(content=response_content, role="assistant")
        self.add_message(response)
        return response
