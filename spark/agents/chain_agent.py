"""
Chain agent class
"""
from dataclasses import dataclass, field
from typing import List

from ..messages.message import Message, RoleType
from ..llms.llm import LLM
from .base_agent import BaseAgent


@dataclass
class PromptChainAgent(BaseAgent):
    """Prompt Chain Agent class"""
    name: str = field(default="PromptChainAgent")
    llm: LLM | None = None
    prompts: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Post-initialization to ensure prompts are set."""
        if not self.prompts:
            self.prompts = [
                "First prompt template.",
                "Second prompt template.",
                # Add more prompts as needed
            ]

    async def process(self, message: Message) -> Message:
        """Process a user message through a chain of prompts and generate a response using the LLM."""
        self.add_message(message)
        
        if not self.llm:
            response_content = f"Hello! You said: '{message.content}'"
            response = Message(content=response_content, role=RoleType.ASSISTANT)
            self.add_message(response)
            return response

        result = message.content
        for i, prompt in enumerate(self.prompts, 1):
            # print(f"\nChain Step {i}:")
            chained_prompt = f"{prompt}\nInput: {result}"
            response_text = await self.llm.chat([{
                "role": RoleType.USER.value,
                "content": chained_prompt
            }])
            # print(response_text)
            result = response_text
        
        response = Message(content=result, role=RoleType.ASSISTANT)
        self.add_message(response)
        return response
